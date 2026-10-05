"""Gap detection: compare stored bar timestamps with the calendar they should follow.

Gaps are recorded, never filled. Crypto trades continuously; stocks follow the New York
Stock Exchange calendar, including holidays and early closes.
"""

from dataclasses import dataclass, field
from functools import cache
from typing import Any

import exchange_calendars as xcals
import pandas as pd

NEW_YORK = "America/New_York"
FREQUENCY = {"1Hour": "h", "1Day": "D"}
STEP = {"1Hour": pd.Timedelta(hours=1), "1Day": pd.Timedelta(days=1)}


@dataclass(frozen=True)
class Gap:
    start: pd.Timestamp
    end: pd.Timestamp
    missing: int


@dataclass
class GapReport:
    expected: int
    present: int
    missing: int
    # Stored bars outside the expected calendar, for example extended-hours stock bars.
    outside_calendar: int
    gaps: list[Gap] = field(default_factory=list)

    @property
    def missing_share(self) -> float:
        return self.missing / self.expected if self.expected else 0.0


@cache
def _nyse() -> Any:
    return xcals.get_calendar("XNYS")


def _schedule(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    calendar = _nyse()
    start = max(first.tz_convert(NEW_YORK).tz_localize(None).normalize(), calendar.first_session)
    end = min(last.tz_convert(NEW_YORK).tz_localize(None).normalize(), calendar.last_session)
    schedule: pd.DataFrame = calendar.schedule.loc[start:end]
    return schedule


def expected_crypto(first: pd.Timestamp, last: pd.Timestamp, timeframe: str) -> pd.DatetimeIndex:
    """Every hour, or every UTC midnight, from the first bar to the last."""
    return pd.date_range(first, last, freq=FREQUENCY[timeframe])


def expected_stock_days(first: pd.Timestamp, last: pd.Timestamp) -> pd.DatetimeIndex:
    """One bar per trading session, stamped at midnight New York time."""
    sessions = _schedule(first, last).index
    stamps = pd.DatetimeIndex(sessions).tz_localize(NEW_YORK).tz_convert("UTC")
    return stamps[(stamps >= first) & (stamps <= last)]


def expected_stock_hours(first: pd.Timestamp, last: pd.Timestamp) -> pd.DatetimeIndex:
    """Hourly bars that overlap regular trading hours, early closes included."""
    stamps: list[pd.Timestamp] = []
    schedule = _schedule(first, last)
    opens: list[pd.Timestamp] = schedule["open"].tolist()
    closes: list[pd.Timestamp] = schedule["close"].tolist()
    for session_open, session_close in zip(opens, closes, strict=True):
        opened = session_open.tz_convert("UTC").floor("h")
        closed = session_close.tz_convert("UTC")
        stamps.extend(pd.date_range(opened, closed, freq="h", inclusive="left"))
    index = pd.DatetimeIndex(stamps)
    return index[(index >= first) & (index <= last)]


def expected_index(
    asset_class: str, timeframe: str, first: pd.Timestamp, last: pd.Timestamp
) -> pd.DatetimeIndex:
    if asset_class == "crypto":
        return expected_crypto(first, last, timeframe)
    if timeframe == "1Day":
        return expected_stock_days(first, last)
    return expected_stock_hours(first, last)


def find_gaps(expected: pd.DatetimeIndex, actual: pd.DatetimeIndex) -> GapReport:
    """Report which expected timestamps are absent, grouped into consecutive runs."""
    missing = expected.difference(actual)
    report = GapReport(
        expected=len(expected),
        present=len(expected.intersection(actual)),
        missing=len(missing),
        outside_calendar=len(actual.difference(expected)),
    )
    if len(missing) == 0:
        return report
    # A new run starts wherever a missing stamp is not the next expected stamp.
    position = pd.Series(expected.get_indexer(missing), index=missing)
    run = (position.diff() != 1).cumsum()
    for _, stamps in position.groupby(run):
        report.gaps.append(Gap(start=stamps.index[0], end=stamps.index[-1], missing=len(stamps)))
    return report
