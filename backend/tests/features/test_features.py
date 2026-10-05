"""Feature builders on hand-built examples, including a weekend, and no-lookahead proofs."""

import math

import numpy as np
import pandas as pd
import pytest

from radar.features.calendars import nyse_schedule, session_of
from radar.features.panels import crypto_panel, mixed_panel
from radar.features.returns import daily_range, log_returns, trailing_zscore
from radar.features.volatility import (
    realised_volatility_crypto,
    realised_volatility_stock,
    smoothed_log_volatility,
)


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


def hourly(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(ts(start), ts(end), freq="h")


# --- returns ---------------------------------------------------------------------------


def test_log_returns_skip_missing_bars_when_a_step_is_given() -> None:
    index = pd.DatetimeIndex(
        [ts("2024-01-01 00:00"), ts("2024-01-01 01:00"), ts("2024-01-01 03:00")]
    )
    prices = pd.Series([100.0, 110.0, 121.0], index=index)
    plain = log_returns(prices)
    assert plain.iloc[1] == pytest.approx(math.log(1.1))
    assert plain.iloc[2] == pytest.approx(math.log(1.1))
    stepped = log_returns(prices, step=pd.Timedelta(hours=1))
    assert stepped.iloc[1] == pytest.approx(math.log(1.1))
    assert pd.isna(stepped.iloc[2])  # two hours apart: not a one-hour return


def test_daily_range() -> None:
    result = daily_range(pd.Series([110.0]), pd.Series([100.0]))
    assert result.iloc[0] == pytest.approx(math.log(1.1))


def test_trailing_zscore_uses_only_earlier_values() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 100.0, 5.0])
    z = trailing_zscore(values, window=3)
    assert z.iloc[:3].isna().all()  # not enough history yet
    # At index 4 the window is [2, 3, 4]: mean 3, sample deviation 1.
    assert z.iloc[4] == pytest.approx(97.0)
    # The spike at index 4 does not affect its own baseline, only later ones.
    changed = values.copy()
    changed.iloc[5] = -999.0
    assert trailing_zscore(changed, window=3).iloc[:5].equals(z.iloc[:5])


# --- realised volatility ---------------------------------------------------------------


def test_crypto_realised_volatility_matches_a_hand_calculation() -> None:
    index = hourly("2024-01-01 00:00", "2024-01-03 23:00")
    # Every hourly log return is exactly 0.01.
    close = pd.Series(100 * np.exp(0.01 * np.arange(len(index))), index=index)
    rv = realised_volatility_crypto(close)
    assert rv.loc[ts("2024-01-02"), "returns"] == 24
    assert rv.loc[ts("2024-01-02"), "rv"] == pytest.approx(0.01 * math.sqrt(24))
    # The first day has no return for its first bar: 23 returns, still enough.
    assert rv.loc[ts("2024-01-01"), "returns"] == 23
    assert not rv.loc[ts("2024-01-01"), "flagged"]


def test_crypto_day_with_too_few_bars_has_no_value() -> None:
    index = hourly("2024-01-01 00:00", "2024-01-02 23:00")
    close = pd.Series(100 * np.exp(0.01 * np.arange(len(index))), index=index)
    thin = close.drop(index[30:44])  # 14 bars missing on the second day
    rv = realised_volatility_crypto(thin)
    assert rv.loc[ts("2024-01-02"), "flagged"]
    assert pd.isna(rv.loc[ts("2024-01-02"), "rv"])
    assert rv.loc[ts("2024-01-01"), "rv"] == pytest.approx(0.01 * math.sqrt(23))


def test_crypto_realised_volatility_has_no_lookahead() -> None:
    index = hourly("2024-01-01 00:00", "2024-01-04 23:00")
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(index)))), index=index)
    full = realised_volatility_crypto(close)
    changed = close.copy()
    changed[changed.index >= ts("2024-01-03")] *= 5.0
    again = realised_volatility_crypto(changed)
    assert again.loc[: ts("2024-01-02"), "rv"].equals(full.loc[: ts("2024-01-02"), "rv"])


