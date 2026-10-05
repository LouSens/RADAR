"""Risk transmission and weekend gaps: what one market's trouble has meant for another.

Two questions, both answered by counting what actually followed past cases.

**Risk transmission.** In the sessions after market A entered its turbulent state, were
market B's swings larger than usual? An episode starts on the first session A is
labelled turbulent after a stretch when it was not. The label is the filtered one, known
at that session's close, so the episode is something a reader could have seen at the
time. What is measured comes strictly after it.

**Weekend gaps.** Bitcoin trades while stock markets are shut. Has the size and
direction of Bitcoin's move between Friday's close and Monday's open told us anything
about where gold and stocks opened on Monday?

Both end in a verdict from a fixed rule. This is association, not cause: two markets can
react to the same news.
"""

import math
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats

from radar.analytics.correlation import interval

TURBULENT = "turbulent"
HORIZONS = (1, 5, 10)
# Sessions that must pass before a new episode can start, so episodes do not overlap.
MIN_GAP = 10
MIN_EPISODES = 15
MIN_WEEKENDS = 30
SIGNIFICANCE = 0.05
DRAWS = 2000
SEED = 7

SpillVerdict = Literal["spills over", "no measurable spillover", "not enough episodes"]
LinkVerdict = Literal["moves with", "moves against", "no measurable link", "not enough weekends"]


def episode_starts(labels: pd.Series, min_gap: int = MIN_GAP) -> np.ndarray:
    """Positions where the label turns turbulent, at least `min_gap` sessions apart."""
    turbulent = (labels == TURBULENT).to_numpy()
    known = labels.notna().to_numpy()
    starts: list[int] = []
    for t in range(1, len(turbulent)):
        entered = turbulent[t] and known[t - 1] and not turbulent[t - 1]
        if entered and (not starts or t - starts[-1] >= min_gap):
            starts.append(t)
    return np.array(starts, dtype=int)


def swing_after(returns: np.ndarray, steps: int) -> np.ndarray:
    """Average absolute daily return over the `steps` sessions after each one.

    NaN where the future is incomplete or has a missing return.
    """
    size = np.abs(returns)
    csum = np.concatenate([[0.0], np.cumsum(np.nan_to_num(size))])
    gaps = np.concatenate([[0], np.cumsum(np.isnan(size))])
    n = len(returns)
    out = np.full(n, np.nan)
    for t in range(n - steps):
        if gaps[t + steps + 1] - gaps[t + 1] == 0:
            out[t] = (csum[t + steps + 1] - csum[t + 1]) / steps
    return out


class Spillover(BaseModel):
    source: str
    target: str
    # Sessions after the episode began that the swings are averaged over.
    steps: int
    episodes: int
    # Average absolute daily move of the target after an episode, and on all other days.
    after: float | None = None
    usual: float | None = None
    # after / usual, with a 95% range from resampling the episodes.
    ratio: float | None = None
    ratio_low: float | None = None
    ratio_high: float | None = None
    # Chance of a ratio this large if episodes were ordinary days; adjusted for the family.
    p_value: float | None = None
    p_adjusted: float | None = None
    verdict: SpillVerdict = "not enough episodes"


def spillover(
    source: str,
    target: str,
    labels: pd.Series,
    target_returns: pd.Series,
    steps: int,
    *,
    min_episodes: int = MIN_EPISODES,
    draws: int = DRAWS,
) -> Spillover:
    """Whether the target swung more than usual after the source turned turbulent."""
    after = swing_after(target_returns.to_numpy(dtype=float), steps)
    starts = episode_starts(labels.reindex(target_returns.index))
    starts = starts[~np.isnan(after[starts])] if len(starts) else starts
    base = Spillover(source=source, target=target, steps=steps, episodes=len(starts))
    if len(starts) < min_episodes:
        return base
    episode = after[starts]
    other = np.ones(len(after), dtype=bool)
    other[starts] = False
    usual_days = after[other & ~np.isnan(after)]
    usual = float(usual_days.mean())
    ratio = float(episode.mean() / usual)

    rng = np.random.default_rng(SEED)
    resampled = rng.choice(episode, size=(draws, len(episode)), replace=True).mean(axis=1) / usual
    # What the average would be for the same number of ordinary days, picked at random.
    pool = after[~np.isnan(after)]
    ordinary = rng.choice(pool, size=(draws, len(episode)), replace=True).mean(axis=1)
    p_value = float((1 + (ordinary >= episode.mean()).sum()) / (draws + 1))
    return base.model_copy(
        update={
            "after": float(episode.mean()),
            "usual": usual,
            "ratio": ratio,
            "ratio_low": float(np.quantile(resampled, 0.025)),
            "ratio_high": float(np.quantile(resampled, 0.975)),
            "p_value": p_value,
        }
    )


def spill_verdict(row: Spillover, p_adjusted: float | None) -> Spillover:
    """`spills over` when swings were larger than usual beyond chance, after correction."""
    if row.ratio is None or p_adjusted is None:
        return row
    verdict: SpillVerdict = (
        "spills over" if p_adjusted < SIGNIFICANCE and row.ratio > 1 else "no measurable spillover"
    )
    return row.model_copy(update={"p_adjusted": p_adjusted, "verdict": verdict})


# --- weekend gaps ----------------------------------------------------------------------


class WeekendGap(BaseModel):
    symbol: str
    weekends: int
    # Correlation between Bitcoin's weekend move and this market's Monday opening gap.
    correlation: float | None = None
    low: float | None = None
    high: float | None = None
    # Opening gap per 1.0 of Bitcoin weekend move (a slope: 0.05 means 5% of the move).
    slope: float | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    # Average gap after Bitcoin's worst tenth of weekends, and after all weekends.
    gap_after_worst: float | None = None
    gap_usual: float | None = None
    worst_count: int = 0
    verdict: LinkVerdict = "not enough weekends"


def weekend_gap(
    symbol: str, bitcoin_move: pd.Series, gap: pd.Series, *, min_weekends: int = MIN_WEEKENDS
) -> WeekendGap:
    """How a market's Monday opening gap has related to Bitcoin's move while it was shut."""
    both = pd.concat([bitcoin_move, gap], axis=1, keys=["btc", "gap"]).dropna()
    n = len(both)
    if n < min_weekends:
        return WeekendGap(symbol=symbol, weekends=n)
    x = both["btc"].to_numpy(dtype=float)
    y = both["gap"].to_numpy(dtype=float)
    fit = stats.linregress(x, y)
    correlation = float(fit.rvalue)
    low, high = interval(correlation, n)
    worst = x <= np.quantile(x, 0.1)
    return WeekendGap(
        symbol=symbol,
        weekends=n,
        correlation=correlation,
        low=low,
        high=high,
        slope=float(fit.slope),
        p_value=float(fit.pvalue),
        gap_after_worst=float(y[worst].mean()),
        gap_usual=float(y.mean()),
        worst_count=int(worst.sum()),
    )


def link_verdict(row: WeekendGap, p_adjusted: float | None) -> WeekendGap:
    if row.correlation is None or p_adjusted is None or math.isnan(p_adjusted):
        return row
    verdict: LinkVerdict = (
        "no measurable link"
        if p_adjusted >= SIGNIFICANCE
        else "moves with"
        if row.correlation > 0
        else "moves against"
    )
    return row.model_copy(update={"p_adjusted": p_adjusted, "verdict": verdict})
