"""Before you buy: is this price high or low against its own recent past? (decision 078)

Not a forecast. It says where the price sits between the lowest and highest of the last
week, month and three months, and sets that beside the user's own record: where their
past purchases sat, and what followed the ones made near the top and near the bottom.
The account record shows the user bought near the week's high; this is the check that
would have said so at the time.

Prices are hourly bars from Binance's public market data, asked for when the check is
made. Every figure uses prices up to now only.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

import pandas as pd
from pydantic import AwareDatetime, BaseModel

from radar.pipelines import account
from radar.providers import binance_public
from radar.providers.public import PublicReader

VERSION = "check-1"
DAY, WEEK, MONTH, QUARTER = 24, 168, 720, 2160
YEAR_DAYS = 365
HISTORY = timedelta(days=95)
HIGH, LOW = 0.65, 0.35
Where = Literal["high", "middle", "low"]


class Yours(BaseModel):
    """What the record says about this coin."""

    purchases: int
    sales: int
    result: float
    held: bool


class Check(BaseModel):
    coin: str
    as_of: AwareDatetime
    model_version: str
    price: float
    # Where the price sits between the lowest and highest of each period: 0 to 1.
    place_day: float | None = None
    place_week: float
    place_month: float | None
    place_quarter: float | None
    place_year: float | None = None
    # How far it has moved over the last day and week, and how far below the highest
    # price of the longest period there is.
    move_day: float
    move_week: float
    below_high: float
    weekly_swing: float | None
    where: Where
    yours: Yours | None = None
    # Where the user's purchases have sat in the week before them, over every coin.
    habit_place: float | None = None
    outcomes: list[account.Outcome] = []


def _place(bars: pd.DataFrame, hours: int) -> float | None:
    if len(bars) < hours:
        return None
    recent = bars.iloc[-hours:]
    top, bottom = float(recent["high"].max()), float(recent["low"].min())
    last = float(bars["close"].iloc[-1])
    return (last - bottom) / (top - bottom) if top > bottom else 0.5


def where(place_week: float, place_month: float | None) -> Where:
    """High, middle or low, from the week and the month together."""
    level = place_week if place_month is None else (place_week + place_month) / 2
    return "high" if level >= HIGH else "low" if level <= LOW else "middle"


def build(
    coin: str,
    bars: pd.DataFrame,
    record: account.Record | None,
    now: datetime,
    daily: pd.DataFrame | None = None,
) -> Check:
    """The check for one coin from its hourly bars (at least a week of them), and from a
    year of daily bars when there is one."""
    close = bars["close"]
    last = float(close.iloc[-1])
    week = _place(bars, WEEK)
    if week is None:
        raise ValueError("At least a week of hourly prices is needed")
    month, quarter = _place(bars, MONTH), _place(bars, QUARTER)
    year = None
    if daily is not None and len(daily) >= YEAR_DAYS - 30:
        recent = daily.iloc[-YEAR_DAYS:]
        top = max(float(recent["high"].max()), last)
        bottom = min(float(recent["low"].min()), last)
        year = (last - bottom) / (top - bottom) if top > bottom else 0.5
    longest = bars.iloc[-min(len(bars), QUARTER) :]
    by_day = close.iloc[::24].pct_change().dropna()
    swing = float(by_day.iloc[-20:].std() * 5**0.5) if len(by_day) >= 20 else None
    mine = next((a for a in record.assets if a.asset == coin), None) if record else None
    buys = [a.buys for a in record.assets if a.buys] if record else []
    spent = sum(b.dollars for b in buys)
    return Check(
        coin=coin,
        as_of=now,
        model_version=VERSION,
        price=last,
        place_day=_place(bars, DAY),
        place_week=week,
        place_month=month,
        place_quarter=quarter,
        place_year=year,
        move_day=last / float(close.iloc[-25]) - 1,
        move_week=last / float(close.iloc[-WEEK]) - 1,
        below_high=last / float(longest["high"].max()) - 1,
        weekly_swing=swing,
        where=where(week, month),
        yours=(
            None
            if mine is None
            else Yours(
                purchases=mine.standing.purchases,
                sales=mine.standing.sales,
                result=mine.standing.realised + (mine.unrealised or 0.0),
                held=mine.held,
            )
        ),
        habit_place=sum(b.place * b.dollars for b in buys) / spent if spent > 0 else None,
        outcomes=record.buy_outcomes if record else [],
    )


def fetch(source: PublicReader, coin: str, now: datetime | None = None) -> pd.DataFrame:
    """About three months of hourly bars for a coin against USDT; empty when Binance
    does not list it."""
    now = now or datetime.now(UTC)
    start, end = int((now - HISTORY).timestamp() * 1000), int(now.timestamp() * 1000)
    return binance_public.hourly_bars(source, coin + "USDT", start, end)


def fetch_year(source: PublicReader, coin: str, now: datetime | None = None) -> pd.DataFrame:
    """A year of daily bars for a coin against USDT; empty when there are none."""
    now = now or datetime.now(UTC)
    start = int((now - timedelta(days=YEAR_DAYS + 5)).timestamp() * 1000)
    return binance_public.daily_bars(source, coin + "USDT", start, int(now.timestamp() * 1000))
