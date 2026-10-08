"""Fine-tuning the sentiment model on our own labelled headlines.

FinBERT was trained on formal financial sentences. Our articles are crypto headlines,
quoted posts, and market wraps, so the model is given a few more passes over headlines
of that kind, with their labels, at a low learning rate. This adjusts it to our text
without throwing away what it already knows.

Guarding against leakage: this module only ever sees the training and validation parts.
The model is chosen by its score on the validation part; the test part is scored once,
afterwards, by the caller. Needs the `nlp` extra.
"""

import random
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from radar.models import classification, sentiment

MODEL_VERSION = "finbert-radar-1"
# Must match the max_length used at inference time in sentiment.FinbertScorer so that
# the model is never fine-tuned on shorter context than it sees in production.
MAX_TOKENS = 256


class Epoch(BaseModel):
    epoch: int
    train_loss: float
    validation_loss: float
    validation_accuracy: float
    validation_macro_f1: float


class TrainingResult(BaseModel):
    base_model: str
    epochs: list[Epoch]
    # The epoch whose weights were kept: the best macro F1 on the validation part.
    best_epoch: int
    n_train: int
    n_validation: int
    learning_rate: float
    batch_size: int
    seed: int


def _llrd_param_groups(
    model: Any,
    learning_rate: float,
    weight_decay: float,
    layer_decay: float = 0.9,
) -> list[dict[str, Any]]:
    """Layer-wise learning rate decay parameter groups.

    Lower transformer layers encode general language and should update more slowly;
    upper layers and the classification head adapt to the task domain. Each encoder
    layer gets a learning rate that is ``layer_decay`` times the one above it. The
    embedding layer gets the smallest rate of all.

    Supports both BERT-family (``model.bert``) and DeBERTa-family (``model.deberta``)
    architectures. Falls back with an ``AttributeError`` for unknown architectures so
    the caller can default to a flat learning rate.
    """
    no_decay = {"bias", "LayerNorm.weight"}

    def wd(name: str) -> float:
        return 0.0 if any(nd in name for nd in no_decay) else weight_decay

    # Resolve the encoder layers and embedding module for BERT or DeBERTa
    if hasattr(model, "bert"):
        encoder_layers = model.bert.encoder.layer
        embeddings = model.bert.embeddings
    elif hasattr(model, "deberta"):
        encoder_layers = model.deberta.encoder.layer
        embeddings = model.deberta.embeddings
    else:
        raise AttributeError("Unknown model architecture; LLRD not supported")

    groups: list[dict[str, Any]] = []

    # Classification head — full learning rate
    head_modules = []
    for name in ("classifier", "pooler"):
        if hasattr(model, name):
            head_modules.append(getattr(model, name))
    for module in head_modules:
        for name, p in module.named_parameters():
            groups.append({"params": [p], "lr": learning_rate, "weight_decay": wd(name)})

    # Encoder layers — decay from the top downward
    n = len(encoder_layers)
    for i, layer in enumerate(reversed(encoder_layers)):
        lr_i = learning_rate * (layer_decay ** (i + 1))
        for name, p in layer.named_parameters():
            groups.append({"params": [p], "lr": lr_i, "weight_decay": wd(name)})

    # Embeddings — smallest rate (one step below layer 0)
    lr_embed = learning_rate * (layer_decay ** (n + 1))
    for name, p in embeddings.named_parameters():
        groups.append({"params": [p], "lr": lr_embed, "weight_decay": wd(name)})

    return groups


def oversample_to_balance(
    texts: Sequence[str],
    labels: Sequence[str],
    rng: "np.random.Generator",
) -> tuple[list[str], list[str]]:
    """Oversample minority classes so every class has the same count as the majority.

    Samples are drawn with replacement within each class. The resulting list is
    shuffled so that classes are interleaved rather than grouped.
    """
    counts = Counter(labels)
    max_count = max(counts.values())
    out_texts: list[str] = []
    out_labels: list[str] = []
    for label, count in counts.items():
        indices = [i for i, given in enumerate(labels) if given == label]
        extras = rng.choice(len(indices), size=max_count - count, replace=True)
        selected = indices + [indices[j] for j in extras]
        out_texts += [texts[i] for i in selected]
        out_labels += [label] * max_count
    order = rng.permutation(len(out_texts))
    return [out_texts[i] for i in order], [out_labels[i] for i in order]


