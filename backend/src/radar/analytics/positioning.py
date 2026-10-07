"""How crowded one side of a market is, from positioning reports and funding rates
(decisions 066 and 067).

Pure functions. No lookahead: a reading is compared only with the readings before it,
and a weekly report is dated on the day it could first be acted on, not the day it
describes.
"""

import numpy as np
import pandas as pd

MODEL_VERSION = "positioning-1"
REPORT_LAG_DAYS = 6
WEEKS = 156
CROWDED = 1.5
PAYMENTS = 270
CROWDED_FUNDING = 2.0


def net_share(report: pd.DataFrame) -> pd.Series:
    """Long minus short, as a share of all open contracts."""
    return ((report["long"] - report["short"]) / report["open_interest"]).rename("net")


def unusual(readings: pd.Series, window: int) -> pd.Series:
    """How far each reading sits from the average of the `window` readings before it,
    in units of their spread. The reading itself is not in its own yardstick."""
    before = readings.shift(1)
    spread = before.rolling(window).std()
    return ((readings - before.rolling(window).mean()) / spread.where(spread > 0)).rename("unusual")


def known_from(
    report_days: pd.DatetimeIndex, trading_days: pd.DatetimeIndex, lag_days: int = REPORT_LAG_DAYS
) -> pd.DatetimeIndex:
    """The first trading day on or after `lag_days` past each report's date: when a
    report about a Tuesday, published on the Friday, can first be acted on at a close.
    Reports with no such day yet are dated past the end and drop out on alignment."""
    earliest = report_days + pd.Timedelta(days=lag_days)
    rows = trading_days.searchsorted(earliest, side="left")
    inside = rows < len(trading_days)
    stamps = np.full(len(report_days), np.datetime64("NaT"), dtype="datetime64[ns]")
    stamps[inside] = trading_days.to_numpy(dtype="datetime64[ns]")[rows[inside]]
    return pd.DatetimeIndex(stamps)


def on_trading_days(
    readings: pd.Series, trading_days: pd.DatetimeIndex, lag_days: int = REPORT_LAG_DAYS
) -> pd.Series:
    """Each trading day's latest reading that was already known that day."""
    stamps = known_from(pd.DatetimeIndex(readings.index), trading_days, lag_days)
    known = pd.Series(readings.to_numpy(), index=stamps)
    known = known[known.index.notna()]
    known = known[~known.index.duplicated(keep="last")]
    return known.reindex(trading_days).ffill()


def run_starts(flags: pd.Series) -> list[pd.Timestamp]:
    """The first stamp of each unbroken run of true values: a run counts once."""
    on = flags.fillna(False).astype(bool)
    return list(on.index[(on & ~on.shift(1, fill_value=False)).to_numpy()])


def hold_unless_crowded(reading: pd.Series, level: float = CROWDED) -> pd.Series:
    """Half while the reading says "crowded long", everything otherwise."""
    return pd.Series(np.where(reading >= level, 0.5, 1.0), index=reading.index).where(
        reading.notna()
    )
