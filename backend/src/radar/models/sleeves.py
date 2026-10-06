"""F6. Core and satellite: what each group of holdings carries and what it has added.

The user tags a holding as core (the part meant to be held steadily) or satellite (the
smaller, more adventurous part). The report sets each group's share of the money beside
its share of the risk, and what it added to the mix's return.

The return figures replay today's weights through the past, so they describe today's
mix in past markets, not what the user actually earned.
"""

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from radar.models.portfolio import HoldingRisk

Group = Literal["core", "satellite", "untagged", "cash"]
ORDER: tuple[Group, ...] = ("core", "satellite", "untagged", "cash")
# Sessions the contribution to return is added up over: about a year.
WINDOW = 250


class Sleeve(BaseModel):
    group: Group
    symbols: list[str]
    weight: float
    risk_share: float
    # What the group added to the mix's return over the window, in points of the whole.
    contribution: float


class Report(BaseModel):
    sleeves: list[Sleeve]
    n_days: int
    first_day: date
    last_day: date
    # The sum of the contributions: the mix's return over the window at today's weights.
    total_return: float
    # Holdings with fewer sessions than the window; theirs is added up over what they have.
    short: list[str]


def contributions(returns: pd.DataFrame, weights: dict[str, float]) -> dict[str, float]:
    """Each holding's weight times the sum of its daily returns: the parts add up to the
    sum of the mix's daily returns at fixed weights."""
    simple = np.nansum(np.expm1(returns.to_numpy(dtype=float)), axis=0)
    return {
        str(symbol): float(weights.get(str(symbol), 0.0) * simple[i])
        for i, symbol in enumerate(returns.columns)
    }


def report(
    holdings: list[HoldingRisk],
    tags: dict[str, str],
    returns: pd.DataFrame,
    cash: str,
    window: int = WINDOW,
) -> Report | None:
    """The report, or None when no holding is tagged. `returns` has a column of daily
    log returns for every holding except cash."""
    if not any(tags.get(h.symbol) in ("core", "satellite") for h in holdings):
        return None
    columns = [h.symbol for h in holdings if h.symbol != cash and h.symbol in returns.columns]
    recent = returns[columns].dropna(how="all").iloc[-window:]
    added = contributions(recent, {h.symbol: h.weight for h in holdings})
    days = pd.DatetimeIndex(recent.index)

    def group_of(symbol: str) -> Group:
        if symbol == cash:
            return "cash"
        tag = tags.get(symbol)
        return "core" if tag == "core" else "satellite" if tag == "satellite" else "untagged"

    sleeves = []
    for group in ORDER:
        members = [h for h in holdings if group_of(h.symbol) == group]
        if not members:
            continue
        sleeves.append(
            Sleeve(
                group=group,
                symbols=[h.symbol for h in members],
                weight=sum(h.weight for h in members),
                risk_share=sum(h.risk_share for h in members),
                contribution=sum(added.get(h.symbol, 0.0) for h in members),
            )
        )
    return Report(
        sleeves=sleeves,
        n_days=len(recent),
        first_day=days[0].date(),
        last_day=days[-1].date(),
        total_return=sum(s.contribution for s in sleeves),
        short=[c for c in columns if int(recent[c].notna().sum()) < len(recent)],
    )
