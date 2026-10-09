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
    # The epoch whose weights were kept (see `keep` in `fine_tune`).
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

    Works from the parameter names, so it serves any encoder whose layers are named
    ``encoder.layer.N`` (BERT, RoBERTa, DeBERTa). Raises ``AttributeError`` when no
    such layer is found, so that a rate meant to decay is never silently left flat.
    """
    no_decay = ("bias", "LayerNorm.weight")
    named = list(model.named_parameters())
    depths = [_layer_of(name) for name, _ in named]
    found = [depth for depth in depths if depth is not None]
    if not found:
        raise AttributeError("No encoder layers found; layer-wise decay is not supported")
    n = max(found) + 1
    groups: list[dict[str, Any]] = []
    for (name, parameter), depth in zip(named, depths, strict=True):
        if depth is not None:
            steps_down = n - depth  # the top layer is one step under the head
        elif "embeddings" in name:
            steps_down = n + 1
        else:
            steps_down = 0  # the classification head and pooler: the full rate
        groups.append(
            {
                "params": [parameter],
                "lr": learning_rate * layer_decay**steps_down,
                "weight_decay": 0.0 if any(part in name for part in no_decay) else weight_decay,
            }
        )
    return groups


def _layer_of(name: str) -> int | None:
    """The encoder layer a parameter belongs to, read from its name."""
    marker = "encoder.layer."
    if marker not in name:
        return None
    return int(name.split(marker, 1)[1].split(".", 1)[0])


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
    epochs: int = 4,
    learning_rate: float = 2e-5,
    batch_size: int = 16,
    weight_decay: float = 0.01,
    warmup_share: float = 0.1,
    seed: int = 13,
    # --- each of these is off unless asked for, so a plain call is a plain run ---
    early_stopping_patience: int = 99,
    label_smoothing: float = 0.0,
    class_weights: bool = False,
    layer_wise_lr_decay: float = 1.0,
    oversample_minority: bool = False,
    dropout: float | None = None,
    train_targets: np.ndarray | None = None,
    keep: str = "loss",
) -> TrainingResult:
    """Train on the training part, keep the epoch that does best on the validation part.

    The kept model and its tokenizer are saved to ``out_dir``.

    Parameters
    ----------
    keep:
        Which epoch is saved: ``"loss"`` for the lowest validation error, ``"f1"`` for
        the highest balanced score. The error moves less from one epoch to the next
        on a few hundred headlines, and an epoch after it has turned upwards is one
        where the model has begun to memorise. Early stopping follows the same measure.
    dropout:
        Overrides the share of units dropped inside the encoder while training
        (the models ship with 0.1). ``None`` leaves the model's own setting.
    train_targets:
        One row per training text, each a share for every label in
        ``sentiment.LABELS`` order, used in place of ``train_labels`` as the thing
        the model is trained towards. A headline two labelling passes disagree on can
        then count half for each. Not combined with class weights or oversampling.
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
        Stop training after this many consecutive epochs without an improvement on
        the validation part, by the measure named in ``keep``.
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

    if keep not in ("loss", "f1"):
        raise ValueError("keep must be 'loss' or 'f1'")
    if train_targets is not None and (class_weights or oversample_minority):
        raise ValueError("Shares per label cannot be combined with weights or oversampling")
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    regular = (
        {}
        if dropout is None
        else {"hidden_dropout_prob": dropout, "attention_probs_dropout_prob": dropout}
    )

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
            **regular,
        ).to(device)
        index = {name: i for i, name in enumerate(label_names)}
        names = label_names
    else:
        # Pre-trained head (FinBERT etc.) — use the model's own label numbering
        model = AutoModelForSequenceClassification.from_pretrained(base_model, **regular).to(device)
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
    # Shares per label, put into the model's own label order.
    shares = None
    if train_targets is not None:
        ours = {label: i for i, label in enumerate(sentiment.LABELS)}
        shares = torch.tensor(
            np.asarray(train_targets, dtype=float)[:, [ours[name] for name in names]],
            dtype=torch.float,
        )

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
        param_groups = _llrd_param_groups(model, learning_rate, weight_decay, layer_wise_lr_decay)
    else:
        param_groups = model.parameters()

    optimiser = torch.optim.AdamW(param_groups, lr=learning_rate, weight_decay=weight_decay)
    steps = epochs * int(np.ceil(len(eff_texts) / batch_size))
    schedule = get_linear_schedule_with_warmup(optimiser, int(warmup_share * steps), steps)

    history: list[Epoch] = []
    best_score = -np.inf
    no_improve = 0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffled = rng.permutation(len(eff_texts))
        total = 0.0
        for start in range(0, len(shuffled), batch_size):
            rows = shuffled[start : start + batch_size]
            batch = {k: v.to(device) for k, v in encode([eff_texts[i] for i in rows]).items()}
            if shares is None:
                wanted = targets([eff_labels[i] for i in rows]).to(device)
            else:
                wanted = shares[rows].to(device)
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
        score = -validation_loss if keep == "loss" else report.macro_f1
        if score > best_score:
            best_score = score
            no_improve = 0
            out_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
        else:
            no_improve += 1
            if no_improve >= early_stopping_patience:
                break
    best = (
        min(history, key=lambda e: e.validation_loss)
        if keep == "loss"
        else max(history, key=lambda e: e.validation_macro_f1)
    )
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
