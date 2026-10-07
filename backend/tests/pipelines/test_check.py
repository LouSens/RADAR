"""Before you buy, on hourly prices made by hand."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from radar.pipelines import account, check

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def bars(close: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2026-06-01", periods=len(close), freq="h", tz="UTC")
    return pd.DataFrame({"high": close, "low": close, "close": close}, index=index)


def test_a_price_at_the_top_of_its_week_and_month_reads_as_high() -> None:
    rising = bars(np.linspace(100, 200, 2400))
    found = check.build("SOL", rising, None, NOW)
    assert (found.place_week, found.place_month, found.place_quarter) == (1.0, 1.0, 1.0)
    assert found.where == "high"
    assert found.below_high == 0
    assert found.move_week == pytest.approx(200 / rising["close"].iloc[-168] - 1)
    assert found.weekly_swing is not None
    assert (found.yours, found.habit_place, found.outcomes) == (None, None, [])


def test_a_price_at_the_bottom_reads_as_low_and_says_how_far_under_the_high() -> None:
    falling = bars(np.linspace(200, 100, 2400))
    found = check.build("SOL", falling, None, NOW)
    assert found.where == "low"
    assert found.place_week == 0
    assert found.below_high == pytest.approx(100 / falling["high"].iloc[-2160:].max() - 1)


def test_with_only_a_week_of_prices_the_longer_periods_are_left_out() -> None:
    short = bars(np.linspace(100, 110, 200))
    found = check.build("NEW", short, None, NOW)
    assert (found.place_month, found.place_quarter, found.weekly_swing) == (None, None, None)
    assert found.where == "high"
    with pytest.raises(ValueError, match="week"):
        check.build("NEW", bars(np.linspace(100, 110, 100)), None, NOW)


def test_nothing_in_the_check_changes_when_later_prices_are_added() -> None:
    close = 100 + 10 * np.sin(np.arange(2600) / 40)
    early = check.build("SOL", bars(close[:2400]), None, NOW)
    again = check.build("SOL", bars(close)[:2400], None, NOW)
    assert early == again


def test_week_and_month_are_read_together() -> None:
    assert check.where(0.9, 0.5) == "high"
    assert check.where(0.9, 0.3) == "middle"
    assert check.where(0.2, 0.4) == "low"
    assert check.where(0.5, None) == "middle"


def test_the_users_own_record_is_set_beside_the_price() -> None:
    from tests.pipelines.test_account import ENTRIES, prices
    from tests.pipelines.test_account import NOW as THEN

    record = account.build(ENTRIES, prices, {"SOL": 1.01}, THEN)
    found = check.build("SOL", bars(np.linspace(100, 200, 2400)), record, NOW)
    assert found.yours is not None
    assert (found.yours.purchases, found.yours.sales, found.yours.held) == (2, 1, True)
    assert found.habit_place is not None
    assert 0 <= found.habit_place <= 1
    assert found.outcomes == record.buy_outcomes
    assert sum(o.trades for o in record.buy_outcomes) == 2
    assert {o.where for o in record.buy_outcomes} <= {"high", "middle", "low"}
    other = check.build("ADA", bars(np.linspace(100, 200, 2400)), record, NOW)
    assert other.yours is None
