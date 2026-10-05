"""Walk-forward calibration of the outcome simulator, and its conformal adjustment.

For every past day the simulator is run exactly as it would have been run then: with a
regime model fitted on earlier days only, and returns up to that day only. Its ranges are
then scored against what actually happened. This is what lets the app say "the 80% range
has contained the outcome in X% of N past cases".

The conformal adjustment (adaptive conformal inference) widens or narrows each range using
only the hits and misses of earlier forecasts whose outcomes were already known.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel

from radar.models import regime, simulator

# Trading steps for each horizon in days. Stocks have about 5 sessions a week.
HORIZON_STEPS: dict[str, dict[int, int]] = {
    "crypto": {1: 1, 7: 7, 30: 30},
    "stock": {1: 1, 7: 5, 30: 21},
}
QUANTILE_LEVELS = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
INTERVALS = simulator.INTERVALS
TRAILING_YEAR = 365
# How fast the conformal adjustment reacts to a miss.
CONFORMAL_RATE = 0.02


@dataclass
class ForecastSet:
    """Every walk-forward forecast for one horizon."""

    steps: int
    origins: np.ndarray  # row position of each forecast day in the observations
    samples: np.ndarray  # simulated cumulative log returns, shape (origins, paths), sorted
    realised: np.ndarray  # what actually happened; NaN where the future is not known yet
    baseline: np.ndarray  # baseline quantiles at QUANTILE_LEVELS, shape (origins, levels)


def walk_forward_forecasts(
    observations: pd.DataFrame,
    steps: tuple[int, ...],
    *,
    min_train: int = 500,
    refit_every: int = 63,
    n_paths: int = 2000,
    seed: int = 11,
    n_init: int = 2,
) -> dict[int, ForecastSet]:
    """Run the simulator for every day after the first `min_train`, with no lookahead."""
    clean = observations.dropna(subset=list(regime.FEATURES))
    returns = clean["ret"].to_numpy(dtype=float)
    n = len(clean)
    longest = max(steps)
    origins: list[int] = []
    samples: dict[int, list[np.ndarray]] = {s: [] for s in steps}
    baseline: dict[int, list[np.ndarray]] = {s: [] for s in steps}

    for start in range(min_train, n, refit_every):
        end = min(start + refit_every, n)
        model = regime.fit(clean.iloc[:start], n_init=n_init, seed=seed)
        # Filtered, so the label of day t depends on days up to t only.
        probabilities = regime.filtered_probabilities(model, clean.iloc[:end]).to_numpy()
        labels = probabilities.argmax(axis=1)
        transition = np.array(model.transition)
        for t in range(start, end):
            pools, _ = simulator.build_pools(returns[: t + 1], labels[: t + 1], model.n_states)
            inputs = simulator.SimulationInputs(
                start_probabilities=probabilities[t],
                transition=transition,
                pools=pools,
                all_returns=returns[: t + 1],
            )
            cumulative = simulator.cumulative_returns(
                simulator.simulate(inputs, longest, n_paths=n_paths, seed=seed + t)
            )
            trailing = returns[max(0, t + 1 - TRAILING_YEAR) : t + 1]
            origins.append(t)
            for s in steps:
                samples[s].append(np.sort(cumulative[:, s - 1]).astype(np.float32))
                baseline[s].append(simulator.gbm_quantiles(trailing, s, QUANTILE_LEVELS))

    positions = np.array(origins)
    csum = np.concatenate([[0.0], np.cumsum(returns)])
    result = {}
    for s in steps:
        ahead = positions + s
        realised = np.full(len(positions), np.nan)
        known = ahead < n
        realised[known] = csum[ahead[known] + 1] - csum[positions[known] + 1]
        result[s] = ForecastSet(
            steps=s,
            origins=positions,
            samples=np.array(samples[s]),
            realised=realised,
            baseline=np.array(baseline[s]),
        )
    return result


def _quantiles(samples: np.ndarray, levels: np.ndarray) -> np.ndarray:
    """Per-forecast quantiles. `levels` may be one value per forecast or shared."""
    if levels.ndim == 0:
        result: np.ndarray = np.quantile(samples, float(levels), axis=1)
        return result
    index = np.clip(levels, 0.0, 1.0) * (samples.shape[1] - 1)
    low = np.floor(index).astype(int)
    high = np.minimum(low + 1, samples.shape[1] - 1)
    weight = index - low
    rows = np.arange(len(samples))
    mixed: np.ndarray = samples[rows, low] * (1 - weight) + samples[rows, high] * weight
    return mixed


def raw_hits(forecasts: ForecastSet, level: float) -> np.ndarray:
    """Whether each outcome fell inside the simulator's own range. NaN where unknown."""
    tail = (1.0 - level) / 2.0
    low = _quantiles(forecasts.samples, np.array(tail))
    high = _quantiles(forecasts.samples, np.array(1.0 - tail))
    hits = ((forecasts.realised >= low) & (forecasts.realised <= high)).astype(float)
    hits[np.isnan(forecasts.realised)] = np.nan
    return hits


