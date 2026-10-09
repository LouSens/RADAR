"""Scoring a classifier against hand labels: accuracy and macro F1."""

from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel


class ClassScore(BaseModel):
    label: str
    # Of the items given this label, the share that truly had it.
    precision: float
    # Of the items that truly had this label, the share that were given it.
    recall: float
    f1: float
    # How many items truly had this label.
    support: int


class ClassificationReport(BaseModel):
    n: int
    accuracy: float
    # The plain average of each label's F1, so a rare label counts as much as a common one.
    macro_f1: float
    classes: list[ClassScore]


def report(
    truth: Sequence[str], predicted: Sequence[str], labels: Sequence[str]
) -> ClassificationReport:
    """Compare predictions with the true labels. Labels with no true items are left out
    of the macro average."""
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must have the same length")
    classes = []
    for label in labels:
        hit = sum(t == label and p == label for t, p in zip(truth, predicted, strict=True))
        given = sum(p == label for p in predicted)
        support = sum(t == label for t in truth)
        precision = hit / given if given else 0.0
        recall = hit / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        classes.append(
            ClassScore(label=label, precision=precision, recall=recall, f1=f1, support=support)
        )
    present = [c for c in classes if c.support > 0]
    correct = sum(t == p for t, p in zip(truth, predicted, strict=True))
    return ClassificationReport(
        n=len(truth),
        accuracy=correct / len(truth) if truth else 0.0,
        macro_f1=sum(c.f1 for c in present) / len(present) if present else 0.0,
        classes=classes,
    )


class Comparison(BaseModel):
    """Whether one classifier is measurably better than another on the same items."""

    n: int
    # Items the first got right and the second got wrong, and the reverse.
    only_first_right: int
    only_second_right: int
    # McNemar's exact test: the chance of a split this lopsided if the two were equal.
    p_value: float


def mcnemar(truth: Sequence[str], first: Sequence[str], second: Sequence[str]) -> Comparison:
    """Compare two classifiers on the same items, using only the items where they differ."""
    from scipy.stats import binom

    if not len(truth) == len(first) == len(second):
        raise ValueError("truth and both predictions must have the same length")
    only_first = sum(a == t and b != t for t, a, b in zip(truth, first, second, strict=True))
    only_second = sum(a != t and b == t for t, a, b in zip(truth, first, second, strict=True))
    differing = only_first + only_second
    p_value = 1.0
    if differing:
        p_value = min(1.0, 2.0 * float(binom.cdf(min(only_first, only_second), differing, 0.5)))
    return Comparison(
        n=len(truth), only_first_right=only_first, only_second_right=only_second, p_value=p_value
    )


def log_loss(truth: Sequence[str], probabilities: np.ndarray, labels: Sequence[str]) -> float:
    """Cross-entropy: how much probability the model put on the true label, averaged.

    `probabilities` has one row per item and one column per label, in the order of
    `labels`. Zero would be certainty and always right; a model that always says a
    third each scores 1.10 on three labels. Unlike accuracy it also counts how sure
    the model was, so being confidently wrong costs more than being unsure.
    """
    if len(truth) != len(probabilities):
        raise ValueError("truth and probabilities must have the same length")
    column = {label: i for i, label in enumerate(labels)}
    given = np.asarray(probabilities, dtype=float)[
        np.arange(len(truth)), [column[label] for label in truth]
    ]
    return float(-np.log(np.clip(given, 1e-12, 1.0)).mean())


def with_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    """The same probabilities made less sure (above 1) or more sure (below 1).

    The order of the labels in each row does not change, so neither does accuracy.
    """
    logits = np.log(np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    scaled = np.exp(logits)
    return np.asarray(scaled / scaled.sum(axis=1, keepdims=True))


def fit_temperature(
    truth: Sequence[str], probabilities: np.ndarray, labels: Sequence[str]
) -> float:
    """The one temperature, from 0.5 to 5, that gives the lowest cross-entropy."""
    grid = np.arange(0.5, 5.0001, 0.05)
    losses = [log_loss(truth, with_temperature(probabilities, t), labels) for t in grid]
    return float(grid[int(np.argmin(losses))])


def cohen_kappa(first: Sequence[str], second: Sequence[str], labels: Sequence[str]) -> float:
    """Agreement between two sets of labels, beyond what chance alone would give.

    1 is full agreement; 0 is what two labellers would reach by handing out labels at
    their own usual rates without reading anything.
    """
    if len(first) != len(second) or not len(first):
        raise ValueError("Both sets of labels must have the same, non-zero length")
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second, strict=True)) / n
    by_chance = sum(
        (list(first).count(label) / n) * (list(second).count(label) / n) for label in labels
    )
    if by_chance == 1.0:
        return 1.0
    return float((observed - by_chance) / (1.0 - by_chance))
