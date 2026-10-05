"""Realised volatility from hourly bars. Pure functions.

Both functions return one row per day with `rv` (the realised volatility), `returns`
(how many returns went into it), and `flagged` (True where data was too thin and `rv`
is empty). A day's value uses only bars of that day, so it is known once the day ends.
"""

from typing import Any

import numpy as np
import pandas as pd

from radar.features.returns import log_returns

HOUR = pd.Timedelta(hours=1)
MIN_CRYPTO_RETURNS = 18


def realised_volatility_crypto(
    hourly_close: pd.Series, min_returns: int = MIN_CRYPTO_RETURNS
) -> pd.DataFrame:
    """Square root of the sum of squared hourly log returns, per UTC day.

    `hourly_close` is indexed by bar start (UTC). The return of the 00:00 bar runs from
    the previous day's last close, so a full day has 24 returns. A return across a
    missing bar is dropped; a day with fewer than `min_returns` has no value.
    """
    returns = log_returns(hourly_close, step=HOUR)
    day = pd.DatetimeIndex(returns.index).floor("D")
    squared = (returns**2).groupby(day).sum(min_count=1)
    count = returns.notna().groupby(day).sum()
    frame = pd.DataFrame({"rv": np.sqrt(squared), "returns": count})
    frame["flagged"] = frame["returns"] < min_returns
    frame.loc[frame["flagged"], "rv"] = np.nan
    return frame


def realised_volatility_stock(
    hourly_close: pd.Series, daily: pd.DataFrame, schedule: pd.DataFrame
) -> pd.DataFrame:
    """Realised volatility per trading session, overnight move included.

    For each session: the squared overnight log return (previous session's close to this
    session's open) plus the squared log returns between the open and each hourly close
    inside regular hours. This covers the full day, as the crypto figure does.

    `hourly_close` is indexed by bar start (UTC). `daily` is indexed by session date with
    columns `open` and `close`. `schedule` is `nyse_schedule(...)`. A session with a
    missing regular-hours bar, or with no previous close, has no value and is flagged.
    """
    rows = []
    previous_close = np.nan
    opens: list[pd.Timestamp] = schedule["open"].tolist()
    closes: list[pd.Timestamp] = schedule["close"].tolist()
    open_by_session: dict[Any, float] = daily["open"].astype(float).to_dict()
    close_by_session: dict[Any, float] = daily["close"].astype(float).to_dict()
    for session, opened, closed in zip(schedule.index, opens, closes, strict=True):
        if session not in open_by_session:
            previous_close = np.nan
            continue
        day_open = open_by_session[session]
        day_close = close_by_session[session]
        expected = pd.date_range(opened.floor("h"), closed, freq="h", inclusive="left")
        bars = hourly_close.reindex(expected)
        path = np.concatenate([[day_open], bars.to_numpy(dtype=float)])
        intraday = np.diff(np.log(path))
        overnight = np.log(day_open / previous_close)
        complete = bool(bars.notna().all()) and bool(np.isfinite(overnight))
        total = overnight**2 + float(np.sum(intraday**2))
        rows.append(
            {
                "session": session,
                "rv": np.sqrt(total) if complete else np.nan,
                "returns": int(bars.notna().sum()) + int(np.isfinite(overnight)),
                "flagged": not complete,
            }
        )
        previous_close = day_close
    frame = pd.DataFrame(rows, columns=["session", "rv", "returns", "flagged"])
    return frame.set_index("session")
