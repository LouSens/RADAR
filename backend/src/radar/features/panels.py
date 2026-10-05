"""Aligned return panels (spec 7.4). Pure functions.

Two panels, because crypto trades every day and stocks do not:

- The crypto panel has one row per UTC day, seven days a week.
- The mixed panel has one row per New York Stock Exchange session, sampled at that
  session's close (16:00 New York, earlier on half days). Crypto prices are taken at the
  same instant, so a weekend's crypto move lands in Monday's return, beside the stock
  move it should be compared with.

No lookahead: a row uses only prices at or before its own timestamp.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from radar.features.returns import log_frame

DAY = pd.Timedelta(days=1)
HOUR = pd.Timedelta(hours=1)
# A missing crypto bar at the close may be replaced by the latest earlier bar this recent.
MAX_FILL = pd.Timedelta(hours=6)


def crypto_panel(daily_close: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns on UTC day boundaries.

    `daily_close` has one column per symbol, indexed by the day's start (UTC). The
    return stamped at day `d` covers that day and is known when it ends. A return across
    a missing day is left empty.
    """
    full = daily_close.asfreq("D")
    return log_frame(full).diff()


def _price_at(
    series: pd.Series, wanted: pd.DatetimeIndex, max_fill: pd.Timedelta
) -> tuple[np.ndarray, np.ndarray]:
    """Price of the bar at each wanted stamp, else the latest earlier bar within `max_fill`.

    Returns the prices and a mask that is True where an earlier bar was used.
    """
    known = series.dropna()
    left = pd.DataFrame({"want": wanted.as_unit("ns")})
    right = pd.DataFrame(
        {"ts": pd.DatetimeIndex(known.index).as_unit("ns"), "price": known.to_numpy(dtype=float)}
    )
    matched = pd.merge_asof(
        left, right, left_on="want", right_on="ts", direction="backward", tolerance=max_fill
    )
    used_earlier = matched["ts"].notna() & (matched["ts"] != matched["want"])
    return matched["price"].to_numpy(dtype=float), used_earlier.to_numpy(dtype=bool)


@dataclass(frozen=True)
class MixedPanel:
    """Prices and returns per trading session, indexed by the session's close (UTC)."""

    prices: pd.DataFrame
    returns: pd.DataFrame
    # True where a crypto price was carried forward from an earlier hourly bar.
    filled: pd.DataFrame
    # The session date of each row.
    sessions: pd.DatetimeIndex


def mixed_panel(
    stock_daily_close: pd.DataFrame,
    crypto_hourly_close: pd.DataFrame,
    schedule: pd.DataFrame,
    max_fill: pd.Timedelta = MAX_FILL,
) -> MixedPanel:
    """Sample every asset at each session's close and take session-to-session returns.

    `stock_daily_close` is indexed by session date. `crypto_hourly_close` is indexed by
    bar start (UTC); the price at the close is the close of the hourly bar that ends
    there. `schedule` is `nyse_schedule(...)`.
    """
    closes = pd.DatetimeIndex(schedule["close"]).tz_convert("UTC")
    sessions = pd.DatetimeIndex(schedule.index)

    stocks = stock_daily_close.reindex(sessions)
    stocks.index = closes

    # The bar that ends at the close starts one hour earlier.
    wanted = closes - HOUR
    crypto = pd.DataFrame(index=closes, columns=crypto_hourly_close.columns, dtype=float)
    filled_crypto = pd.DataFrame(False, index=closes, columns=crypto_hourly_close.columns)
    for column in crypto_hourly_close.columns:
        price, was_filled = _price_at(crypto_hourly_close[column], wanted, max_fill)
        crypto[column] = price
        filled_crypto[column] = was_filled

    prices = pd.concat([stocks, crypto], axis=1)
    filled = pd.concat(
        [pd.DataFrame(False, index=closes, columns=stocks.columns), filled_crypto], axis=1
    )
    returns = log_frame(prices).diff()
    return MixedPanel(prices=prices, returns=returns, filled=filled, sessions=sessions)
