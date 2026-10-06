"""Risk levels, other mixes, and the gap to a chosen target, for the stored portfolio.

Built from an analysis that already exists, so everything here agrees with the figures
on the other tabs: the same covariance, the same yardstick (the daily movement of US
stocks), the same holdings.

The output describes. It gives the size of the gap between the portfolio and the target
the user chose, in shares and in money. It never says what to do about it.
"""

from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel

from radar.analytics import summary
from radar.features.panels import MixedPanel
from radar.models import allocation
from radar.models import portfolio as model
from radar.models.holdings import CASH

LEVELS: tuple[allocation.Level, ...] = ("low", "moderate", "high")
SignalKind = Literal["risk_above_target", "risk_below_target", "drift", "turbulent"]


class Target(BaseModel):
    """What the user chose to hold the portfolio against."""

    level: allocation.Level
    split: allocation.Method = "current"
    set_at: AwareDatetime | None = None


class Signal(BaseModel):
    """Something that has moved the portfolio away from its target, with its size."""

    kind: SignalKind
    # The figure the signal is about: a ratio of swings, or a share of the money.
    value: float
    # What it is compared with: the edge of the band, or the threshold.
    against: float
    symbols: list[str] = []


class Plan(BaseModel):
    # How much the holdings swing with no cash at all, as a multiple of US stocks.
    invested_ratio: float
    # The mix's swings over the long run and in current conditions, same yardstick.
    ratio: float
    now_ratio: float | None
    # What each level would ask of these holdings, for the split in use.
    levels: list[allocation.LevelPlan]
    # Each way of splitting the established holdings, backtested. Empty with one holding.
    mixes: list[allocation.Backtest]
    target: Target | None = None
    # The chosen level applied to the chosen split, and each holding's gap to it.
    target_plan: allocation.LevelPlan | None = None
    moves: list[allocation.Move] = []
    in_band: bool | None = None
    signals: list[Signal] = []
    trust: summary.Trust


def _proportions(
    method: allocation.Method,
    symbols: list[str],
    current: np.ndarray,
    young: set[str],
    mixes: list[allocation.Backtest],
) -> np.ndarray:
    """Shares of the invested part under one split. Newer holdings keep their share: the
    split is worked out for the holdings with a long record only."""
    chosen = next((m for m in mixes if m.method == method), None)
    if method == "current" or chosen is None:
        return current
    kept = float(sum(current[i] for i, s in enumerate(symbols) if s in young))
    return np.array(
        [
            current[i] if s in young else (1.0 - kept) * chosen.weights_now.get(s, 0.0)
            for i, s in enumerate(symbols)
        ]
    )


def build(
    xray: model.Xray,
    level: model.RiskLevel,
    young: list[str],
    states: dict[str, str],
    covered_value: float,
    panel: MixedPanel,
    target: Target | None,
    *,
    window: int = allocation.WINDOW,
) -> Plan:
    """The plan for an analysed portfolio. `states` maps a holding to its market's state."""
    symbols = xray.symbols
    by_symbol = {h.symbol: h for h in xray.holdings}
    spread = np.array([by_symbol[s].daily_volatility for s in symbols])
    cov = np.array(xray.correlation) * np.outer(spread, spread)
    whole = np.array([by_symbol[s].weight for s in symbols])
    cash = by_symbol[CASH].weight if CASH in by_symbol else 0.0
    current = whole / whole.sum()
    stock_swing = xray.daily_volatility / level.ratio

    def invested_ratio(p: np.ndarray) -> float:
        return float(np.sqrt(p @ cov @ p)) / stock_swing

    established = [s for s in symbols if s not in set(young)]
    mixes: list[allocation.Backtest] = []
    if len(established) >= 2:
        simple = np.expm1(panel.returns[established].dropna())
        weights = np.array([by_symbol[s].weight for s in established])
        share = cash / (cash + float(weights.sum()))
        try:
            mixes = [
                allocation.backtest(
                    pd.DataFrame(simple), method, weights, cash=share, window=window
                )
                for method in allocation.METHODS
            ]
        except ValueError:
            mixes = []

    method: allocation.Method = target.split if target else "current"
    proportions = _proportions(method, symbols, current, set(young), mixes)
    full = invested_ratio(proportions)
    levels = [allocation.level_plan(name, full) for name in LEVELS]

    # In current conditions: the long-run figure scaled by how much the mix has been
    # swinging lately against its own long-run swings.
    now_ratio = None
    if established:
        own = model.mix_returns(
            panel.returns[established], np.array([by_symbol[s].weight for s in established])
        )
        recent = model.recent_volatility(own.to_numpy(dtype=float))
        usual = float(own.std())
        if len(recent) and not np.isnan(recent[-1]) and usual > 0:
            now_ratio = level.ratio * float(recent[-1]) / usual

    plan = Plan(
        invested_ratio=invested_ratio(current),
        ratio=level.ratio,
        now_ratio=now_ratio,
        levels=levels,
        mixes=mixes,
        trust=summary.grade_mixes(mixes[0].n_days if mixes else 0),
    )
    if target is None:
        return plan

    chosen = next(p for p in levels if p.level == target.level)
    wanted = {s: float(proportions[i]) * (1.0 - chosen.cash_share) for i, s in enumerate(symbols)}
    wanted[CASH] = chosen.cash_share
    held = {s: float(by_symbol[s].weight) for s in symbols}
    held[CASH] = cash
    gaps = allocation.moves(held, wanted, covered_value)
    seen = now_ratio if now_ratio is not None else level.ratio
    signals: list[Signal] = []
    if seen >= chosen.band_high:
        signals.append(Signal(kind="risk_above_target", value=seen, against=chosen.band_high))
    elif seen < chosen.band_low:
        signals.append(Signal(kind="risk_below_target", value=seen, against=chosen.band_low))
    drifted = [g.symbol for g in gaps if g.drifted]
    if drifted:
        widest = max(abs(g.target_weight - g.current_weight) for g in gaps)
        signals.append(
            Signal(
                kind="drift",
                value=widest,
                against=allocation.DRIFT_THRESHOLD,
                symbols=drifted,
            )
        )
    rough = [s for s in symbols if states.get(s) == "turbulent"]
    if rough:
        signals.append(
            Signal(
                kind="turbulent",
                value=float(sum(held[s] for s in rough)),
                against=0.0,
                symbols=rough,
            )
        )
    return plan.model_copy(
        update={
            "target": target,
            "target_plan": chosen,
            "moves": gaps,
            "in_band": chosen.band_low <= seen < chosen.band_high,
            "signals": signals,
        }
    )


def stamped(level: allocation.Level, split: allocation.Method, now: datetime) -> Target:
    return Target(level=level, split=split, set_at=now)
