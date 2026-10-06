"""Macro drivers (spec F8): which outside forces a market has been moving with.

A market's daily return is regressed on the daily returns of the driver funds (stocks,
the dollar, long bonds, inflation-linked bonds, expected stock volatility) over a
trailing window. Ridge regularisation, because the drivers move with each other.

Each driver is put on the same scale inside the window, so a coefficient reads as: on a
day when this driver moved by one of its own typical days, the market moved this much,
other drivers held still.

No lookahead. A window ending at session `t` uses returns up to `t`, and its scaling is
fitted on that window alone. The out-of-sample score fits on a window and predicts the
sessions after it.
"""

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

MODEL_VERSION = "drivers-1"
WINDOWS = (90, 250)
# Strength of the ridge penalty, on standardised drivers.
ALPHA = 5.0
BOOTSTRAPS = 500
# Sessions predicted after each fit when scoring out of sample.
TEST_BLOCK = 20
SEED = 11

Verdict = Literal["moves with", "moves against", "no measurable link"]


def _fit(
    x: np.ndarray, y: np.ndarray, alpha: float = ALPHA
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Ridge on drivers standardised within the sample. Returns the coefficients, the
    intercept, and the mean and spread used for scaling."""
    mean = x.mean(axis=0)
    spread = x.std(axis=0)
    spread[spread == 0] = 1.0
    z = (x - mean) / spread
    centre = y.mean()
    gram = z.T @ z + alpha * np.eye(z.shape[1])
    coefficients = np.linalg.solve(gram, z.T @ (y - centre))
    return coefficients, float(centre), mean, spread


def _predict(x: np.ndarray, fitted: tuple[np.ndarray, float, np.ndarray, np.ndarray]) -> np.ndarray:
    coefficients, centre, mean, spread = fitted
    return np.asarray(centre + ((x - mean) / spread) @ coefficients, dtype=float)


def _r_squared(y: np.ndarray, predicted: np.ndarray, reference: float | np.ndarray) -> float:
    total = float(((y - reference) ** 2).sum())
    return float("nan") if total == 0 else 1.0 - float(((y - predicted) ** 2).sum()) / total


class DriverReading(BaseModel):
    symbol: str
    # The market's move on a day the driver moved by one typical day of its own.
    coefficient: float
    low: float
    high: float
    verdict: Verdict


class DriverPoint(BaseModel):
    day: date
    r_squared: float
    coefficients: list[float]


class OutOfSample(BaseModel):
    """Fit on a window, predict the next sessions, repeat. Scored on every prediction."""

    n_days: int
    r_squared: float
    baseline_r_squared: float
    first_day: date
    last_day: date


class WindowResult(BaseModel):
    window: int
    drivers: list[DriverReading]
    # Share of the market's day-to-day variance the drivers account for in this window.
    r_squared: float
    first_day: date
    last_day: date
    # The same reading at earlier dates, to show how it has moved.
    history: list[DriverPoint]
    out_of_sample: OutOfSample | None
    baseline: str
    # The driver with the largest measurable coefficient, or null when none is measurable.
    strongest: str | None


def current(
    y: np.ndarray, x: np.ndarray, symbols: list[str], *, bootstraps: int = BOOTSTRAPS
) -> tuple[list[DriverReading], float]:
    """Coefficients for one window with 95% ranges from resampling its days."""
    fitted = _fit(x, y)
    rng = np.random.default_rng(SEED)
    picks = rng.integers(0, len(y), size=(bootstraps, len(y)))
    samples = np.array([_fit(x[rows], y[rows])[0] for rows in picks])
    low = np.quantile(samples, 0.025, axis=0)
    high = np.quantile(samples, 0.975, axis=0)
    readings = []
    for i, symbol in enumerate(symbols):
        verdict: Verdict = (
            "moves with" if low[i] > 0 else "moves against" if high[i] < 0 else "no measurable link"
        )
        readings.append(
            DriverReading(
                symbol=symbol,
                coefficient=float(fitted[0][i]),
                low=float(low[i]),
                high=float(high[i]),
                verdict=verdict,
            )
        )
    return readings, _r_squared(y, _predict(x, fitted), float(y.mean()))


def walk_forward(
    y: np.ndarray, x: np.ndarray, baseline: np.ndarray, window: int, block: int = TEST_BLOCK
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Out-of-sample predictions of the full model and of the baseline driver alone.

    Returns the positions predicted and the two sets of predictions. The reference a
    prediction must beat is the mean of its own training window, also returned here as
    part of scoring by the caller.
    """
    positions: list[int] = []
    model: list[float] = []
    simple: list[float] = []
    for end in range(window, len(y) - 1, block):
        train = slice(end - window, end)
        test = slice(end, min(end + block, len(y)))
        model.extend(_predict(x[test], _fit(x[train], y[train])))
        simple.extend(_predict(baseline[test], _fit(baseline[train], y[train])))
        positions.extend(range(test.start, test.stop))
    return np.array(positions, dtype=int), np.array(model), np.array(simple)


def analyse(
    returns: pd.DataFrame,
    target: str,
    drivers: list[str],
    baseline: str,
    window: int,
    *,
    bootstraps: int = BOOTSTRAPS,
    history_step: int = 5,
    history_points: int = 150,
) -> WindowResult | None:
    """Everything shown for one market and one window length."""
    frame = returns[[target, *drivers]].dropna()
    if len(frame) < window + 1:
        return None
    y = frame[target].to_numpy(dtype=float)
    x = frame[drivers].to_numpy(dtype=float)
    days = pd.DatetimeIndex(frame.index)
    n = len(frame)

    readings, r_squared = current(y[n - window :], x[n - window :], drivers, bootstraps=bootstraps)

    history = []
    ends = list(range(n, window - 1, -history_step))[:history_points][::-1]
    for end in ends:
        fitted = _fit(x[end - window : end], y[end - window : end])
        segment = y[end - window : end]
        history.append(
            DriverPoint(
                day=days[end - 1].date(),
                r_squared=_r_squared(
                    segment, _predict(x[end - window : end], fitted), float(segment.mean())
                ),
                coefficients=[float(c) for c in fitted[0]],
            )
        )

    column = drivers.index(baseline)
    positions, model, simple = walk_forward(y, x, x[:, [column]], window)
    out_of_sample = None
    if len(positions) >= TEST_BLOCK:
        # Each prediction is judged against the mean of the window it was fitted on.
        csum = np.concatenate([[0.0], np.cumsum(y)])
        starts = ((positions - window) // TEST_BLOCK) * TEST_BLOCK + window
        reference = (csum[starts] - csum[starts - window]) / window
        out_of_sample = OutOfSample(
            n_days=len(positions),
            r_squared=_r_squared(y[positions], model, reference),
            baseline_r_squared=_r_squared(y[positions], simple, reference),
            first_day=days[positions[0]].date(),
            last_day=days[positions[-1]].date(),
        )

    measurable = [r for r in readings if r.verdict != "no measurable link"]
    strongest = max(measurable, key=lambda r: abs(r.coefficient)).symbol if measurable else None
    return WindowResult(
        window=window,
        drivers=readings,
        r_squared=r_squared,
        first_day=days[n - window].date(),
        last_day=days[-1].date(),
        history=history,
        out_of_sample=out_of_sample,
        baseline=baseline,
        strongest=strongest,
    )
