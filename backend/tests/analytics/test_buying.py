"""The ladder of purchases (decision 077), on figures worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import buying


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def test_months_are_full_blocks_after_the_warm_up() -> None:
    assert buying.month_starts(days=50, every=21, warm_up=5).tolist() == [5, 26]
    assert buying.month_starts(days=47, every=21, warm_up=5).tolist() == [5, 26]
    assert buying.month_starts(days=46, every=21, warm_up=5).tolist() == [5]


def test_a_ladder_splits_the_money_evenly_over_prices_a_swing_apart() -> None:
    rungs = buying.ladder(price=100.0, weekly_swing=0.05, amount=90.0)
    assert [r.price for r in rungs] == pytest.approx([100.0, 95.0, 90.0])
    assert [r.amount for r in rungs] == [30.0, 30.0, 30.0]
    assert [r.below for r in rungs] == pytest.approx([0.0, 0.05, 0.10])


def ladder_frame(close: list[float]) -> pd.DataFrame:
    prices = np.array(close, dtype=float)
    return pd.DataFrame({"high": prices, "low": prices, "close": prices}, index=days(len(prices)))


def test_a_ladder_buys_lower_rungs_when_reached_and_the_rest_on_the_last_day() -> None:
    # Twenty quiet days set the swing, then a month of four days.
    quiet = [100.0, 101.0] * 10
    swing = float(pd.Series([*quiet, 100.0]).pct_change().rolling(20).std().iloc[20] * np.sqrt(5))
    one, two = 100 * (1 - swing), 100 * (1 - 2 * swing)
    falls = ladder_frame([*quiet, 100.0, one - 0.01, one + 1, 100.0])
    found = buying.ladder_replay(falls, np.array([20]), every=4)
    # First part at 100, second at its rung, third never reached: bought at the close.
    # (The day gapped a cent under the rung, so that day's price is what was paid.)
    paid = 3 / (1 / 100 + 1 / (one - 0.01) + 1 / 100)
    assert found["filled"].tolist() == [1]
    assert found["saving"].iloc[0] == pytest.approx(1 - paid / 100)
    assert found["saving"].iloc[0] > 0

    runs_away = ladder_frame([*quiet, 100.0, 110.0, 120.0, 130.0])
    missed = buying.ladder_replay(runs_away, np.array([20]), every=4)
    assert missed["filled"].tolist() == [0]
    assert missed["saving"].iloc[0] == pytest.approx(1 - (3 / (1 / 100 + 2 / 130)) / 100)
    assert missed["saving"].iloc[0] < 0
    assert two < one < 100


def test_a_ladder_is_set_from_days_before_the_month_only() -> None:
    quiet = [100.0, 101.0] * 10
    month = [100.0, 95.0, 97.0, 99.0]
    first = buying.ladder_replay(ladder_frame([*quiet, *month]), np.array([20]), every=4)
    later = buying.ladder_replay(
        ladder_frame([*quiet, *month, 5.0, 500.0]), np.array([20]), every=4
    )
    assert first.equals(later)
