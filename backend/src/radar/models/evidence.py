"""How sure are we? Small statistics that sit beside every figure the app shows.

- An interval for a share measured on a sample ("65% of 200" is really a range).
- A correction for running many tests at once, so that the few that pass by luck are
  not reported as findings.
- For a three-way tone classifier, how often it gets the direction outright wrong, which
  matters more to a reader than confusing "neutral" with "mildly positive".
"""

from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel
from scipy import stats

LEVEL = 0.95
FALSE_DISCOVERY_RATE = 0.05


def wilson(successes: int, n: int, level: float = LEVEL) -> tuple[float, float]:
    """The Wilson interval for a share: the range the true share plausibly lies in.

    Better behaved than the textbook interval for small samples and for shares near 0
    or 1. With no observations it is the whole range.
    """
    if n <= 0:
        return 0.0, 1.0
    z = float(stats.norm.ppf(0.5 + level / 2.0))
    share = successes / n
    centre = (share + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def share_interval(share: float, n: int, level: float = LEVEL) -> tuple[float, float]:
    """`wilson` for a share that was stored as a fraction of `n`."""
    return wilson(round(share * n), n, level)


def benjamini_hochberg(p_values: Sequence[float | None]) -> list[float | None]:
    """Adjust p-values for the number of tests run together (false discovery rate).

    If the adjusted values under 0.05 are called findings, then on average no more than
    5% of those findings are flukes. Missing p-values stay missing and are not counted.
    """
    known = [(p, i) for i, p in enumerate(p_values) if p is not None and not np.isnan(p)]
    adjusted: list[float | None] = [None] * len(p_values)
    m = len(known)
    smallest = 1.0
    for rank, (p, i) in sorted(enumerate(sorted(known), start=1), reverse=True):
        smallest = min(smallest, p * m / rank)
        adjusted[i] = smallest
    return adjusted


class Direction(BaseModel):
    """How a tone classifier does on direction, the part a reader acts on."""

    n: int
    # Items given the opposite pole to their label (positive for negative, or the reverse).
    opposite: int
    opposite_rate: float
    # Items where label and prediction both took a side, and how often the side matched.
    both_polar: int
    same_direction: float | None


def direction(
    truth: Sequence[str],
    predicted: Sequence[str],
    positive: str = "positive",
    negative: str = "negative",
) -> Direction:
    poles = {positive, negative}
    pairs = list(zip(truth, predicted, strict=True))
    polar = [(t, p) for t, p in pairs if t in poles and p in poles]
    opposite = sum(t != p for t, p in polar)
    return Direction(
        n=len(pairs),
        opposite=opposite,
        opposite_rate=opposite / len(pairs) if pairs else 0.0,
        both_polar=len(polar),
        same_direction=1.0 - opposite / len(polar) if polar else None,
    )
