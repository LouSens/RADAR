"""Market calendars. Stocks follow the New York Stock Exchange; crypto never closes."""

from functools import cache
from typing import Any

import exchange_calendars as xcals
import pandas as pd

NEW_YORK = "America/New_York"


@cache
def _nyse() -> Any:
    return xcals.get_calendar("XNYS")


def nyse_schedule(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """Trading sessions that overlap the span between two instants.

    A session is included when it closes at or after `first` and opens at or before
    `last`. Indexed by session date (timezone-naive midnight). Columns `open` and
    `close` are UTC instants and reflect holidays and early closes.
    """
    calendar = _nyse()
    day = pd.Timedelta(days=1)
    start = max(
        first.tz_convert(NEW_YORK).tz_localize(None).normalize() - day, calendar.first_session
    )
    end = min(last.tz_convert(NEW_YORK).tz_localize(None).normalize() + day, calendar.last_session)
    nearby: pd.DataFrame = calendar.schedule.loc[start:end, ["open", "close"]]
    overlaps = (nearby["close"] >= first) & (nearby["open"] <= last)
    return nearby[overlaps]


def session_of(stamps: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Session date of stock daily-bar stamps, which sit at midnight New York time."""
    return stamps.tz_convert(NEW_YORK).tz_localize(None).normalize()
