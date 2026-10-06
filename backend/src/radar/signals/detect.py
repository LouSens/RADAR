"""F7. Signal detectors: the rules that say "something changed today".

Each detector takes series indexed by day and returns the days its rule fired. A day's
signal may use only what was known by the end of that day; the callers pass regime
labels that were themselves produced walk-forward (`walk_forward_states`).

Pure functions. Loading and storing live in `pipelines/signals.py`.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from radar.analytics import event_study
from radar.models import regime

SignalType = Literal["regime_change", "abnormal_move", "sentiment_shock"]
TYPES: tuple[SignalType, ...] = ("regime_change", "abnormal_move", "sentiment_shock")

# The new state must be at least this probable for a change of state to count.
REGIME_PROBABILITY = 0.7
# An hourly move this many times the usual size for the current state is abnormal.
MOVE_MULTIPLE = 3.0
# Hourly returns needed in a state before its usual size is trusted.
MIN_HOURS = 200
# Sessions of history before the first walk-forward state, and sessions between refits.
MIN_TRAIN = 500
REFIT_EVERY = 63


@dataclass(frozen=True)
class Occurrence:
    """One day a rule fired. `variant` splits a type by direction."""

    day: pd.Timestamp
    variant: str
    detail: dict[str, Any] = field(default_factory=dict)


def walk_forward_states(
    observations: pd.DataFrame,
    *,
    min_train: int = MIN_TRAIN,
    step: int = REFIT_EVERY,
    n_init: int = 2,
    seed: int = 7,
) -> pd.DataFrame:
    """The market state of each day as it could have been known that day.

    Every `step` days the regime model is fitted again on all earlier days only, then
    used for the next `step` days. Each day's probabilities are filtered: they use that
    day and the days before it, never a later one. Columns: `label`, `probability`.
    """
    clean = observations.dropna(subset=list(regime.FEATURES))
    parts = []
    for start in range(min_train, len(clean), step):
        model = regime.fit(
            clean.iloc[:start], n_states=regime.DEFAULT_STATES, n_init=n_init, seed=seed
        )
        seen = clean.iloc[: start + step]
        probabilities = regime.filtered_probabilities(model, seen).iloc[start:]
        parts.append(
            pd.DataFrame(
                {
                    "label": probabilities.idxmax(axis=1),
                    "probability": probabilities.max(axis=1),
                }
            )
        )
    if not parts:
        return pd.DataFrame(
            {"label": pd.Series(dtype=object), "probability": pd.Series(dtype=float)}
        )
    return pd.concat(parts)


def regime_changes(states: pd.DataFrame, threshold: float = REGIME_PROBABILITY) -> list[Occurrence]:
    """Days on which the most probable state changed and the new one is probable enough.

    The state it changed from is the last one that itself passed the threshold, so a day
    of doubt in between does not turn one change into two.
    """
    found: list[Occurrence] = []
    settled: str | None = None
    for day, label, probability in zip(
        states.index, states["label"], states["probability"], strict=True
    ):
        if probability <= threshold:
            continue
        if settled is not None and label != settled:
            found.append(
                Occurrence(
                    day=pd.Timestamp(day),
                    variant=f"to {label}",
                    detail={"from": settled, "to": str(label), "probability": float(probability)},
                )
            )
        settled = str(label)
    return found


def usual_hourly_size(
    hourly: pd.Series, days: pd.Index, labels: pd.Series, min_hours: int = MIN_HOURS
) -> pd.Series:
    """For each hourly return, the usual size of an hourly return in the state the
    market was in going into that day, measured on earlier days only.

    `hourly` holds hourly log returns; `days` gives the day each belongs to; `labels`
    gives each day's state. The state going into a day is the day before's.
    """
    going_in = labels.shift(1)
    state = pd.Series(going_in.reindex(days).to_numpy(), index=hourly.index, dtype=object)
    frame = pd.DataFrame({"sq": hourly.to_numpy() ** 2, "state": state.to_numpy(), "day": days})
    frame = frame[frame["state"].notna() & np.isfinite(frame["sq"])]
    # Per state: sums over each day, then running totals up to the day before.
    by_day = frame.groupby(["state", "day"])["sq"].agg(["sum", "count"])
    earlier = by_day.groupby(level="state").cumsum() - by_day
    size = np.sqrt(earlier["sum"] / earlier["count"].where(earlier["count"] >= min_hours))
    keys = pd.MultiIndex.from_arrays([state.to_numpy(), days], names=["state", "day"])
    return pd.Series(size.reindex(keys).to_numpy(), index=hourly.index, dtype=float)


def abnormal_moves(
    hourly: pd.Series,
    days: pd.Index,
    labels: pd.Series,
    multiple: float = MOVE_MULTIPLE,
    min_hours: int = MIN_HOURS,
) -> list[Occurrence]:
    """Days with an hourly move beyond `multiple` times the usual size for the state.
    One per day: the first such hour."""
    size = usual_hourly_size(hourly, days, labels, min_hours)
    ratio = (hourly / size).to_numpy(dtype=float)
    found: list[Occurrence] = []
    seen: set[Any] = set()
    for position in np.flatnonzero(np.abs(ratio) > multiple).tolist():
        day = days[position]
        if day in seen:
            continue
        seen.add(day)
        found.append(
            Occurrence(
                day=pd.Timestamp(day),
                variant="up" if ratio[position] > 0 else "down",
                detail={
                    "hour": pd.Timestamp(hourly.index[position]).isoformat(),
                    "move": float(hourly.iloc[position]),
                    "usual": float(size.iloc[position]),
                    "multiple": float(abs(ratio[position])),
                },
            )
        )
    return found


def sentiment_shocks(tone: pd.Series, threshold: float = event_study.THRESHOLD) -> list[Occurrence]:
    """Days whose news tone is more than `threshold` standard deviations from the
    average of the year before. Days within three of the last shock belong to it."""
    z = event_study.zscore(tone)
    return [
        Occurrence(
            day=pd.Timestamp(z.index[event.position]),
            variant="positive" if event.sign > 0 else "negative",
            detail={"z": float(z.iloc[event.position]), "tone": float(tone.iloc[event.position])},
        )
        for event in event_study.find_events(z, threshold)
    ]
