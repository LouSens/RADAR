"""F6. Portfolio simulation: a block bootstrap of the holdings' joint daily returns.

A simulated future is built by gluing together short runs of real past days. Each run
is taken whole, for every holding at once, so two things in the record survive: how the
holdings moved against each other on the same day, and the way rough days cluster.

The holdings are left alone along a path (nothing is rebalanced), and whatever the
weights leave over is cash, which does not move.

No lookahead: a simulation for day `t` may only be given returns from days up to `t`.
`backtest` checks past ranges that way, each one built from the days before it.
"""

import numpy as np
from pydantic import BaseModel

from radar.models import simulator

MODEL_VERSION = "portfolio-bootstrap-1"
DEFAULT_PATHS = 10_000
# Sessions in each run of real days glued into a path: two trading weeks.
BLOCK = 10
HORIZONS = (30, 90)
# Sessions of joint history needed before a range is drawn.
MIN_DAYS = 250
# Paths for each past range in the backtest; fewer than a live run, to keep it quick.
BACKTEST_PATHS = 2_000
# Changes in value the chances are worked out for: -50% to +50% in steps of one point.
CHANGES = tuple(round(c / 100, 2) for c in range(-50, 51))


def sample_days(
    n_days: int, horizon: int, n_paths: int, block: int, rng: np.random.Generator
) -> np.ndarray:
    """Row numbers of past days for each path, in runs of `block` consecutive days."""
    block = max(1, min(block, n_days))
    n_blocks = -(-horizon // block)
    starts = rng.integers(0, n_days - block + 1, size=(n_paths, n_blocks))
    days = starts[:, :, None] + np.arange(block)
    picked: np.ndarray = days.reshape(n_paths, -1)[:, :horizon]
    return picked


def simulate(
    returns: np.ndarray,
    weights: np.ndarray,
    horizon: int,
    n_paths: int = DEFAULT_PATHS,
    block: int = BLOCK,
    seed: int = 0,
    scale: float = 1.0,
) -> np.ndarray:
    """Cumulative log change in the portfolio's value at the end of each day ahead.

    `returns` holds daily log returns, one row per past day and one column per holding;
    `weights` are the holdings' shares of the whole now. `scale` widens every path, for
    holdings too new to be in `returns` (decision 043). Shape: (n_paths, horizon).
    """
    rng = np.random.default_rng(seed)
    days = sample_days(len(returns), horizon, n_paths, block, rng)
    growth = np.exp(np.cumsum(returns[days], axis=1))
    value = (1.0 - float(weights.sum())) + growth @ weights
    cumulative: np.ndarray = np.log(value) * scale
    return cumulative


class Chance(BaseModel):
    """How often the simulated value was at or past one change from today."""

    change: float
    # At the end of the horizon, the value is below today's by at least this change
    # (for a fall) or above it by at least this change (for a rise).
    ends_beyond: float
    # The value closes at or past it on any day in the horizon.
    touches: float


def chances(cumulative: np.ndarray, steps: int) -> list[Chance]:
    paths = cumulative[:, :steps]
    terminal = np.sort(paths[:, -1])
    lowest = np.sort(np.minimum(paths.min(axis=1), 0.0))
    highest = np.sort(np.maximum(paths.max(axis=1), 0.0))
    n = len(terminal)
    result = []
    for change in CHANGES:
        level = float(np.log1p(change)) if change > -1 else -np.inf
        if change < 0:
            ends = np.searchsorted(terminal, level, side="right") / n
            touched = np.searchsorted(lowest, level, side="right") / n
        else:
            ends = 1.0 - np.searchsorted(terminal, level, side="left") / n
            touched = 1.0 - np.searchsorted(highest, level, side="left") / n
        result.append(Chance(change=change, ends_beyond=float(ends), touches=float(touched)))
    return result


class PastRange(BaseModel):
    """One range drawn in the past from earlier days only, and what then happened."""

    # Row number of the first day the range looked ahead from.
    origin: int
    realised: float
    # Level of each interval to its low and high, as cumulative log changes.
    bounds: dict[str, tuple[float, float]]


class Coverage(BaseModel):
    """How often past ranges of one stated level held what happened."""

    level: float
    n: int
    inside: int


def realised_change(returns: np.ndarray, weights: np.ndarray) -> float:
    """The log change in value of holdings left alone through these days."""
    growth = np.exp(returns.sum(axis=0))
    return float(np.log((1.0 - float(weights.sum())) + growth @ weights))


def backtest(
    returns: np.ndarray,
    weights: np.ndarray,
    horizon: int,
    *,
    min_days: int = MIN_DAYS,
    n_paths: int = BACKTEST_PATHS,
    block: int = BLOCK,
    seed: int = 0,
) -> list[PastRange]:
    """Draw a range at each past origin from the days before it, then see what happened.

    Origins are a full horizon apart, so no two outcomes share a day.
    """
    records = []
    for origin in range(min_days, len(returns) - horizon + 1, horizon):
        paths = simulate(returns[:origin], weights, horizon, n_paths, block, seed + origin)
        terminal = paths[:, -1]
        records.append(
            PastRange(
                origin=origin,
                realised=realised_change(returns[origin : origin + horizon], weights),
                bounds={
                    f"{level:g}": simulator.interval_bounds(terminal, level)
                    for level in simulator.INTERVALS
                },
            )
        )
    return records


def normal_backtest(
    returns: np.ndarray, weights: np.ndarray, horizon: int, *, min_days: int = MIN_DAYS
) -> list[PastRange]:
    """The baseline, checked at the same origins: a random walk whose steady drift and
    spread are those of the mix's daily returns on the days before each origin."""
    daily = np.log1p(np.expm1(returns) @ weights)
    records = []
    for origin in range(min_days, len(returns) - horizon + 1, horizon):
        bounds = {}
        for level in simulator.INTERVALS:
            tail = (1.0 - level) / 2.0
            low, high = simulator.gbm_quantiles(
                daily[:origin], horizon, np.array([tail, 1.0 - tail])
            )
            bounds[f"{level:g}"] = (float(low), float(high))
        records.append(
            PastRange(
                origin=origin,
                realised=realised_change(returns[origin : origin + horizon], weights),
                bounds=bounds,
            )
        )
    return records


def coverage(records: list[PastRange]) -> list[Coverage]:
    result = []
    for level in simulator.INTERVALS:
        key = f"{level:g}"
        inside = sum(1 for r in records if r.bounds[key][0] <= r.realised <= r.bounds[key][1])
        result.append(Coverage(level=level, n=len(records), inside=inside))
    return result


class Horizon(BaseModel):
    # The spread of the value `steps` sessions ahead, in money.
    summary: simulator.HorizonSummary
    chances: list[Chance]
    coverage: list[Coverage]
    # The same check for a plain constant-volatility random walk, to compare with.
    baseline_coverage: list[Coverage] = []


class Simulation(BaseModel):
    model_version: str
    n_paths: int
    block: int
    # Past sessions the runs of days were drawn from.
    n_days: int
    start_value: float
    # Above one when every path was widened for newer holdings.
    scale: float
    # Value quantiles at the end of each day, to the longest horizon. Day 0 is today.
    fan: dict[str, list[float]]
    horizons: list[Horizon]


def run(
    returns: np.ndarray,
    weights: np.ndarray,
    value: float,
    *,
    scale: float = 1.0,
    n_paths: int = DEFAULT_PATHS,
    block: int = BLOCK,
    seed: int = 0,
) -> Simulation | None:
    """The simulation as stored, or None when there is too little joint history."""
    if len(returns) < MIN_DAYS:
        return None
    cumulative = simulate(returns, weights, max(HORIZONS), n_paths, block, seed, scale)
    return Simulation(
        model_version=MODEL_VERSION,
        n_paths=n_paths,
        block=block,
        n_days=len(returns),
        start_value=value,
        scale=scale,
        fan=simulator.fan(cumulative, value),
        horizons=[
            Horizon(
                summary=simulator.summarise(cumulative, steps, value),
                chances=chances(cumulative, steps),
                coverage=coverage(backtest(returns, weights, steps, block=block, seed=seed)),
                baseline_coverage=coverage(normal_backtest(returns, weights, steps)),
            )
            for steps in HORIZONS
        ],
    )
