"""Other ways to split a portfolio, and what a chosen risk level asks of it (spec F6).

Two separate questions, kept apart on purpose:

- **How the holdings are split among themselves.** Five rules: the split as it is now,
  equal weights, the split with the smallest swings, the split where every holding
  carries the same share of risk, and hierarchical risk parity. All are long-only, with a
  cap on any one holding.
- **How much is kept in cash.** Cash does not move, so it scales the whole mix's swings
  down in proportion. A risk level (low, moderate, high) fixes how large those swings
  should be against the stock market's, and that fixes the cash share.

The backtest is walk-forward: at each monthly rebalance the split is worked out from
returns before that day only. It reports history, not an expectation.

Nothing here says what anyone ought to hold. It describes mixes and how they behaved.
"""

from collections.abc import Callable
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf

MODEL_VERSION = "allocation-1"

Method = Literal["current", "equal", "min_variance", "equal_risk", "hierarchical"]
METHODS: tuple[Method, ...] = ("current", "equal", "min_variance", "equal_risk", "hierarchical")
Level = Literal["low", "moderate", "high"]

# No holding above this share of the invested part, unless there are too few to allow it.
MAX_WEIGHT = 0.6
# Sessions of returns each rebalance looks back over, and sessions between rebalances.
WINDOW = 250
REBALANCE_EVERY = 21
# Cost of trading, as a share of the amount traded.
COST = 0.001
# A holding is flagged when it sits this far from its target share of the whole.
DRIFT_THRESHOLD = 0.05

# Daily swings as a multiple of US stocks': where each level ends, and the figure aimed
# for inside it. The edges are the ones on the risk scale (decision 041).
BANDS: dict[Level, tuple[float, float]] = {
    "low": (0.0, 0.5),
    "moderate": (0.5, 1.0),
    "high": (1.0, 2.0),
}
AIMS: dict[Level, float] = {"low": 0.25, "moderate": 0.75, "high": 1.5}


# --- splits ----------------------------------------------------------------------------


def cap_for(n: int, cap: float = MAX_WEIGHT) -> float:
    """The cap in force for `n` holdings: never below what an equal split needs."""
    return max(cap, 1.0 / n)


def capped(weights: np.ndarray, cap: float) -> np.ndarray:
    """Scale to sum to one with nothing above `cap`, handing any excess to the rest in
    proportion."""
    w = np.clip(np.asarray(weights, dtype=float), 0.0, None)
    w = w / w.sum()
    full = np.zeros(len(w), dtype=bool)  # holdings already at the cap
    for _ in range(len(w)):
        over = (w > cap + 1e-12) & ~full
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        full |= over
        room = ~full
        if not room.any():
            break
        if w[room].sum() > 0:
            w[room] += excess * w[room] / w[room].sum()
        else:
            w[room] += excess / room.sum()
    return np.asarray(w, dtype=float)


def _solve(
    objective: Callable[[np.ndarray], float], n: int, cap: float, start: np.ndarray
) -> np.ndarray:
    result = minimize(
        objective,
        start,
        method="SLSQP",
        bounds=[(0.0, cap)] * n,
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}],
        options={"maxiter": 500, "ftol": 1e-12},
    )
    return capped(np.asarray(result.x, dtype=float), cap)


def min_variance(cov: np.ndarray, cap: float) -> np.ndarray:
    """The long-only split with the smallest swings."""
    n = len(cov)
    scale = float(np.trace(cov)) / n or 1.0
    return _solve(lambda w: float(w @ cov @ w) / scale, n, cap, np.full(n, 1.0 / n))


def equal_risk(cov: np.ndarray, cap: float) -> np.ndarray:
    """The split in which every holding carries the same share of the risk, as nearly as
    the cap allows."""
    n = len(cov)
    scale = float(np.trace(cov)) / n or 1.0

    def spread(w: np.ndarray) -> float:
        contribution = w * (cov @ w) / scale
        return float(((contribution - contribution.mean()) ** 2).sum()) * 1e4

    start = 1.0 / np.sqrt(np.diag(cov))
    return _solve(spread, n, cap, capped(start, cap))


