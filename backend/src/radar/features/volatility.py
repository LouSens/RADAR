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
    opened = pd.DatetimeIndex(schedule["open"]).tz_convert("UTC").floor("h")
    closed = pd.DatetimeIndex(schedule["close"]).tz_convert("UTC")
    # Hourly bars each session should have, looked up in one pass.
    hours = np.ceil((closed - opened) / HOUR).astype(int)
    owner = np.repeat(np.arange(len(schedule)), hours)
    offset = np.concatenate([np.arange(n) for n in hours]) if len(hours) else np.array([], int)
    expected = opened[owner] + pd.to_timedelta(offset, unit="h")
    prices = hourly_close.reindex(expected).to_numpy(dtype=float)
    ends = np.cumsum(hours)

    open_by_session: dict[Any, float] = daily["open"].astype(float).to_dict()
    close_by_session: dict[Any, float] = daily["close"].astype(float).to_dict()
    rows = []
    previous_close = np.nan
    for position, session in enumerate(schedule.index):
        if session not in open_by_session:
            previous_close = np.nan
            continue
        day_open = open_by_session[session]
        bars = prices[ends[position] - hours[position] : ends[position]]
        intraday = np.diff(np.log(np.concatenate([[day_open], bars])))
        overnight = np.log(day_open / previous_close)
        present = int(np.isfinite(bars).sum())
        complete = present == len(bars) and bool(np.isfinite(overnight))
        total = overnight**2 + float(np.sum(intraday**2))
        rows.append(
            {
                "session": session,
                "rv": np.sqrt(total) if complete else np.nan,
                "returns": present + int(np.isfinite(overnight)),
                "flagged": not complete,
            }
        )
        previous_close = close_by_session[session]
    frame = pd.DataFrame(rows, columns=["session", "rv", "returns", "flagged"])
    return frame.set_index("session")
