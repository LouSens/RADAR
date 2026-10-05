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
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from radar.models import classification, sentiment

MODEL_VERSION = "finbert-radar-1"
MAX_TOKENS = 128


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


def fine_tune(
    train_texts: Sequence[str],
    train_labels: Sequence[str],
    validation_texts: Sequence[str],
    validation_labels: Sequence[str],
    out_dir: Path,
    *,
    base_model: str = sentiment.MODEL_ID,
    epochs: int = 4,
    learning_rate: float = 2e-5,
    batch_size: int = 16,
    weight_decay: float = 0.01,
    warmup_share: float = 0.1,
    seed: int = 13,
) -> TrainingResult:
    """Train on the training part, keep the epoch that does best on the validation part.

    The kept model and its tokenizer are saved to `out_dir`.
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
    model = AutoModelForSequenceClassification.from_pretrained(base_model).to(device)
    # Use the model's own numbering of the three labels.
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

    def evaluate() -> tuple[float, list[str]]:
        model.eval()
        losses, predicted = [], []
        with torch.no_grad():
            for start in range(0, len(validation_texts), 64):
                batch = {
                    k: v.to(device) for k, v in encode(validation_texts[start : start + 64]).items()
                }
                wanted = targets(validation_labels[start : start + 64]).to(device)
                output = model(**batch, labels=wanted)
                losses.append(float(output.loss) * len(wanted))
                predicted += [names[i] for i in output.logits.argmax(dim=-1).tolist()]
        return sum(losses) / len(validation_texts), predicted

    optimiser = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    steps = epochs * int(np.ceil(len(train_texts) / batch_size))
    schedule = get_linear_schedule_with_warmup(optimiser, int(warmup_share * steps), steps)
    order = np.random.default_rng(seed)
    history: list[Epoch] = []
    best_score = -1.0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffled = order.permutation(len(train_texts))
        total = 0.0
        for start in range(0, len(shuffled), batch_size):
            rows = shuffled[start : start + batch_size]
            batch = {k: v.to(device) for k, v in encode([train_texts[i] for i in rows]).items()}
            wanted = targets([train_labels[i] for i in rows]).to(device)
            loss = model(**batch, labels=wanted).loss
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
                train_loss=total / len(train_texts),
                validation_loss=validation_loss,
                validation_accuracy=report.accuracy,
                validation_macro_f1=report.macro_f1,
            )
        )
        if report.macro_f1 > best_score:
            best_score = report.macro_f1
            out_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
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