def test_stock_realised_volatility_adds_the_overnight_move() -> None:
    # Tuesday 2024-01-16 and Wednesday 2024-01-17: regular sessions, 14:30 to 21:00 UTC.
    schedule = nyse_schedule(ts("2024-01-16"), ts("2024-01-17 23:00"))
    assert len(schedule) == 2
    sessions = pd.DatetimeIndex(schedule.index)
    daily = pd.DataFrame({"open": [100.0, 102.0], "close": [101.0, 102.0]}, index=sessions)
    # Wednesday: opens at 102 and every hourly close stays at 102, so only the overnight
    # move from 101 to 102 contributes.
    bars = hourly("2024-01-17 14:00", "2024-01-17 20:00")
    hourly_close = pd.Series(102.0, index=bars)
    rv = realised_volatility_stock(hourly_close, daily, schedule)

    wednesday = sessions[1]
    assert rv.loc[wednesday, "rv"] == pytest.approx(abs(math.log(102 / 101)))
    assert rv.loc[wednesday, "returns"] == 8  # seven hourly bars plus the overnight return
    assert not rv.loc[wednesday, "flagged"]
    # Tuesday has no previous close and no hourly bars here: no value.
    assert rv.loc[sessions[0], "flagged"]
    assert pd.isna(rv.loc[sessions[0], "rv"])


def test_stock_session_with_a_missing_hourly_bar_is_flagged() -> None:
    schedule = nyse_schedule(ts("2024-01-16"), ts("2024-01-17 23:00"))
    sessions = pd.DatetimeIndex(schedule.index)
    daily = pd.DataFrame({"open": [100.0, 102.0], "close": [101.0, 102.0]}, index=sessions)
    bars = hourly("2024-01-17 14:00", "2024-01-17 20:00").delete(3)
    rv = realised_volatility_stock(pd.Series(102.0, index=bars), daily, schedule)
    assert rv.loc[sessions[1], "flagged"]


# --- panels ----------------------------------------------------------------------------


def test_session_of_reads_midnight_new_york_stamps() -> None:
    stamps = pd.DatetimeIndex([ts("2024-01-16 05:00"), ts("2024-07-01 04:00")])
    assert list(session_of(stamps)) == [pd.Timestamp("2024-01-16"), pd.Timestamp("2024-07-01")]


def test_crypto_panel_runs_seven_days_a_week_and_leaves_gaps_empty() -> None:
    days = pd.date_range(ts("2024-01-05"), ts("2024-01-09"), freq="D")  # Friday to Tuesday
    close = pd.DataFrame({"BTC/USD": [100.0, 110.0, 121.0, 121.0, 133.1]}, index=days)
    panel = crypto_panel(close)
    assert panel["BTC/USD"].iloc[1] == pytest.approx(math.log(1.1))  # Saturday
    assert panel["BTC/USD"].iloc[2] == pytest.approx(math.log(1.1))  # Sunday
    assert len(panel) == 5

    holed = crypto_panel(close.drop(days[2]))
    assert pd.isna(holed["BTC/USD"].loc[days[2]])
    assert pd.isna(holed["BTC/USD"].loc[days[3]])  # no return across the missing day
    assert holed["BTC/USD"].loc[days[4]] == pytest.approx(math.log(133.1 / 121.0))