def hierarchical(cov: np.ndarray, cap: float) -> np.ndarray:
    """Hierarchical risk parity: group holdings that move alike, then share risk between
    groups and within them by inverse variance."""
    n = len(cov)
    if n == 1:
        return np.ones(1)
    spread = np.sqrt(np.diag(cov))
    corr = np.clip(cov / np.outer(spread, spread), -1.0, 1.0)
    order = list(range(n))
    if n > 2:
        distance = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))
        np.fill_diagonal(distance, 0.0)
        order = [int(i) for i in leaves_list(linkage(squareform(distance, checks=False), "single"))]

    def cluster_variance(items: list[int]) -> float:
        block = cov[np.ix_(items, items)]
        inverse = 1.0 / np.diag(block)
        w = inverse / inverse.sum()
        return float(w @ block @ w)

    weights = np.ones(n)
    groups = [order]
    while groups:
        nxt = []
        for group in groups:
            if len(group) < 2:
                continue
            left, right = group[: len(group) // 2], group[len(group) // 2 :]
            v_left, v_right = cluster_variance(left), cluster_variance(right)
            share = 1.0 - v_left / (v_left + v_right)
            weights[left] *= share
            weights[right] *= 1.0 - share
            nxt += [left, right]
        groups = nxt
    return capped(weights, cap)


def split(method: Method, cov: np.ndarray, current: np.ndarray, cap: float) -> np.ndarray:
    """Weights of the invested part under one rule. They sum to one."""
    n = len(cov)
    if method == "current":
        return np.asarray(current, dtype=float) / float(np.sum(current))
    if method == "equal":
        return np.full(n, 1.0 / n)
    if method == "min_variance":
        return min_variance(cov, cap)
    if method == "equal_risk":
        return equal_risk(cov, cap)
    return hierarchical(cov, cap)


def shrunk_covariance(returns: np.ndarray) -> np.ndarray:
    return np.asarray(LedoitWolf().fit(returns).covariance_, dtype=float)


# --- walk-forward backtest -------------------------------------------------------------


def rebalance_weights(
    returns: pd.DataFrame,
    method: Method,
    current: np.ndarray,
    *,
    window: int = WINDOW,
    every: int = REBALANCE_EVERY,
    cap: float = MAX_WEIGHT,
) -> pd.DataFrame:
    """The split chosen at each rebalance, indexed by the first session it applies to.

    `returns` holds simple daily returns, complete rows only. The split for a session
    uses the `window` sessions before it and nothing from that session on.
    """
    values = returns.to_numpy(dtype=float)
    limit = cap_for(values.shape[1], cap)
    rows, stamps = [], []
    for i in range(window, len(values), every):
        cov = shrunk_covariance(values[i - window : i])
        rows.append(split(method, cov, current, limit))
        stamps.append(returns.index[i])
    return pd.DataFrame(rows, index=pd.DatetimeIndex(stamps), columns=returns.columns)


class Backtest(BaseModel):
    """How one way of splitting the holdings behaved, rebalanced monthly. History only."""

    method: Method
    n_days: int
    first_day: date
    last_day: date
    rebalances: int
    # Standard deviation of the mix's daily return, cash included.
    daily_volatility: float
    deepest_fall: float
    # Average share of the whole mix traded at each rebalance.
    turnover: float
    # Growth over the whole period after trading costs. History, not an expectation.
    total_return: float
    cost_paid: float
    # The split in force today, by holding; the shares of the invested part sum to one.
    weights_now: dict[str, float]
    # The value of one unit at each rebalance, for a small chart.
    path: list[float]


def backtest(
    returns: pd.DataFrame,
    method: Method,
    current: np.ndarray,
    *,
    cash: float = 0.0,
    window: int = WINDOW,
    every: int = REBALANCE_EVERY,
    cost: float = COST,
    cap: float = MAX_WEIGHT,
) -> Backtest:
    """Run one split through the stored history. `cash` is the share kept in cash, which
    earns nothing and is restored at each rebalance."""
    targets = rebalance_weights(returns, method, current, window=window, every=every, cap=cap)
    if targets.empty:
        raise ValueError("Not enough history for a walk-forward backtest")
    values = returns.to_numpy(dtype=float)
    invested = 1.0 - cash
    value = 1.0
    held = np.zeros(values.shape[1])  # value held in each holding
    idle = 1.0  # value held in cash
    daily: list[float] = []
    path: list[float] = []
    traded: list[float] = []
    costs = 0.0
    schedule = {returns.index.get_loc(stamp): row for stamp, row in targets.iterrows()}
    for i in range(window, len(values)):
        if i in schedule:
            wanted = schedule[i].to_numpy(dtype=float) * invested * value
            moved = float(np.abs(wanted - held).sum())
            fee = moved * cost
            if path:  # the first purchase sets the mix up; it is not a rebalance
                traded.append(moved / value)
                costs += fee / value
                value -= fee
                wanted = schedule[i].to_numpy(dtype=float) * invested * value
            held = wanted
            idle = value - float(held.sum())
            path.append(value)
        before = value
        held = held * (1.0 + values[i])
        value = float(held.sum()) + idle
        daily.append(value / before - 1.0)
    series = np.array(daily)
    level = np.concatenate([[1.0], np.cumprod(1.0 + series)])
    days = pd.DatetimeIndex(returns.index[window:])
    return Backtest(
        method=method,
        n_days=len(series),
        first_day=days[0].date(),
        last_day=days[-1].date(),
        rebalances=len(traded),
        daily_volatility=float(series.std()),
        deepest_fall=float((level / np.maximum.accumulate(level) - 1.0).min()),
        turnover=float(np.mean(traded)) if traded else 0.0,
        total_return=float(value - 1.0),
        cost_paid=float(costs),
        weights_now={str(c): float(w) for c, w in targets.iloc[-1].items()},
        path=[float(p) for p in path],
    )


# --- risk levels -----------------------------------------------------------------------


class LevelPlan(BaseModel):
    """What one risk level would ask of these holdings."""

    level: Level
    # The swings aimed for, and the band the level covers, as multiples of US stocks'.
    aim: float
    band_low: float
    band_high: float
    # Share of the whole kept in cash to reach the aim, keeping the holdings' own split.
    cash_share: float
    # The swings that cash share gives. Below the aim when the level cannot be reached.
    ratio: float
    # False when even with no cash these holdings swing less than the level aims for.
    reachable: bool


def level_plan(level: Level, invested_ratio: float) -> LevelPlan:
    """The cash share that brings a mix to a level.

    `invested_ratio` is how much the holdings swing with no cash at all, as a multiple of
    US stocks. Cash scales that down in proportion, so the share is one minus the aim
    over that figure. With no borrowing, the most these holdings can reach is
    `invested_ratio` itself.
    """
    aim = AIMS[level]
    low, high = BANDS[level]
    reachable = invested_ratio >= aim
    cash = max(0.0, 1.0 - aim / invested_ratio) if invested_ratio > 0 else 0.0
    return LevelPlan(
        level=level,
        aim=aim,
        band_low=low,
        band_high=high,
        cash_share=cash,
        ratio=invested_ratio * (1.0 - cash),
        reachable=reachable,
    )


def level_of(ratio: float) -> str:
    """The name of the level a mix's swings fall in."""
    for level, (_, high) in BANDS.items():
        if ratio < high:
            return level
    return "very high"


class Move(BaseModel):
    """How far one holding sits from its target share of the whole."""

    symbol: str
    current_weight: float
    target_weight: float
    # Positive when the holding is below target. In money at today's value.
    change_value: float
    drifted: bool


def moves(
    current: dict[str, float],
    target: dict[str, float],
    value: float,
    threshold: float = DRIFT_THRESHOLD,
) -> list[Move]:
    """Each holding's gap to target, flagged when it is wider than the threshold."""
    rows = []
    for symbol in dict.fromkeys([*current, *target]):
        now, wanted = current.get(symbol, 0.0), target.get(symbol, 0.0)
        rows.append(
            Move(
                symbol=symbol,
                current_weight=now,
                target_weight=wanted,
                change_value=(wanted - now) * value,
                drifted=abs(wanted - now) > threshold + 1e-9,
            )
        )
    return rows
