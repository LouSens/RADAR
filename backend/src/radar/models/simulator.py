"""F2. Outcome simulator: regime-switching Monte Carlo with bootstrapped returns.

Each simulated future starts from today's regime probabilities. For every day ahead it
first draws the next regime from the regime model's transition matrix, then draws that
day's return from the real returns seen in that regime. Sampling real returns keeps the
fat tails that a normal distribution would miss.

No lookahead: a simulation for date `t` may only be given returns and regime labels from
days up to `t`. The functions here are pure; callers are responsible for what they pass.
"""

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel

MODEL_VERSION = "simulator-rsmc-1"
DEFAULT_PATHS = 10_000
# A regime needs at least this many past returns to be sampled on its own.
MIN_POOL = 20
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
INTERVALS = (0.5, 0.8, 0.95)


@dataclass(frozen=True)
class SimulationInputs:
    """Everything a run depends on. The same inputs and seed give the same paths."""

    start_probabilities: np.ndarray  # today's filtered regime probabilities
    transition: np.ndarray  # regime transition matrix
    pools: tuple[np.ndarray, ...]  # past daily log returns seen in each regime
    all_returns: np.ndarray  # every past daily log return, the fallback pool


def build_pools(
    returns: np.ndarray, labels: np.ndarray, n_states: int
) -> tuple[tuple[np.ndarray, ...], list[int]]:
    """Group past returns by the regime each day was in.

    `labels` holds the regime index of each day, from filtered probabilities. A regime
    with fewer than `MIN_POOL` returns falls back to all returns; the indexes of such
    regimes are returned so the caller can say so.
    """
    pools: list[np.ndarray] = []
    thin: list[int] = []
    for state in range(n_states):
        pool = returns[labels == state]
        if len(pool) < MIN_POOL:
            thin.append(state)
            pool = returns
        pools.append(pool)
    return tuple(pools), thin


def simulate(
    inputs: SimulationInputs, horizon: int, n_paths: int = DEFAULT_PATHS, seed: int = 0
) -> np.ndarray:
    """Simulate daily log returns. Returns an array of shape (n_paths, horizon)."""
    rng = np.random.default_rng(seed)
    n_states = len(inputs.start_probabilities)
    cumulative = np.cumsum(inputs.transition, axis=1)
    cumulative[:, -1] = 1.0  # guard against rounding
    start = np.cumsum(inputs.start_probabilities)
    start[-1] = 1.0
    state = np.searchsorted(start, rng.random(n_paths), side="right")
    returns = np.empty((n_paths, horizon))
    for day in range(horizon):
        draws = rng.random(n_paths)
        state = (draws[:, None] > cumulative[state]).sum(axis=1)
        picks = rng.random(n_paths)
        for k in range(n_states):
            mask = state == k
            if mask.any():
                pool = inputs.pools[k]
                returns[mask, day] = pool[(picks[mask] * len(pool)).astype(int)]
    return returns


def cumulative_returns(daily: np.ndarray) -> np.ndarray:
    """Cumulative log return at the end of each simulated day."""
    cumulative: np.ndarray = np.cumsum(daily, axis=1)
    return cumulative


class Interval(BaseModel):
    level: float
    low: float
    high: float


class HorizonSummary(BaseModel):
    """The outcome distribution at one horizon, as prices."""

    steps: int
    quantiles: dict[str, float]
    intervals: list[Interval]
    # Histogram of the final price: bin edges (one more than counts) and counts.
    histogram_edges: list[float]
    histogram_counts: list[int]
    # Average of each path's largest peak-to-trough fall, as a negative fraction.
    expected_worst_drawdown: float
    mean_return: float


def interval_bounds(terminal: np.ndarray, level: float) -> tuple[float, float]:
    """The central interval holding `level` of the outcomes."""
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(terminal, [tail, 1.0 - tail])
    return float(low), float(high)


def summarise(
    cumulative: np.ndarray, steps: int, start_price: float, bins: int = 40
) -> HorizonSummary:
    """Describe the distribution `steps` days ahead. `cumulative` is from `cumulative_returns`."""
    paths = cumulative[:, :steps]
    terminal = paths[:, -1]
    prices = start_price * np.exp(terminal)
    # Drawdown along each path, counting the starting price as the first peak.
    with_start = np.concatenate([np.zeros((len(paths), 1)), paths], axis=1)
    peak = np.maximum.accumulate(with_start, axis=1)
    worst = np.exp(with_start - peak).min(axis=1) - 1.0
    low, high = np.quantile(prices, [0.005, 0.995])
    counts, edges = np.histogram(prices[(prices >= low) & (prices <= high)], bins=bins)
    return HorizonSummary(
        steps=steps,
        quantiles={
            f"{q:g}": float(start_price * np.exp(np.quantile(terminal, q))) for q in QUANTILES
        },
        intervals=[
            Interval(
                level=level,
                low=start_price * float(np.exp(interval_bounds(terminal, level)[0])),
                high=start_price * float(np.exp(interval_bounds(terminal, level)[1])),
            )
            for level in INTERVALS
        ],
        histogram_edges=[float(e) for e in edges],
        histogram_counts=[int(c) for c in counts],
        expected_worst_drawdown=float(worst.mean()),
        mean_return=float(np.exp(terminal).mean() - 1.0),
    )


def fan(cumulative: np.ndarray, start_price: float) -> dict[str, list[float]]:
    """Price quantiles at the end of each day, for a fan chart. Day 0 is the start price."""
    result: dict[str, list[float]] = {}
    for q in QUANTILES:
        path = start_price * np.exp(np.quantile(cumulative, q, axis=0))
        result[f"{q:g}"] = [start_price, *[float(v) for v in path]]
    return result


class LevelProbabilities(BaseModel):
    """Chances relating to one price level. Two different questions, kept apart."""

    level: float
    steps: int
    # The price is at or beyond the level at the end of the horizon.
    ends_above: float
    ends_below: float
    # The price reaches the level at the close of any day in the horizon.
    touches: float


def level_probabilities(
    cumulative: np.ndarray, steps: int, start_price: float, level: float
) -> LevelProbabilities:
    paths = start_price * np.exp(cumulative[:, :steps])
    terminal = paths[:, -1]
    # The current price counts: a level the price already sits at has been touched.
    highest = np.maximum(paths.max(axis=1), start_price)
    lowest = np.minimum(paths.min(axis=1), start_price)
    touched = highest >= level if level >= start_price else lowest <= level
    return LevelProbabilities(
        level=level,
        steps=steps,
        ends_above=float((terminal >= level).mean()),
        ends_below=float((terminal < level).mean()),
        touches=float(touched.mean()),
    )


# --- baseline --------------------------------------------------------------------------


def gbm_quantiles(trailing_returns: np.ndarray, steps: int, levels: np.ndarray) -> np.ndarray:
    """Baseline: a random walk with constant drift and volatility from the trailing year.

    Returns the quantiles of the cumulative log return `steps` days ahead.
    """
    from scipy.stats import norm

    mean, std = trailing_returns.mean(), trailing_returns.std(ddof=1)
    quantiles: np.ndarray = steps * mean + np.sqrt(steps) * std * norm.ppf(levels)
    return quantiles


def pinball_loss(realised: np.ndarray, predicted: np.ndarray, level: float) -> float:
    """Average pinball loss of a predicted quantile; lower is better."""
    diff = realised - predicted
    return float(np.mean(np.maximum(level * diff, (level - 1.0) * diff)))
