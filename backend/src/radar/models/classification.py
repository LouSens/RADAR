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
