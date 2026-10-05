"""F4. Sentiment versus price: does news tone lead price, follow it, or neither?

Two measurements on daily data, and one rule that turns them into a verdict.

- Event study. An event is a day whose news tone was far from its own recent normal
  (more than 2 standard deviations, judged against the trailing year only). For each
  event the price path is followed from the day before to three days after, with the
  asset's usual daily drift removed, and averaged over events.
- Lead-lag. The correlation between a day's tone and the return `k` days later, for `k`
  from -5 to +5. Positive `k` means tone came first.

A "day" is a UTC day for crypto and a trading session for stocks, so for crypto the
window is 24 hours before to 72 hours after. No lookahead: an event is identified from
that day and earlier days only, and the drift removed is measured before the window.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats

from radar.models import evidence

THRESHOLD = 2.0
ZSCORE_WINDOW = 365
ZSCORE_MIN = 60
MERGE_DAYS = 3
OFFSETS = (-1, 0, 1, 2, 3)
DRIFT_DAYS = 90
MAX_LAG = 5
MIN_EVENTS = 30
SIGNIFICANCE = 0.05

VERDICTS = (
    "sentiment leads price",
    "price leads sentiment",
    "no measurable relationship",
    "not enough events",
)


def zscore(
    sentiment: pd.Series, window: int = ZSCORE_WINDOW, minimum: int = ZSCORE_MIN
) -> pd.Series:
    """How unusual each day's tone is against the days before it (never including it)."""
    earlier = sentiment.shift(1)
    mean = earlier.rolling(window, min_periods=minimum).mean()
    std = earlier.rolling(window, min_periods=minimum).std()
    return ((sentiment - mean) / std.where(std > 0)).rename("z")


@dataclass(frozen=True)
class Event:
    position: int  # row of the event day in the series
    sign: int  # +1 for unusually positive tone, -1 for unusually negative


def find_events(z: pd.Series, threshold: float = THRESHOLD, merge: int = MERGE_DAYS) -> list[Event]:
    """Days beyond the threshold. One that falls within `merge` days of the event before
    it belongs to that event and is not counted again."""
    values = z.to_numpy(dtype=float)
    events: list[Event] = []
    for position in np.flatnonzero(np.abs(values) > threshold).tolist():
        if events and position - events[-1].position < merge:
            continue
        events.append(Event(position=position, sign=1 if values[position] > 0 else -1))
    return events


def abnormal_paths(
    returns: pd.Series,
    positions: list[int],
    offsets: tuple[int, ...] = OFFSETS,
    drift_days: int = DRIFT_DAYS,
) -> np.ndarray:
    """Cumulative return around each day in `positions`, with the usual drift removed.

    One row per day, one column per offset. The drift is the average daily return over
    the `drift_days` days that end before the window opens. Rows without a full window
    or enough earlier history are left out.
    """
    values = returns.to_numpy(dtype=float)
    first, last = min(offsets), max(offsets)
    rows = []
    for position in positions:
        start, end = position + first, position + last
        history = values[max(0, start - drift_days) : start]
        if start < 0 or end >= len(values) or len(history) < drift_days // 2:
            continue
        window = values[start : end + 1]
        if np.isnan(window).any():
            continue
        rows.append(np.cumsum(window - np.nanmean(history)))
    return np.array(rows).reshape(-1, len(offsets))


class AveragePath(BaseModel):
    """The average price path around one kind of event."""

    n: int
    offsets: list[int]
    mean: list[float]
    # 90% band from resampling the events.
    low: list[float]
    high: list[float]


def average_path(
    paths: np.ndarray,
    offsets: tuple[int, ...] = OFFSETS,
    draws: int = 2000,
    seed: int = 0,
) -> AveragePath:
    if len(paths) == 0:
        return AveragePath(n=0, offsets=list(offsets), mean=[], low=[], high=[])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(paths), size=(draws, len(paths)))
    resampled = paths[picks].mean(axis=1)
    low, high = np.quantile(resampled, [0.05, 0.95], axis=0)
    return AveragePath(
        n=len(paths),
        offsets=list(offsets),
        mean=paths.mean(axis=0).tolist(),
        low=low.tolist(),
        high=high.tolist(),
    )


def matched_positions(
    events: list[Event], labels: np.ndarray | None, n_days: int, seed: int = 0
) -> list[int]:
    """One random non-event day for each event, in the same market regime where known."""
    rng = np.random.default_rng(seed)
    taken = {e.position for e in events}
    free = np.array([i for i in range(n_days) if i not in taken])
    picks = []
    for event in events:
        pool = free
        if labels is not None:
            same = free[labels[free] == labels[event.position]]
            if len(same):
                pool = same
        picks.append(int(rng.choice(pool)))
    return picks


class LagCorrelation(BaseModel):
    lag: int
    correlation: float
    n: int
    significant: bool
    # The chance of a correlation this large if there were no link at all.
    p_value: float | None = None