def conformal_hits(
    forecasts: ForecastSet, level: float, rate: float = CONFORMAL_RATE
) -> tuple[np.ndarray, float]:
    """Hits of the conformally adjusted range, and the adjustment to use next.

    The range for each forecast uses a miss rate tuned on earlier forecasts only: after a
    miss it widens, after a hit it narrows slightly. A forecast `steps` days ahead only
    learns from forecasts made at least `steps` days before it, because later ones have
    no outcome yet. Returns the hit record and the miss rate for the next live forecast.
    """
    target = 1.0 - level
    alpha = target
    n = len(forecasts.origins)
    hits = np.full(n, np.nan)
    for i in range(n):
        bounded = float(np.clip(alpha, 0.001, 0.999))
        row = forecasts.samples[i : i + 1]
        low = _quantiles(row, np.array([bounded / 2.0]))[0]
        high = _quantiles(row, np.array([1.0 - bounded / 2.0]))[0]
        if not np.isnan(forecasts.realised[i]):
            hits[i] = float(low <= forecasts.realised[i] <= high)
        # The outcome that becomes known before the next forecast is made.
        learned = i + 1 - forecasts.steps
        if learned >= 0 and not np.isnan(hits[learned]):
            alpha += rate * (target - (1.0 - hits[learned]))
    return hits, float(np.clip(alpha, 0.001, 0.999))


class CalibrationRow(BaseModel):
    horizon_days: int
    steps: int
    nominal: float
    # Share of past ranges that contained the outcome.
    empirical: float
    empirical_conformal: float
    n: int
    # The miss rate to ask the simulator for next, so that long-run coverage is nominal.
    conformal_miss_rate: float
    # Average pinball loss over the quantile levels; lower is better.
    pinball_model: float
    pinball_baseline: float
    first_origin: str
    last_origin: str


def evaluate(
    forecasts: dict[int, ForecastSet], horizon_of: dict[int, int], index: pd.DatetimeIndex
) -> list[CalibrationRow]:
    """Coverage and pinball loss for every horizon and range. `horizon_of` maps steps to days."""
    rows = []
    for steps, forecast in forecasts.items():
        known = ~np.isnan(forecast.realised)
        if not known.any():
            continue
        realised = forecast.realised[known]
        model_loss = []
        baseline_loss = []
        for column, level in enumerate(QUANTILE_LEVELS):
            predicted = _quantiles(forecast.samples[known], np.array(level))
            model_loss.append(simulator.pinball_loss(realised, predicted, float(level)))
            baseline_loss.append(
                simulator.pinball_loss(realised, forecast.baseline[known, column], float(level))
            )
        origins = index[forecast.origins[known]]
        for level in INTERVALS:
            raw = raw_hits(forecast, level)
            adjusted, miss_rate = conformal_hits(forecast, level)
            rows.append(
                CalibrationRow(
                    horizon_days=horizon_of[steps],
                    steps=steps,
                    nominal=level,
                    empirical=float(np.nanmean(raw)),
                    empirical_conformal=float(np.nanmean(adjusted)),
                    n=int(known.sum()),
                    conformal_miss_rate=miss_rate,
                    pinball_model=float(np.mean(model_loss)),
                    pinball_baseline=float(np.mean(baseline_loss)),
                    first_origin=str(origins[0].date()),
                    last_origin=str(origins[-1].date()),
                )
            )
    return rows