def weekend_example() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Friday 2024-01-05 to Tuesday 2024-01-09. New York closes at 21:00 UTC in January.

    Bitcoin is 100 until Friday's stock close, climbs to 110 over the weekend, and stays
    there. GLD closes at 50 on Friday, 51 on Monday, 51 on Tuesday.
    """
    schedule = nyse_schedule(ts("2024-01-05"), ts("2024-01-09 23:00"))
    assert [d.day for d in schedule.index] == [5, 8, 9]
    stocks = pd.DataFrame({"GLD": [50.0, 51.0, 51.0]}, index=pd.DatetimeIndex(schedule.index))
    bars = hourly("2024-01-04 00:00", "2024-01-09 23:00")
    # A bar's close is the price at the end of its hour.
    price = np.where(bars + pd.Timedelta(hours=1) <= ts("2024-01-05 21:00"), 100.0, 110.0)
    crypto = pd.DataFrame({"BTC/USD": price}, index=bars)
    return stocks, crypto, schedule


def test_mixed_panel_puts_the_weekend_crypto_move_in_mondays_return() -> None:
    stocks, crypto, schedule = weekend_example()
    panel = mixed_panel(stocks, crypto, schedule)

    assert list(panel.returns.index) == [
        ts("2024-01-05 21:00"),
        ts("2024-01-08 21:00"),
        ts("2024-01-09 21:00"),
    ]
    friday, monday, tuesday = panel.returns.index
    # Friday's price is taken at the stock close: Bitcoin is still 100 there.
    assert panel.prices.loc[friday, "BTC/USD"] == 100.0
    # The whole weekend move sits in Monday's row, beside gold's Friday-to-Monday move.
    assert panel.returns.loc[monday, "BTC/USD"] == pytest.approx(math.log(110 / 100))
    assert panel.returns.loc[monday, "GLD"] == pytest.approx(math.log(51 / 50))
    assert panel.returns.loc[tuesday, "BTC/USD"] == pytest.approx(0.0)
    assert panel.returns.loc[tuesday, "GLD"] == pytest.approx(0.0)
    assert not panel.filled.to_numpy().any()
    assert list(panel.sessions) == list(schedule.index)


def test_mixed_panel_has_no_lookahead() -> None:
    stocks, crypto, schedule = weekend_example()
    before = mixed_panel(stocks, crypto, schedule)
    later = crypto.copy()
    # Change everything after Monday's close, including the very next bar.
    later.loc[later.index >= ts("2024-01-08 21:00"), "BTC/USD"] = 999.0
    stocks_later = stocks.copy()
    stocks_later.iloc[2] = 999.0
    after = mixed_panel(stocks_later, later, schedule)
    monday = ts("2024-01-08 21:00")
    assert after.prices.loc[:monday].equals(before.prices.loc[:monday])
    assert after.returns.loc[:monday].equals(before.returns.loc[:monday])


def test_mixed_panel_fills_a_missing_close_bar_and_flags_it() -> None:
    stocks, crypto, schedule = weekend_example()
    monday = ts("2024-01-08 21:00")
    # Remove the bar that ends at Monday's close and the one before it.
    holed = crypto.drop([ts("2024-01-08 20:00"), ts("2024-01-08 19:00")])
    panel = mixed_panel(stocks, holed, schedule)
    assert panel.prices.loc[monday, "BTC/USD"] == 110.0
    assert panel.filled.loc[monday, "BTC/USD"]
    assert not panel.filled.loc[monday, "GLD"]

    # With no bar inside the fill limit the price is left empty, never invented.
    long_gap = crypto[(crypto.index < ts("2024-01-08 12:00")) | (crypto.index > monday)]
    empty = mixed_panel(stocks, long_gap, schedule)
    assert pd.isna(empty.prices.loc[monday, "BTC/USD"])
    assert not empty.filled.loc[monday, "BTC/USD"]


def test_mixed_panel_follows_daylight_saving_and_early_closes() -> None:
    # 2024-07-03 closed early at 13:00 New York (17:00 UTC); 2024-07-05 closed at 20:00 UTC.
    schedule = nyse_schedule(ts("2024-07-03"), ts("2024-07-05 23:00"))
    stocks = pd.DataFrame({"GLD": [50.0, 50.0]}, index=pd.DatetimeIndex(schedule.index))
    bars = hourly("2024-07-02 00:00", "2024-07-05 23:00")
    crypto = pd.DataFrame({"BTC/USD": np.arange(len(bars), dtype=float) + 1}, index=bars)
    panel = mixed_panel(stocks, crypto, schedule)
    assert list(panel.prices.index) == [ts("2024-07-03 17:00"), ts("2024-07-05 20:00")]
    # Each price is the close of the bar that starts one hour before the session close.
    assert panel.prices["BTC/USD"].iloc[0] == crypto.loc[ts("2024-07-03 16:00"), "BTC/USD"]
    assert panel.prices["BTC/USD"].iloc[1] == crypto.loc[ts("2024-07-05 19:00"), "BTC/USD"]


def test_smoothed_log_volatility_is_trailing_only() -> None:
    rng = np.random.default_rng(4)
    index = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    realised = pd.Series(np.exp(rng.normal(-4, 0.5, 200)), index=index)
    smooth = smoothed_log_volatility(realised)
    # Smoother than the raw series, and on the same level.
    raw = pd.Series(np.log(realised.to_numpy()), index=index)
    assert smooth.diff().std() < raw.diff().std() / 2
    assert smooth.mean() == pytest.approx(raw.mean(), abs=0.1)
    # Changing later days leaves earlier values untouched.
    changed = realised.copy()
    changed.iloc[150:] = 10.0
    assert smoothed_log_volatility(changed).iloc[:150].equals(smooth.iloc[:150])
