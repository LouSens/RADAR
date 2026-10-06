"""F7. Track records: what followed each kind of signal in the past, against all days.

For every past day a signal fired, the return over the next day and the next week is
taken, and the same is done for every day as the baseline. A signal has an edge only
if rises followed it clearly more or less often than they follow any day.

Pure functions. A forward return starts at the close of the signal's day, so it never
overlaps what the signal was made from.
"""

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.stats import binomtest, mannwhitneyu

MODEL_VERSION = "signal-track-1"
MIN_OCCURRENCES = 30
SIGNIFICANCE = 0.05
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)

Verdict = Literal[
    "followed by rises more often",
    "followed by falls more often",
    "no measurable edge",
    "not enough occurrences",
]
# The second question: whichever way the market went, was the move larger than usual?
SizeVerdict = Literal[
    "followed by larger moves",
    "followed by smaller moves",
    "no measurable difference",
    "not enough occurrences",
]


class Outcome(BaseModel):
    """Forward returns over one horizon, for the signal days or for all days."""

    n: int
    share_positive: float | None
    # 95% range for the share (Wilson). Null without any cases.
    share_low: float | None
    share_high: float | None
    mean: float | None
    # Typical size of the move whichever way it went.
    mean_size: float | None
    quantiles: dict[str, float]


class HorizonRecord(BaseModel):
    # Steps ahead, and the plain word for them ("1 day", "1 week").
    steps: int
    label: str
    signal: Outcome
    baseline: Outcome
    # Chance of a share at least this far from the baseline's if the signal meant nothing.
    p_value: float | None
    verdict: Verdict
    # The same for the size of the move: signal days against every other day.
    size_p_value: float | None = None
    size_verdict: SizeVerdict = "not enough occurrences"


class TrackRecord(BaseModel):
    type: str
    symbol: str
    variant: str
    n: int
    first_day: str | None
    last_day: str | None
    horizons: list[HorizonRecord]
    # The verdicts quoted for the signal: the one-day horizon's.
    verdict: Verdict
    size_verdict: SizeVerdict = "not enough occurrences"


def forward_returns(close: pd.Series, steps: int) -> pd.Series:
    """Log return from each day's close to the close `steps` days later."""
    logged = pd.Series(np.log(close.to_numpy(dtype=float)), index=close.index)
    return (logged.shift(-steps) - logged).rename(f"forward_{steps}")


