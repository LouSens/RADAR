"""Coins low against high in their range, on invented coins with a known answer."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import screening

DAYS = pd.date_range("2022-01-03", periods=900, freq="D")  # starts on a Monday


def coins(count: int, reverting: bool, seed: int = 0) -> pd.DataFrame:
    """Daily closes. With `reverting`, each coin is pulled back towards 100, so a coin
    that is low tends to rise and one that is high tends to fall."""
    rng = np.random.default_rng(seed)
    logs = np.zeros((len(DAYS), count))
    for t in range(1, len(DAYS)):
        pull = -0.05 * logs[t - 1] if reverting else 0.0
        logs[t] = logs[t - 1] + pull + rng.normal(0, 0.03, count)
    return pd.DataFrame(100 * np.exp(logs), index=DAYS, columns=[f"C{i}" for i in range(count)])


def run(close: pd.DataFrame, days: int = 7) -> list[screening.Week]:
    places = screening.place(close, close, close)
    counts = screening.eligible(close, pd.DataFrame(2e6, index=close.index, columns=close.columns))
    return screening.weekly(places, counts, screening.ahead(close, days))


def test_place_is_zero_at_the_bottom_of_the_range_and_one_at_the_top() -> None:
    rising = pd.DataFrame({"A": np.linspace(1, 2, 60), "B": np.linspace(2, 1, 60)})
    found = screening.place(rising, rising, rising)
    assert found["A"].iloc[-1] == pytest.approx(1.0)
    assert found["B"].iloc[-1] == pytest.approx(0.0)
    assert found.iloc[:29].isna().all().all()


def test_a_coin_counts_only_with_enough_history_and_enough_trading() -> None:
    close = pd.DataFrame({"A": np.ones(100), "B": [np.nan] * 60 + [1.0] * 40})
    traded = pd.DataFrame({"A": 2e6, "B": 2e6}, index=close.index)
    traded.loc[80:, "A"] = 10.0  # low for most of the last month
    ok = screening.eligible(close, traded)
    assert ok["A"].iloc[59]
    assert not ok["A"].iloc[58]
    assert not ok["B"].iloc[99]  # 40 days seen
    assert not ok["A"].iloc[99]  # trading has dried up over the last month


def test_nothing_about_a_day_changes_when_later_days_change() -> None:
    close = coins(30, reverting=True)
    changed = close.copy()
    changed.iloc[600:] *= 5
    first = screening.place(close, close, close)
    second = screening.place(changed, changed, changed)
    pd.testing.assert_frame_equal(first.iloc[:600], second.iloc[:600])
    assert screening.ahead(close, 7).iloc[-7:].isna().all().all()


def test_coins_that_revert_show_low_ahead_of_high_and_pass() -> None:
    rows = run(coins(80, reverting=True))
    found = screening.judge(rows, mark=0.005)
    assert found is not None
    assert found.lead > 0.01
    assert found.no_lead < 0.01
    assert found.first_half > 0
    assert found.second_half > 0
    assert found.passes
    assert all(r.low_coins >= 10 and r.high_coins >= 10 for r in rows)
    assert all(pd.Timestamp(r.day).dayofweek == 0 for r in rows)


def test_coins_that_wander_show_no_lead_and_do_not_pass() -> None:
    found = screening.judge(run(coins(80, reverting=False, seed=3)), mark=0.005)
    assert found is not None
    assert abs(found.lead) < 0.005
    assert not found.passes


def test_too_few_coins_or_weeks_gives_no_verdict() -> None:
    assert run(coins(8, reverting=True)) == []
    assert screening.judge([], mark=0.005) is None
