"""Crowding readings and the three ways of paying in, on figures worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import buying, positioning
from radar.models import direction


def test_net_share_is_long_minus_short_over_open_interest() -> None:
    report = pd.DataFrame({"long": [300.0], "short": [100.0], "open_interest": [1000.0]})
    assert positioning.net_share(report).tolist() == [0.2]


def test_a_reading_is_measured_against_the_readings_before_it_only() -> None:
    readings = pd.Series([1.0, 3.0, 1.0, 3.0, 10.0, 2.0])
    result = positioning.unusual(readings, window=4)
    assert result.iloc[:4].isna().all()
    # The four before the fifth are 1, 3, 1, 3: average 2, spread 1.1547.
    assert result.iloc[4] == pytest.approx((10 - 2) / np.std([1, 3, 1, 3], ddof=1))
    changed = readings.copy()
    changed.iloc[5] = 99.0
    assert positioning.unusual(changed, window=4).iloc[:5].equals(result.iloc[:5])


def test_a_report_about_a_tuesday_is_known_from_the_monday_after() -> None:
    trading = pd.bdate_range("2024-01-01", "2024-01-31")
    reports = pd.DatetimeIndex(["2024-01-02", "2024-01-09", "2024-01-30"])  # Tuesdays
    known = positioning.known_from(reports, trading)
    assert known[0] == pd.Timestamp("2024-01-08")
    assert known[1] == pd.Timestamp("2024-01-15")
    assert pd.isna(known[2])  # its Monday is past the end of the prices

    readings = pd.Series([1.0, 2.0, 3.0], index=reports)
    daily = positioning.on_trading_days(readings, trading)
    assert daily.loc[:"2024-01-05"].isna().all()
    assert daily.loc["2024-01-08"] == 1.0
    assert daily.loc["2024-01-12"] == 1.0
    assert daily.loc["2024-01-15"] == 2.0
    assert daily.iloc[-1] == 2.0


def test_a_run_of_crowded_weeks_counts_once() -> None:
    flags = pd.Series([False, True, True, False, True, np.nan, True], index=range(7))
    assert positioning.run_starts(flags) == [1, 4, 6]


def test_half_is_held_while_crowded_long() -> None:
    reading = pd.Series([np.nan, 0.0, 1.5, 2.0, -3.0])
    weight = positioning.hold_unless_crowded(reading)
    assert np.isnan(weight.iloc[0])
    assert weight.iloc[1:].tolist() == [1.0, 0.5, 0.5, 1.0]


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def test_paying_in_on_schedule_buys_at_each_payment() -> None:
    close = pd.Series([10.0, 10.0, 20.0, 20.0], index=days(4))
    replay = buying.on_schedule(close, every=2, cost=0.0)
    # 0.1 units at 10, then 0.05 units at 20: 0.15 units worth 3 for 2 paid.
    assert replay["paid"].tolist() == [1.0, 1.0, 2.0, 2.0]
    assert replay["value"].tolist() == pytest.approx([1.0, 1.0, 3.0, 3.0])
    result = buying.outcome(replay)
    assert result.end == pytest.approx(1.5)
    assert result.worst == pytest.approx(0.0)
    assert result.cash_share == 0.0

    half = buying.on_schedule(close, every=2, cost=0.0, cash_share=0.5)
    assert half["cash"].tolist() == [0.5, 0.5, 1.0, 1.0]
    assert half["value"].iloc[-1] == pytest.approx(1.0 + 0.075 * 20)


def test_a_gain_that_turns_into_a_loss_is_sold_and_bought_back_on_a_new_high() -> None:
    #                  0     1     2    3    4    5    6     7
    close = pd.Series([10.0, 11.0, 9.0, 8.0, 7.0, 8.0, 9.5, 12.0], index=days(8))
    replay, trades = buying.cut_at_break_even(close, every=100, cost=0.0, window=2)
    # One payment at 10. Worth 1.1 on day 1 (armed), 0.9 on day 2: sold for 0.9.
    assert replay["cash"].iloc[2] == pytest.approx(0.9)
    assert replay["value"].iloc[4] == pytest.approx(0.9)  # out while it falls to 7
    # Day 5 (8) is not above the high of days 3 and 4 (8); day 6 (9.5) is: bought back.
    assert replay["cash"].iloc[5] == pytest.approx(0.9)
    assert replay["cash"].iloc[6] == 0.0
    assert replay["value"].iloc[7] == pytest.approx(0.9 / 9.5 * 12.0)
    assert trades == 2


def test_a_holding_that_never_got_ahead_is_not_sold() -> None:
    close = pd.Series([10.0, 9.0, 8.0, 9.0], index=days(4))
    replay, trades = buying.cut_at_break_even(close, every=100, cost=0.0)
    assert trades == 0
    assert replay["cash"].eq(0.0).all()


def test_waiting_for_dips_keeps_cash_until_the_price_has_dropped() -> None:
    close = pd.Series([10.0, 10.0, 10.0, 9.5, 8.9, 12.0], index=days(6))
    replay, trades = buying.wait_for_dips(close, every=2, cost=0.0, dip=0.10, window=2)
    assert replay["cash"].tolist() == [1.0, 1.0, 2.0, 2.0, 0.0, 0.0]
    # Day 4's close of 8.9 is 11% under the high of the two days before (10).
    assert trades == 1
    assert replay["value"].iloc[-1] == pytest.approx(3.0 / 8.9 * 12.0)


@pytest.mark.parametrize("name", ["schedule", "cut", "dips"])
def test_what_was_done_up_to_a_day_does_not_change_when_later_prices_change(name: str) -> None:
    rng = np.random.default_rng(4)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 500))), index=days(500))
    changed = close.copy()
    changed.iloc[300:] = changed.iloc[300:] * 0.5

    def run(prices: pd.Series) -> pd.DataFrame:
        if name == "schedule":
            return buying.on_schedule(prices)
        if name == "cut":
            return buying.cut_at_break_even(prices)[0]
        return buying.wait_for_dips(prices)[0]

    assert run(close).iloc[:300].equals(run(changed).iloc[:300])


def test_outside_inputs_of_a_bar_use_only_what_was_known_by_then() -> None:
    rng = np.random.default_rng(6)
    index = pd.date_range("2024-01-01", periods=600, freq="h", tz="UTC")
    volume = pd.Series(rng.uniform(1, 3, 600), index=index)
    frame = pd.DataFrame({"volume": volume, "taker_buy": volume * rng.uniform(0.3, 0.7, 600)})
    paid = pd.date_range("2023-12-01", periods=180, freq="8h", tz="UTC") + pd.Timedelta(
        milliseconds=2
    )
    funding = pd.Series(rng.normal(0.0001, 0.0001, 180), index=paid)

    table = direction.outside_summary(frame, funding)
    assert table["buy_1"].between(0.3, 0.7).all()
    # A payment at 08:00 is first seen on the bar that opens at 08:00.
    at_eight = pd.Timestamp("2024-01-05 08:00", tz="UTC")
    assert table.loc[at_eight, "funding"] == funding.loc[at_eight + pd.Timedelta(milliseconds=2)]
    assert table.loc[at_eight - pd.Timedelta(hours=1), "funding"] != table.loc[at_eight, "funding"]

    cut = index[400]
    later_frame, later_funding = frame.copy(), funding.copy()
    later_frame.loc[cut:, "taker_buy"] = 0.0
    later_funding.loc[cut:] = 9.0
    assert (
        direction.outside_summary(later_frame, later_funding)
        .loc[: index[399]]
        .equals(table.loc[: index[399]])
    )
    assert (
        direction.outside_bars(later_frame, later_funding)
        .loc[: index[399]]
        .equals(direction.outside_bars(frame, funding).loc[: index[399]])
    )
