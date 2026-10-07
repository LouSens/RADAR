"""Coins low in their range against coins high in it (decision 078). Pure functions.

Each week every coin is placed between the lowest and highest price of its last week and
month, the same way the app's check before buying does. The coins low in their range are
then set against the coins high in it by what followed.

No lookahead: a coin's place on a day uses that day and earlier days only; what followed
starts at that day's close.
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

MODEL_VERSION = "screening-1"
WEEK, MONTH = 7, 30
HIGH, LOW = 0.65, 0.35
MIN_HISTORY = 60
MIN_TRADED = 1_000_000.0
MIN_GROUP = 10


def place(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Each coin's place each day: where the close sits between the lowest low and
    highest high of the last week and of the last month, averaged. One column per coin."""

    def within(days: int) -> pd.DataFrame:
        top, bottom = high.rolling(days).max(), low.rolling(days).min()
        return (close - bottom) / (top - bottom).where(top > bottom)

    return (within(WEEK) + within(MONTH)) / 2


def eligible(close: pd.DataFrame, traded: pd.DataFrame) -> pd.DataFrame:
    """True where a coin has enough history and enough trading to count that day."""
    seen = close.notna().cumsum()
    busy = traded.rolling(MONTH).median()
    return (seen >= MIN_HISTORY) & (busy >= MIN_TRADED)


def ahead(close: pd.DataFrame, days: int) -> pd.DataFrame:
    """Each coin's return over the next `days` days; missing where they have not passed."""
    return close.shift(-days) / close - 1


class Week(BaseModel):
    day: str
    low_coins: int
    high_coins: int
    # Average return of each group less the middle coin's, and the low group's lead.
    low: float
    high: float
    lead: float
    # The share of low coins that were up at all.
    low_up: float


def weekly(
    places: pd.DataFrame, counts: pd.DataFrame, later: pd.DataFrame, every: int = 1
) -> list[Week]:
    """One row per Monday (every `every`th one) with enough coins in both groups."""
    mondays = [day for day in places.index if day.dayofweek == 0][::every]
    rows: list[Week] = []
    for day in mondays:
        ok = counts.loc[day] & places.loc[day].notna() & later.loc[day].notna()
        if not ok.any():
            continue
        where, after = places.loc[day][ok], later.loc[day][ok]
        middle = float(after.median())
        low, high = after[where <= LOW], after[where >= HIGH]
        if len(low) < MIN_GROUP or len(high) < MIN_GROUP:
            continue
        rows.append(
            Week(
                day=str(day.date()),
                low_coins=len(low),
                high_coins=len(high),
                low=float(low.mean()) - middle,
                high=float(high.mean()) - middle,
                lead=float(low.mean() - high.mean()),
                low_up=float((low > 0).mean()),
            )
        )
    return rows


class Verdict(BaseModel):
    weeks: int
    lead: float
    # The share of resamples of weeks in which the low coins were not ahead.
    no_lead: float
    first_half: float
    second_half: float
    years_ahead: int
    years: int
    low_up: float
    passes: bool


def judge(rows: list[Week], mark: float, draws: int = 5000, seed: int = 7) -> Verdict | None:
    """The pass mark of decision 078 applied to the weekly leads."""
    if len(rows) < 20:
        return None
    lead = np.array([r.lead for r in rows])
    year = np.array([int(r.day[:4]) for r in rows])
    rng = np.random.default_rng(seed)
    means = lead[rng.integers(0, len(lead), size=(draws, len(lead)))].mean(axis=1)
    half = len(lead) // 2
    by_year = pd.Series(lead).groupby(year).mean()
    first, second = float(lead[:half].mean()), float(lead[half:].mean())
    average, no_lead = float(lead.mean()), float((means <= 0).mean())
    ahead_years = int((by_year > 0).sum())
    return Verdict(
        weeks=len(rows),
        lead=average,
        no_lead=no_lead,
        first_half=first,
        second_half=second,
        years_ahead=ahead_years,
        years=len(by_year),
        low_up=float(np.mean([r.low_up for r in rows])),
        passes=bool(
            average >= mark
            and no_lead < 0.05
            and first > 0
            and second > 0
            and ahead_years >= 0.6 * len(by_year)
        ),
    )