def wilson(positive: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """The 95% range for a share, well behaved for small counts."""
    share = positive / n
    centre = (share + z**2 / (2 * n)) / (1 + z**2 / n)
    half = z * np.sqrt(share * (1 - share) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def outcome(returns: pd.Series) -> Outcome:
    values = returns.dropna().to_numpy(dtype=float)
    n = len(values)
    if n == 0:
        return Outcome(
            n=0,
            share_positive=None,
            share_low=None,
            share_high=None,
            mean=None,
            mean_size=None,
            quantiles={},
        )
    positive = int((values > 0).sum())
    low, high = wilson(positive, n)
    return Outcome(
        n=n,
        share_positive=positive / n,
        share_low=low,
        share_high=high,
        mean=float(values.mean()),
        mean_size=float(np.abs(values).mean()),
        quantiles={f"{q:g}": float(np.quantile(values, q)) for q in QUANTILES},
    )


def horizon_record(
    forward: pd.Series, days: list[pd.Timestamp], steps: int, label: str
) -> HorizonRecord:
    signal = outcome(forward.reindex(days))
    baseline = outcome(forward)
    p_value = None
    if signal.n > 0 and baseline.share_positive is not None and signal.share_positive is not None:
        p_value = float(
            binomtest(
                round(signal.share_positive * signal.n), signal.n, baseline.share_positive
            ).pvalue
        )
    # Sizes on signal days against sizes on all the other days.
    sizes = forward.dropna().abs()
    on_signal = sizes[sizes.index.isin(days)]
    others = sizes[~sizes.index.isin(days)]
    size_p_value = (
        float(mannwhitneyu(on_signal.to_numpy(), others.to_numpy()).pvalue)
        if len(on_signal) > 0 and len(others) > 0
        else None
    )
    return HorizonRecord(
        steps=steps,
        label=label,
        signal=signal,
        baseline=baseline,
        p_value=p_value,
        verdict=verdict(signal, baseline, True),
        size_p_value=size_p_value,
        size_verdict=size_verdict(signal, baseline, size_p_value is not None),
    )


def verdict(signal: Outcome, baseline: Outcome, survives: bool) -> Verdict:
    """An edge needs enough cases, a range for the share that excludes the baseline's
    share, and to survive the correction for how many records were looked at."""
    if signal.n < MIN_OCCURRENCES:
        return "not enough occurrences"
    if (
        baseline.share_positive is None
        or signal.share_low is None
        or signal.share_high is None
        or not survives
    ):
        return "no measurable edge"
    if signal.share_low > baseline.share_positive:
        return "followed by rises more often"
    if signal.share_high < baseline.share_positive:
        return "followed by falls more often"
    return "no measurable edge"


def size_verdict(signal: Outcome, baseline: Outcome, survives: bool) -> SizeVerdict:
    """Larger or smaller moves need enough cases and a difference in size that survives
    the correction for how many records were looked at."""
    if signal.n < MIN_OCCURRENCES:
        return "not enough occurrences"
    if signal.mean_size is None or baseline.mean_size is None or not survives:
        return "no measurable difference"
    if signal.mean_size > baseline.mean_size:
        return "followed by larger moves"
    return "followed by smaller moves"


def record(
    type_: str,
    symbol: str,
    variant: str,
    days: list[pd.Timestamp],
    close: pd.Series,
    horizons: list[tuple[int, str]],
) -> TrackRecord:
    """The track record of one kind of signal on one market. `close` is indexed by day."""
    known = [d for d in days if d in close.index]
    rows = [
        horizon_record(forward_returns(close, steps), known, steps, label)
        for steps, label in horizons
    ]
    return TrackRecord(
        type=type_,
        symbol=symbol,
        variant=variant,
        n=len(known),
        first_day=min(known).date().isoformat() if known else None,
        last_day=max(known).date().isoformat() if known else None,
        horizons=rows,
        verdict=rows[0].verdict if rows else "not enough occurrences",
        size_verdict=rows[0].size_verdict if rows else "not enough occurrences",
    )


def _survivors(tested: list[tuple[int, int, float]], level: float) -> set[tuple[int, int]]:
    """Benjamini-Hochberg: which of these tests still count after correction."""
    ranked = sorted(tested, key=lambda item: item[2])
    passing = 0
    for rank, (_, _, p_value) in enumerate(ranked, start=1):
        if p_value <= level * rank / len(ranked):
            passing = rank
    return {(i, j) for i, j, _ in ranked[:passing]}


def correct_family(records: list[TrackRecord], level: float = SIGNIFICANCE) -> list[TrackRecord]:
    """Benjamini-Hochberg across every record and horizon with enough cases, once for
    direction and once for size.

    Many records are looked at together, and by luck alone about one in twenty would
    look like an edge. A record keeps a verdict only if it survives this correction.
    """
    enough = [
        (i, j, h)
        for i, r in enumerate(records)
        for j, h in enumerate(r.horizons)
        if h.signal.n >= MIN_OCCURRENCES
    ]
    direction = _survivors(
        [(i, j, h.p_value) for i, j, h in enough if h.p_value is not None], level
    )
    size = _survivors(
        [(i, j, h.size_p_value) for i, j, h in enough if h.size_p_value is not None], level
    )
    corrected = []
    for i, r in enumerate(records):
        horizons = [
            h.model_copy(
                update={
                    "verdict": verdict(h.signal, h.baseline, (i, j) in direction),
                    "size_verdict": size_verdict(h.signal, h.baseline, (i, j) in size),
                }
            )
            for j, h in enumerate(r.horizons)
        ]
        corrected.append(
            r.model_copy(
                update={
                    "horizons": horizons,
                    "verdict": horizons[0].verdict if horizons else r.verdict,
                    "size_verdict": horizons[0].size_verdict if horizons else r.size_verdict,
                }
            )
        )
    return corrected
