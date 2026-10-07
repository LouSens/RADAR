"""How a person trades, read from their own purchases and sales. Pure functions.

An exchange shows what was bought and sold. This sets each trade beside what the price
was doing around it: had it just risen or fallen, was the trade made near the top or the
bottom of the last week's range, and what the price did next. Averaged over many trades
and set beside "any hour", it shows a habit: buying after rises, selling after falls, or
the reverse.

Everything "before" a trade uses hours up to the trade. Everything "after" is hindsight,
shown as a record of what happened, and is missing for trades too recent to have it.
"""

from collections.abc import Iterable

import numpy as np
import pandas as pd
from pydantic import BaseModel

from radar.models.ledger import Entry

MODEL_VERSION = "trading-1"
DAY, WEEK = 24, 168
MIN_TRADES = 10


class Habit(BaseModel):
    """What the price was doing around one kind of trade, weighted by the money in each.

    `place` is where the trade's price sat in the range of the week before it: 0 at the
    week's low, 1 at its high. The moves are fractions (0.01 is 1%).
    """

    trades: int
    dollars: float
    before_day: float
    before_week: float
    place: float
    after_day: float | None
    after_week: float | None


class Usual(BaseModel):
    """The same figures for any hour of the period: what a habit is set beside."""

    hours: int
    before_day: float
    before_week: float
    place: float
    after_day: float
    after_week: float


def context(entries: Iterable[Entry], bars: pd.DataFrame, asset: str) -> pd.DataFrame:
    """One row per purchase or sale of `asset`, with what the price did around it.

    `bars` are hourly, indexed by opening time in UTC, with high, low and close. A trade
    is placed in the last bar that had opened when it was made, and its own price is
    used, not the bar's.
    """
    close = bars["close"].to_numpy(dtype=float)
    high, low = bars["high"].to_numpy(dtype=float), bars["low"].to_numpy(dtype=float)
    index = pd.DatetimeIndex(bars.index)
    rows = []
    for entry in entries:
        if entry.asset != asset or entry.kind not in ("buy", "sell") or not entry.dollars:
            continue
        i = int(index.searchsorted(pd.Timestamp(entry.at), side="right")) - 1
        if i < WEEK:
            continue
        price = entry.dollars / abs(entry.units)
        top = max(high[i - WEEK : i].max(), price)
        bottom = min(low[i - WEEK : i].min(), price)
        rows.append(
            {
                "at": entry.at,
                "kind": entry.kind,
                "dollars": entry.dollars,
                "price": price,
                "before_day": price / close[i - DAY] - 1,
                "before_week": price / close[i - WEEK] - 1,
                "place": (price - bottom) / (top - bottom) if top > bottom else 0.5,
                "after_day": close[i + DAY] / price - 1 if i + DAY < len(close) else np.nan,
                "after_week": close[i + WEEK] / price - 1 if i + WEEK < len(close) else np.nan,
            }
        )
    columns = [
        "at",
        "kind",
        "dollars",
        "price",
        "before_day",
        "before_week",
        "place",
        "after_day",
        "after_week",
    ]
    return pd.DataFrame(rows, columns=columns)


def _weighted(values: pd.Series, weights: pd.Series) -> float | None:
    known = values.notna()
    if not known.any():
        return None
    return float(np.average(values[known], weights=weights[known]))


def habit(trades: pd.DataFrame, kind: str) -> Habit | None:
    """The money-weighted averages over one kind of trade; none when there are none."""
    part = trades[trades["kind"] == kind]
    if part.empty:
        return None
    weights = part["dollars"]
    return Habit(
        trades=len(part),
        dollars=float(weights.sum()),
        before_day=_weighted(part["before_day"], weights) or 0.0,
        before_week=_weighted(part["before_week"], weights) or 0.0,
        place=_weighted(part["place"], weights) or 0.0,
        after_day=_weighted(part["after_day"], weights),
        after_week=_weighted(part["after_week"], weights),
    )


def usual(bars: pd.DataFrame, since: pd.Timestamp) -> Usual | None:
    """The same figures taken at every hour from `since`, as the comparison."""
    close, high, low = bars["close"], bars["high"], bars["low"]
    top = high.shift(1).rolling(WEEK).max().clip(lower=close)
    bottom = low.shift(1).rolling(WEEK).min().clip(upper=close)
    table = pd.DataFrame(
        {
            "before_day": close / close.shift(DAY) - 1,
            "before_week": close / close.shift(WEEK) - 1,
            "place": ((close - bottom) / (top - bottom)).where(top > bottom, 0.5),
            "after_day": close.shift(-DAY) / close - 1,
            "after_week": close.shift(-WEEK) / close - 1,
        }
    )
    table = table[table.index >= since].dropna(subset=["before_week", "place"])
    if table.empty:
        return None
    means = table.mean()
    return Usual(
        hours=len(table),
        before_day=float(means["before_day"]),
        before_week=float(means["before_week"]),
        place=float(means["place"]),
        after_day=float(means["after_day"]),
        after_week=float(means["after_week"]),
    )


def place_is_unusual(trades: pd.DataFrame, kind: str, bars: pd.DataFrame, seed: int = 7) -> bool:
    """Whether the average place of these trades in the week's range is further from
    the usual than chance would give, were the same number of trades made at random
    hours. False when there are fewer than `MIN_TRADES`.
    """
    part = trades[trades["kind"] == kind]
    if len(part) < MIN_TRADES:
        return False
    since = pd.Timestamp(part["at"].min())
    close, high, low = bars["close"], bars["high"], bars["low"]
    top = high.shift(1).rolling(WEEK).max().clip(lower=close)
    bottom = low.shift(1).rolling(WEEK).min().clip(upper=close)
    places = ((close - bottom) / (top - bottom)).where(top > bottom, 0.5)
    pool = places[places.index >= since].dropna().to_numpy()
    if len(pool) < len(part):
        return False
    rng = np.random.default_rng(seed)
    draws = rng.choice(pool, size=(2000, len(part))).mean(axis=1)
    seen = float(part["place"].mean())
    low_edge, high_edge = np.percentile(draws, [2.5, 97.5])
    return bool(seen < low_edge or seen > high_edge)