def lead_lag(
    sentiment: pd.Series, returns: pd.Series, max_lag: int = MAX_LAG
) -> list[LagCorrelation]:
    """Correlation of tone on day `t` with the return on day `t + lag`.

    A lag is marked significant when its correlation is beyond what chance would give,
    allowing for the five lags tested on each side (Bonferroni).
    """
    frame = pd.DataFrame({"s": sentiment, "r": returns})
    critical = stats.norm.ppf(1.0 - SIGNIFICANCE / (2 * max_lag))
    result = []
    for lag in range(-max_lag, max_lag + 1):
        pair = pd.DataFrame({"s": frame["s"], "r": frame["r"].shift(-lag)}).dropna()
        n = len(pair)
        if n < 10 or pair["s"].std() == 0 or pair["r"].std() == 0:
            result.append(LagCorrelation(lag=lag, correlation=0.0, n=n, significant=False))
            continue
        correlation = float(pair["s"].corr(pair["r"]))
        result.append(
            LagCorrelation(
                lag=lag,
                correlation=correlation,
                n=n,
                p_value=float(2.0 * stats.norm.sf(abs(correlation) * np.sqrt(n))),
                significant=bool(abs(correlation) > critical / np.sqrt(n)),
            )
        )
    return result


def verdict(n_events: int, lags: list[LagCorrelation], minimum: int = MIN_EVENTS) -> str:
    """The rule behind the label shown in the app.

    With fewer than `minimum` events there is no verdict. Otherwise take the strongest
    significant correlation where tone came first (lags 1 to 5) and the strongest where
    price came first (lags -5 to -1). If neither side has one, there is no measurable
    relationship; if only one does, or one is stronger, that side leads. The same-day
    correlation is not used, because it cannot say which came first.
    """
    if n_events < minimum:
        return "not enough events"
    tone_first = max((abs(c.correlation) for c in lags if c.lag > 0 and c.significant), default=0.0)
    price_first = max(
        (abs(c.correlation) for c in lags if c.lag < 0 and c.significant), default=0.0
    )
    if tone_first == 0.0 and price_first == 0.0:
        return "no measurable relationship"
    return "sentiment leads price" if tone_first > price_first else "price leads sentiment"


def correct_family(studies: list["EventStudy"], minimum: int = MIN_EVENTS) -> list["EventStudy"]:
    """Re-judge a group of studies run together, allowing for how many tests that is.

    One market's news is tested overall and once per topic, eleven lags each. With that
    many tests a few would look significant by luck alone. The p-values of every lag in
    every study are adjusted together (Benjamini-Hochberg), significance is taken from
    the adjusted values, and each verdict is worked out again.
    """
    flat = [lag.p_value for study in studies for lag in study.lags]
    adjusted = iter(evidence.benjamini_hochberg(flat))
    corrected = []
    for study in studies:
        lags = [
            lag.model_copy(
                update={"significant": q is not None and q < evidence.FALSE_DISCOVERY_RATE}
            )
            for lag, q in zip(study.lags, adjusted, strict=False)
        ]
        corrected.append(
            study.model_copy(
                update={"lags": lags, "verdict": verdict(study.n_events, lags, minimum)}
            )
        )
    return corrected


class EventStudy(BaseModel):
    verdict: str
    n_events: int
    n_positive: int
    n_negative: int
    n_days: int
    first_day: str | None
    last_day: str | None
    positive: AveragePath
    negative: AveragePath
    # The same paths around random days in the same regimes: what no effect looks like.
    baseline: AveragePath
    lags: list[LagCorrelation]


def study(
    sentiment: pd.Series, returns: pd.Series, regimes: pd.Series | None = None, seed: int = 0
) -> EventStudy:
    """Run both measurements on aligned daily series and give the verdict.

    `sentiment` and `returns` share one index of days. `regimes`, if given, holds the
    regime label of each day and is used to choose comparable random days.
    """
    frame = pd.DataFrame({"s": sentiment, "r": returns})
    frame = frame.loc[frame["s"].first_valid_index() :] if frame["s"].notna().any() else frame
    events = find_events(zscore(frame["s"]))
    labels = None
    if regimes is not None:
        labels = regimes.reindex(frame.index).fillna("unknown").to_numpy()
    positive = abnormal_paths(frame["r"], [e.position for e in events if e.sign > 0])
    negative = abnormal_paths(frame["r"], [e.position for e in events if e.sign < 0])
    random_days = matched_positions(events, labels, len(frame), seed) if events else []
    baseline = abnormal_paths(frame["r"], random_days)
    lags = lead_lag(frame["s"], frame["r"])
    days = pd.DatetimeIndex(frame.index)
    return EventStudy(
        verdict=verdict(len(events), lags),
        n_events=len(events),
        n_positive=sum(e.sign > 0 for e in events),
        n_negative=sum(e.sign < 0 for e in events),
        n_days=int(frame["s"].notna().sum()),
        first_day=str(days[0].date()) if len(days) else None,
        last_day=str(days[-1].date()) if len(days) else None,
        positive=average_path(positive, seed=seed),
        negative=average_path(negative, seed=seed + 1),
        baseline=average_path(baseline, seed=seed + 2),
        lags=lags,
    )