def fine_tune(
    train_texts: Sequence[str],
    train_labels: Sequence[str],
    validation_texts: Sequence[str],
    validation_labels: Sequence[str],
    out_dir: Path,
    *,
    base_model: str = sentiment.MODEL_ID,
    label_names: list[str] | None = None,
    epochs: int = 20,
    learning_rate: float = 2e-5,
    batch_size: int = 16,
    weight_decay: float = 0.01,
    warmup_share: float = 0.1,
    seed: int = 13,
    # --- training improvements ---
    early_stopping_patience: int = 3,
    label_smoothing: float = 0.1,
    class_weights: bool = True,
    layer_wise_lr_decay: float = 0.9,
    oversample_minority: bool = True,
) -> TrainingResult:
    """Train on the training part, keep the epoch that does best on the validation part.

    The kept model and its tokenizer are saved to ``out_dir``.

    Parameters
    ----------
    label_names:
        Override the label order from ``model.config.id2label``. Required when the
        base model has no pre-trained classification head (e.g. a raw DeBERTa checkpoint).
        Must be a list of the class names in model-index order, e.g.
        ``["positive", "negative", "neutral"]``.
    oversample_minority:
        If ``True``, minority classes are oversampled with replacement to match the
        majority class count before each training run. This improves recall on the
        directional (positive/negative) labels without requiring new data.
    early_stopping_patience:
        Stop training after this many consecutive epochs without an improvement in
        validation macro-F1. The epoch with the best score is always saved.
    label_smoothing:
        Cross-entropy label smoothing factor. Reduces overconfidence and improves
        macro-F1 on imbalanced classes.
    class_weights:
        Weight the cross-entropy loss inversely to class frequency. Helps when one
        class (typically "neutral") dominates the training set.
    layer_wise_lr_decay:
        Per-layer learning rate decay multiplier (< 1 enables LLRD). Lower transformer
        layers train at a smaller LR to preserve general language knowledge. Set to 1.0
        to disable.
    """
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    tokenizer = AutoTokenizer.from_pretrained(base_model)

    if label_names is not None:
        # Raw checkpoint with no pre-trained head — configure the label mapping explicitly
        id2label = dict(enumerate(label_names))
        label2id = {name: i for i, name in enumerate(label_names)}
        model = AutoModelForSequenceClassification.from_pretrained(
            base_model,
            num_labels=len(label_names),
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True,
        ).to(device)
        index = {name: i for i, name in enumerate(label_names)}
        names = label_names
    else:
        # Pre-trained head (FinBERT etc.) — use the model's own label numbering
        model = AutoModelForSequenceClassification.from_pretrained(base_model).to(device)
        index = {name.lower(): i for i, name in model.config.id2label.items()}
        names = [name for name, _ in sorted(index.items(), key=lambda item: item[1])]

    def encode(texts: Sequence[str]) -> dict[str, "torch.Tensor"]:
        return dict(
            tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
                return_tensors="pt",
            )
        )

    def targets(labels: Sequence[str]) -> "torch.Tensor":
        return torch.tensor([index[label] for label in labels], dtype=torch.long)

    rng = np.random.default_rng(seed)

    # --- minority oversampling ---
    # Done first: the class weights and the length of the schedule below must describe
    # the headlines that are actually trained on, not the ones that were handed in.
    if oversample_minority:
        eff_texts, eff_labels = oversample_to_balance(train_texts, train_labels, rng)
    else:
        eff_texts, eff_labels = list(train_texts), list(train_labels)

    # --- class-weighted loss ---
    if class_weights:
        counts = Counter(eff_labels)
        n_effective = len(eff_labels)
        weights = torch.tensor(
            [n_effective / (len(names) * counts.get(name, 1)) for name in names],
            dtype=torch.float,
        ).to(device)
    else:
        weights = None
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, label_smoothing=label_smoothing)
    # The validation error is the plain one, whatever the training loss is, so that two
    # runs with different weights or smoothing can be put on one chart.
    plain_loss = torch.nn.CrossEntropyLoss()

    def evaluate() -> tuple[float, list[str]]:
        model.eval()
        losses, predicted = [], []
        with torch.no_grad():
            for start in range(0, len(validation_texts), 64):
                batch = {
                    k: v.to(device) for k, v in encode(validation_texts[start : start + 64]).items()
                }
                wanted = targets(validation_labels[start : start + 64]).to(device)
                logits = model(**batch).logits
                losses.append(float(plain_loss(logits, wanted)) * len(wanted))
                predicted += [names[i] for i in logits.argmax(dim=-1).tolist()]
        return sum(losses) / len(validation_texts), predicted

    # --- layer-wise LR decay ---
    if layer_wise_lr_decay < 1.0:
        try:
            param_groups = _llrd_param_groups(
                model, learning_rate, weight_decay, layer_wise_lr_decay
            )
        except AttributeError:
            param_groups = model.parameters()
    else:
        param_groups = model.parameters()

    optimiser = torch.optim.AdamW(param_groups, lr=learning_rate, weight_decay=weight_decay)
    steps = epochs * int(np.ceil(len(eff_texts) / batch_size))
    schedule = get_linear_schedule_with_warmup(optimiser, int(warmup_share * steps), steps)

    history: list[Epoch] = []
    best_score = -1.0
    no_improve = 0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffled = rng.permutation(len(eff_texts))
        total = 0.0
        for start in range(0, len(shuffled), batch_size):
            rows = shuffled[start : start + batch_size]
            batch = {k: v.to(device) for k, v in encode([eff_texts[i] for i in rows]).items()}
            wanted = targets([eff_labels[i] for i in rows]).to(device)
            logits = model(**batch).logits
            loss = loss_fn(logits, wanted)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            schedule.step()
            optimiser.zero_grad()
            total += float(loss) * len(rows)
        validation_loss, predicted = evaluate()
        report = classification.report(list(validation_labels), predicted, sentiment.LABELS)
        history.append(
            Epoch(
                epoch=epoch,
                train_loss=total / len(eff_texts),
                validation_loss=validation_loss,
                validation_accuracy=report.accuracy,
                validation_macro_f1=report.macro_f1,
            )
        )
        if report.macro_f1 > best_score:
            best_score = report.macro_f1
            no_improve = 0
            out_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
        else:
            no_improve += 1
            if no_improve >= early_stopping_patience:
                break
    best = max(history, key=lambda e: e.validation_macro_f1)
    return TrainingResult(
        base_model=base_model,
        epochs=history,
        best_epoch=best.epoch,
        n_train=len(train_texts),
        n_validation=len(validation_texts),
        learning_rate=learning_rate,
        batch_size=batch_size,
        seed=seed,
    )
