"""The readings and the month arithmetic of decision 070, on figures worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import buying, technical


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def wandering(n: int = 500, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    spread = np.abs(rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {"high": close * (1 + spread), "low": close * (1 - spread), "close": close},
        index=days(n),
    )


def test_the_exponential_average_weights_recent_days_more() -> None:
    close = pd.Series([10.0, 10.0, 10.0, 20.0], index=days(4))
    result = technical.ema(close, 3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == pytest.approx(10.0)
    # Span 3 gives the newest day a weight of one half.
    assert result.iloc[3] == pytest.approx(15.0)


def test_the_fibonacci_level_sits_618_thousandths_down_the_latest_rise() -> None:
    # Three flat days at 100, a rise to 200 on the fourth, then quiet.
    high = pd.Series([101.0, 101.0, 101.0, 200.0, 150.0, 150.0], index=days(6))
    low = pd.Series([100.0, 90.0, 100.0, 190.0, 140.0, 140.0], index=days(6))
    levels = technical.fibonacci_level(high, low, window=3)
    assert levels["level"].iloc[:3].isna().all()
    # From day 3 the high is 200 and the low of the three days before it is 90.
    assert levels["floor"].iloc[3:].tolist() == [90.0, 90.0, 90.0]
    assert levels["level"].iloc[3] == pytest.approx(200 - 0.618 * 110)


def test_a_fibonacci_case_needs_the_low_at_the_level_and_the_close_above_the_start() -> None:
    high = pd.Series([101.0, 101.0, 101.0, 200.0, 150.0, 140.0], index=days(6))
    low = pd.Series([100.0, 90.0, 100.0, 190.0, 131.0, 80.0], index=days(6))
    close = pd.Series([100.0, 95.0, 100.0, 195.0, 135.0, 85.0], index=days(6))
    # The level is 132.02. Day 4 reaches it and closes above 90; day 5 closes under 90.
    cases = technical.fibonacci_cases(high, low, close, window=3)
    assert cases == [days(6)[4]]


def test_a_cross_is_dated_on_the_day_the_fast_average_goes_above() -> None:
    close = pd.Series([10.0] * 6 + [9.0, 8.0, 7.0, 12.0, 14.0], index=days(11))
    cases = technical.ema_cross_cases(close, fast=2, slow=4)
    fast, slow = technical.ema(close, 2), technical.ema(close, 4)
    assert len(cases) == 1
    day = cases[0]
    before = day - pd.Timedelta(days=1)
    assert fast[day] > slow[day]
    assert fast[before] <= slow[before]


def test_pullbacks_need_both_the_touch_and_the_rise_around_it() -> None:
    frame = wandering()
    low, close = frame["low"], frame["close"]
    quick, steady = technical.ema(close, 9), technical.ema(close, 13)
    for day in technical.short_pullback_cases(low, close):
        assert low[day] <= steady[day]
        assert quick[day] > steady[day]
    near, trend = technical.ema(close, 50), technical.ema(close, 200)
    found = technical.trend_pullback_cases(low, close)
    assert found
    for day in found:
        assert low[day] <= near[day]
        assert close[day] > trend[day]


def test_no_reading_on_a_day_changes_when_later_days_change() -> None:
    frame = wandering()
    cut = 400
    changed = frame.copy()
    changed.iloc[cut:] = changed.iloc[cut:] * 3
    early = frame.index[cut - 1]

    def found(f: pd.DataFrame) -> list[list[pd.Timestamp]]:
        return [
            technical.ema_cross_cases(f["close"]),
            technical.short_pullback_cases(f["low"], f["close"]),
            technical.trend_pullback_cases(f["low"], f["close"]),
            technical.fibonacci_cases(f["high"], f["low"], f["close"]),
        ]

    for before, after in zip(found(frame), found(changed), strict=True):
        assert [d for d in before if d <= early] == [d for d in after if d <= early]


def test_flags_mark_the_days_of_the_cases() -> None:
    index = days(4)
    assert technical.flags(index, [index[1], index[3]]).tolist() == [False, True, False, True]


def test_months_are_full_blocks_after_the_warm_up() -> None:
    assert buying.month_starts(days=50, every=21, warm_up=5).tolist() == [5, 26]
    assert buying.month_starts(days=47, every=21, warm_up=5).tolist() == [5, 26]
    assert buying.month_starts(days=46, every=21, warm_up=5).tolist() == [5]


def test_the_payment_goes_in_on_the_first_day_the_reading_is_on_or_the_last() -> None:
    on = np.zeros(12, dtype=bool)
    on[[2, 3, 11]] = True
    starts = np.array([0, 4, 8])
    # Month one: day 2. Month two: never, so its last day. Month three: day 3 of it.
    assert buying.day_paid(on, starts, every=4).tolist() == [2, 3, 3]


def test_saving_is_one_minus_price_paid_over_the_first_days_price() -> None:
    close = np.array([100.0, 90.0, 110.0, 200.0, 220.0, 180.0])
    table = buying.saving_table(close, np.array([0, 3]), every=3)
    assert table[0].tolist() == pytest.approx([0.0, 0.1, -0.1])
    assert table[1].tolist() == pytest.approx([0.0, -0.1, 0.1])
    assert buying.savings(table, np.array([1, 2])).tolist() == pytest.approx([0.1, 0.1])


def test_shuffling_keeps_the_waits_and_moves_them_between_months() -> None:
    table = np.array([[0.0, 0.1], [0.0, -0.3], [0.0, 0.2]])
    waits = np.array([1, 0, 1])
    totals = buying.shuffled_waits(table, waits, draws=200, seed=1)
    # Two waits of one day and one of none: the day-one savings of two of three months.
    possible = {round(v, 6) for v in (0.1 - 0.3, 0.1 + 0.2, -0.3 + 0.2)}
    assert {round(float(t), 6) for t in totals} == possible
    assert (totals == buying.shuffled_waits(table, waits, draws=200, seed=1)).all()
