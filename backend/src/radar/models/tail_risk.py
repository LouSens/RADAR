"""F10. Tail risk: how much could be lost in a bad period, and how often that limit broke.

Two measures, each as a fraction of the position lost over the horizon:

- Value at Risk (VaR) at 95%: the loss that should be exceeded in only 5% of periods.
- Expected shortfall (ES): the average loss in the periods that do exceed it.

Three ways of estimating them are compared:

- `historical`: the worst outcomes of the trailing window, as they were.
- `filtered`: the same past outcomes, each divided by the volatility forecast that
  applied to it and multiplied by today's forecast, so calm history is scaled up in
  rough markets and the reverse.
- `simulator`: the outcome simulator's own distribution for the day.

No lookahead: an estimate for day `t` uses outcomes that were complete by day `t`,
forecasts made on or before day `t`, and simulations run from day `t`.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats

MODEL_VERSION = "tail-risk-1"
LEVELS = (0.95, 0.99)
METHODS = ("historical", "filtered", "simulator")
WINDOW = 500
MIN_WINDOW = 250
SIGNIFICANCE = 0.05


@dataclass
class RiskInputs:
    """What the estimates are built from, for one horizon. Arrays have one entry per day."""

    returns: np.ndarray  # daily log returns
    # Volatility forecast made on each day for this horizon (per day); NaN where none.
    volatility_forecast: np.ndarray
    # Days that have a simulation, and each one's simulated log returns over the horizon.
    simulated_days: np.ndarray
    simulated: np.ndarray


def forward_returns(returns: np.ndarray, steps: int) -> np.ndarray:
    """Log return over the `steps` days after each day. NaN where the future is incomplete."""
    csum = np.concatenate([[0.0], np.cumsum(returns)])
    n = len(returns)
    out = np.full(n, np.nan)
    known = np.arange(n) + steps < n
    positions = np.arange(n)[known]
    out[known] = csum[positions + steps + 1] - csum[positions + 1]
    return out


def tail(log_returns: np.ndarray, level: float) -> tuple[float, float]:
    """VaR and expected shortfall of a set of outcomes, as positive loss fractions."""
    losses = 1.0 - np.exp(log_returns)
    var = float(np.quantile(losses, level))
    beyond = losses[losses >= var]
    return var, float(beyond.mean()) if len(beyond) else var


@dataclass
class Estimates:
    """Estimates for every day, for one horizon."""

    steps: int
    # (method, level) -> VaR and ES per day; NaN where the method had too little to go on.
    var: dict[tuple[str, float], np.ndarray]
    es: dict[tuple[str, float], np.ndarray]
    # The loss that actually followed each day; NaN where not yet known.
    realised_loss: np.ndarray


def estimate(
    inputs: RiskInputs,
    steps: int,
    *,
    levels: tuple[float, ...] = LEVELS,
    window: int = WINDOW,
    min_window: int = MIN_WINDOW,
) -> Estimates:
    """VaR and ES for every day by every method that has enough data on that day."""
    n = len(inputs.returns)
    forward = forward_returns(inputs.returns, steps)
    scale = np.sqrt(steps)
    standardised = forward / (inputs.volatility_forecast * scale)
    var = {(m, lv): np.full(n, np.nan) for m in METHODS for lv in levels}
    es = {(m, lv): np.full(n, np.nan) for m in METHODS for lv in levels}

    for t in range(n):
        # Outcomes that were complete by day t: those that began `steps` days earlier.
        last = t - steps
        if last < 0:
            continue
        first = max(0, last - window + 1)
        past = forward[first : last + 1]
        if len(past) >= min_window:
            for level in levels:
                var[("historical", level)][t], es[("historical", level)][t] = tail(past, level)
        today = inputs.volatility_forecast[t]
        shocks = standardised[first : last + 1]
        shocks = shocks[~np.isnan(shocks)]
        if not np.isnan(today) and len(shocks) >= min_window:
            for level in levels:
                key = ("filtered", level)
                var[key][t], es[key][t] = tail(shocks * today * scale, level)

    for row, t in enumerate(inputs.simulated_days):
        for level in levels:
            key = ("simulator", level)
            var[key][t], es[key][t] = tail(inputs.simulated[row].astype(float), level)

    return Estimates(steps=steps, var=var, es=es, realised_loss=1.0 - np.exp(forward))


# --- backtest --------------------------------------------------------------------------


def _log_likelihood(successes: int, trials: int, probability: float) -> float:
    """Binomial log likelihood, with 0 * log(0) taken as 0."""
    total = 0.0
    if successes:
        total += successes * np.log(probability) if probability > 0 else -np.inf
    if trials - successes:
        total += (trials - successes) * np.log1p(-probability) if probability < 1 else -np.inf
    return float(total)


def kupiec(breaches: int, n: int, level: float) -> float:
    """Kupiec's test that breaches happen at the stated rate. Returns the p-value.

    A small p-value means the limit was broken measurably more or less often than it
    should have been.
    """
    if n == 0:
        return float("nan")
    expected = 1.0 - level
    ratio = 2.0 * (
        _log_likelihood(breaches, n, breaches / n) - _log_likelihood(breaches, n, expected)
    )
    return float(stats.chi2.sf(max(ratio, 0.0), df=1))


def christoffersen(breached: np.ndarray) -> float:
    """Christoffersen's test that breaches do not cluster. Returns the p-value.

    A small p-value means a breach was measurably more likely right after another one.
    """
    flags = np.asarray(breached, dtype=bool)
    if len(flags) < 2:
        return float("nan")
    before, after = flags[:-1], flags[1:]
    n00 = int((~before & ~after).sum())
    n01 = int((~before & after).sum())
    n10 = int((before & ~after).sum())
    n11 = int((before & after).sum())
    if n01 + n11 == 0 or n10 + n11 == 0:
        return float("nan")  # no breach, or none with a day after it: nothing to test
    pooled = _log_likelihood(n01 + n11, n00 + n01 + n10 + n11, (n01 + n11) / (len(flags) - 1))
    split = _log_likelihood(n01, n00 + n01, n01 / (n00 + n01)) + _log_likelihood(
        n11, n10 + n11, n11 / (n10 + n11)
    )
    return float(stats.chi2.sf(max(2.0 * (split - pooled), 0.0), df=1))


class Backtest(BaseModel):
    """How one method's limit held at one level. Every period is out of sample."""

    method: str
    level: float
    # Periods tested. For horizons longer than a day they do not overlap.
    n: int
    breaches: int
    expected_breaches: float
    breach_rate: float
    kupiec_p_value: float | None
    clustering_p_value: float | None
    # False when the breach rate differs measurably from the stated rate.
    reliable: bool
    first_day: date
    last_day: date


