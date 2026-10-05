"""Scoring a classifier against hand labels: accuracy and macro F1."""

from collections.abc import Sequence

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