def backtest(estimates: Estimates, index: pd.DatetimeIndex) -> list[Backtest]:
    """Count breaches for every method and level over the same periods.

    Only days where every available method has an estimate and the outcome is known are
    used, so the methods are compared like for like. For a horizon of several days,
    every `steps`-th day is used so that periods do not overlap.
    """
    methods = [
        m
        for m in METHODS
        if any(not np.isnan(v).all() for (k, _), v in estimates.var.items() if k == m)
    ]
    levels = sorted({level for _, level in estimates.var})
    usable = ~np.isnan(estimates.realised_loss)
    for method in methods:
        for level in levels:
            usable &= ~np.isnan(estimates.var[(method, level)])
    positions = np.flatnonzero(usable)
    if len(positions) == 0:
        return []
    positions = positions[(positions - positions[0]) % estimates.steps == 0]
    rows = []
    for method in methods:
        for level in levels:
            breached = (
                estimates.realised_loss[positions] > estimates.var[(method, level)][positions]
            )
            count = int(breached.sum())
            coverage = kupiec(count, len(positions), level)
            clustering = christoffersen(breached)
            rows.append(
                Backtest(
                    method=method,
                    level=level,
                    n=len(positions),
                    breaches=count,
                    expected_breaches=float(len(positions) * (1.0 - level)),
                    breach_rate=count / len(positions),
                    kupiec_p_value=None if np.isnan(coverage) else coverage,
                    clustering_p_value=None if np.isnan(clustering) else clustering,
                    reliable=bool(np.isnan(coverage) or coverage >= SIGNIFICANCE),
                    first_day=index[positions[0]].date(),
                    last_day=index[positions[-1]].date(),
                )
            )
    return rows


def choose(rows: list[Backtest]) -> str | None:
    """The method to display: the one whose limits held closest to their stated rates.

    Methods whose limits are reliable at every level come first. Ties are settled by how
    far each breach rate is from its stated rate, relative to that rate, summed over levels.
    """
    by_method: dict[str, list[Backtest]] = {}
    for row in rows:
        by_method.setdefault(row.method, []).append(row)
    if not by_method:
        return None

    def rank(method: str) -> tuple[int, float]:
        own = by_method[method]
        unreliable = sum(not r.reliable for r in own)
        distance = sum(abs(r.breach_rate - (1 - r.level)) / (1 - r.level) for r in own)
        return unreliable, distance

    return min(by_method, key=rank)


# --- drawdowns -------------------------------------------------------------------------


class Drawdown(BaseModel):
    peak_day: date
    trough_day: date
    # Fall from the peak to the lowest close, as a negative fraction.
    depth: float
    # The first day the close was back above the peak. Empty if it has not recovered.
    recovered_day: date | None


def worst_drawdowns(close: pd.Series, count: int = 5) -> list[Drawdown]:
    """The deepest peak-to-trough falls in daily closes, each counted once."""
    clean = close.dropna()
    if clean.empty:
        return []
    values = clean.to_numpy(dtype=float)
    days = pd.DatetimeIndex(clean.index)
    episodes: list[Drawdown] = []
    peak = 0
    trough = 0
    for i in range(1, len(values)):
        if values[i] >= values[peak]:
            if values[trough] < values[peak]:
                episodes.append(
                    Drawdown(
                        peak_day=days[peak].date(),
                        trough_day=days[trough].date(),
                        depth=float(values[trough] / values[peak] - 1.0),
                        recovered_day=days[i].date(),
                    )
                )
            peak = trough = i
        elif values[i] < values[trough]:
            trough = i
    if values[trough] < values[peak]:
        episodes.append(
            Drawdown(
                peak_day=days[peak].date(),
                trough_day=days[trough].date(),
                depth=float(values[trough] / values[peak] - 1.0),
                recovered_day=None,
            )
        )
    return sorted(episodes, key=lambda e: e.depth)[:count]
