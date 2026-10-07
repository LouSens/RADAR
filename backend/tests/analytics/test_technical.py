"""Indicators, levels, sizing rules and the walk-forward loop, on prices whose answers
can be worked out by hand."""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest

from radar.analytics import technical


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def wandering(n: int = 600, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    spread = np.abs(rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.005, n)),
            "high": close * (1 + spread),
            "low": close * (1 - spread),
            "close": close,
            "volume": rng.uniform(1, 3, n),
        },
        index=days(n),
    )


def test_rsi_is_100_after_only_rises_and_0_after_only_falls() -> None:
    up = pd.Series(np.arange(1.0, 31.0), index=days(30))
    assert technical.rsi(up).iloc[-1] == pytest.approx(100.0)
    assert technical.rsi(up[::-1].set_axis(days(30))).iloc[-1] == pytest.approx(0.0)
    assert technical.rsi(up).iloc[:14].isna().all()


def test_holding_by_swings_halves_when_swings_double() -> None:
    quiet = np.tile([0.01, -0.01], 70)
    returns = pd.Series(np.concatenate([quiet, quiet[:20] * 2]), index=days(160))
    weight = technical.hold_by_swings(returns)
    assert weight.iloc[60] == pytest.approx(1.0)
    assert weight.iloc[-1] == pytest.approx(0.5, abs=0.02)
    assert weight.max() <= 1.0


def test_trend_rules_hold_in_a_rise_and_step_aside_in_a_fall() -> None:
    close = pd.Series(np.concatenate([np.arange(100.0, 400.0), np.arange(400.0, 100.0, -1)]))
    close.index = days(len(close))
    for weight in (
        technical.hold_above_average(close),
        technical.hold_on_cross(close),
        technical.hold_on_direction(close),
    ):
        assert weight.iloc[290] == 1.0
        assert weight.iloc[-1] == 0.0
    assert technical.hold_above_average(close).iloc[:199].isna().all()


def test_event_caution_halves_the_day_before_and_the_day_of_an_event() -> None:
    index = days(10)
    weight = technical.hold_through_events(index, [date(2024, 1, 6), date(2024, 2, 1)])
    # The weight on a day is held over the next day: 4 Jan covers the 5th, 5 Jan the 6th.
    assert weight.tolist() == [1, 1, 1, 0.5, 0.5, 1, 1, 1, 1, 1]


def test_a_weight_earns_the_next_days_return_never_its_own_days() -> None:
    returns = pd.Series([0.0, 0.10, 0.0, -0.10], index=days(4))
    # Deciding on the day of the jump to hold: too late for the jump, in time for nothing.
    late = technical.backtest(returns, pd.Series([0.0, 1.0, 1.0, 0.0], index=days(4)), cost=0)
    assert late.tolist() == pytest.approx([0.0, 0.0, -0.10])
    early = technical.backtest(returns, pd.Series([1.0, 0.0, 0.0, 0.0], index=days(4)), cost=0)
    assert early.tolist() == pytest.approx([0.10, 0.0, 0.0])


def test_changing_the_weight_costs_a_share_of_what_was_traded() -> None:
    returns = pd.Series(0.0, index=days(4))
    net = technical.backtest(returns, pd.Series([1.0, 1.0, 0.5, 0.5], index=days(4)), cost=0.001)
    assert net.tolist() == pytest.approx([-0.001, 0.0, -0.0005])


def test_the_deepest_fall_and_sharpe_ratio_of_a_known_series() -> None:
    returns = pd.Series([0.10, -0.50, 0.20], index=days(3))
    assert technical.deepest_fall(returns) == pytest.approx(-0.5)
    steady = pd.Series([0.01, 0.03] * 50)
    assert technical.sharpe(steady, 252) == pytest.approx(0.02 / steady.std() * np.sqrt(252))


def test_a_rule_identical_to_holding_has_no_sharpe_difference() -> None:
    held = pd.Series(np.random.default_rng(1).normal(0.0005, 0.01, 800), index=days(800))
    gap, p_value = technical.sharpe_difference(held, held, 252, draws=300)
    assert gap == 0.0
    assert p_value == 1.0


def test_a_rule_that_is_plainly_better_gets_a_small_p_value() -> None:
    rng = np.random.default_rng(2)
    held = pd.Series(rng.normal(0.0, 0.01, 1500), index=days(1500))
    gap, p_value = technical.sharpe_difference(held.abs(), held, 252, draws=500)
    assert gap > 5
    assert p_value < 0.01


def test_a_fair_value_gap_is_dated_on_the_first_return_to_it() -> None:
    #            0    1    2    3    4    5
    high = pd.Series([10.0, 11, 14, 15, 16, 13.5], index=days(6))
    low = pd.Series([9.0, 10, 12, 13, 14, 11.5], index=days(6))
    # Day 2's low (12) is above day 0's high (10): a gap from 10 to 12. Day 3's low (13)
    # is above day 1's high (11): a gap from 11 to 13. Day 5's low (11.5) reaches both.
    assert technical.fair_value_gap_cases(high, low, up=True) == [days(6)[5]]
    assert technical.fair_value_gap_cases(high, low, up=False) == []
    # Seen upside down it is a gap down, returned to from below.
    assert technical.fair_value_gap_cases(-low, -high, up=False) == [days(6)[5]]
    # With no time allowed for the return there is no case.
    assert technical.fair_value_gap_cases(high, low, up=True, wait=1) == []


def test_an_order_block_is_the_last_falling_day_before_a_break() -> None:
    frame = pd.DataFrame(
        {
            "open": [10.0, 10, 10, 9.5, 12, 12.5, 12],
            "high": [10.5, 10.5, 10.5, 10.2, 13, 13, 12.5],
            "low": [9.5, 9.5, 9.5, 9.0, 11.5, 12, 10.0],
            "close": [10.0, 10, 10, 9.2, 12.5, 12.6, 10.4],
        },
        index=days(7),
    )
    # Day 3 fell. Day 4 closes above the highs of the 3 days before: the block is day 3,
    # from 9.0 to 10.2. Day 6's low (10.0) is the first to reach it.
    cases = technical.order_block_cases(frame, up=True, lookback=3, search=3)
    assert cases == [days(7)[6]]
    assert technical.order_block_cases(frame, up=True, lookback=3, search=3, wait=1) == []


def test_support_resistance_new_highs_and_volume_are_found_where_expected() -> None:
    n = 80
    low = pd.Series(np.full(n, 100.0), index=days(n))
    low.iloc[70] = 100.3  # within half a percent of the floor
    low.iloc[40] = 120.0
    assert days(n)[70] in technical.support_cases(low)
    assert days(n)[40] not in technical.support_cases(low)
    high = pd.Series(np.full(n, 100.0), index=days(n))
    high.iloc[75] = 90.0
    cases = technical.resistance_cases(high)
    assert days(n)[74] in cases
    assert days(n)[75] not in cases

    close = pd.Series(np.arange(1.0, 301.0), index=days(300))
    assert technical.new_high_cases(close) == list(days(300)[252:])
    volume = pd.Series(1.0, index=days(300))
    volume.iloc[100] = 5.0
    assert technical.high_volume_cases(close, volume, rising=True) == [days(300)[100]]
    assert technical.high_volume_cases(close, volume, rising=False) == []


Cases = Callable[[pd.DataFrame], object]
RULES: dict[str, Cases] = {
    "swings": lambda f: technical.hold_by_swings(f["close"].pct_change()),
    "average": lambda f: technical.hold_above_average(f["close"]),
    "cross": lambda f: technical.hold_on_cross(f["close"]),
    "direction": lambda f: technical.hold_on_direction(f["close"]),
    "features": lambda f: technical.features(f, [date(2024, 6, 1), date(2025, 3, 1)]),
    "rsi": lambda f: technical.rsi_cases(f["close"], below=True),
    "gap": lambda f: technical.fair_value_gap_cases(f["high"], f["low"], up=True),
    "block": lambda f: technical.order_block_cases(f, up=True),
    "support": lambda f: technical.support_cases(f["low"]),
    "resistance": lambda f: technical.resistance_cases(f["high"]),
    "new high": lambda f: technical.new_high_cases(f["close"]),
    "volume": lambda f: technical.high_volume_cases(f["close"], f["volume"], rising=True),
}


@pytest.mark.parametrize("name", list(RULES))
def test_nothing_known_on_a_day_changes_when_later_days_change(name: str) -> None:
    """No lookahead: what each rule says up to a day is the same whatever comes after."""
    frame = wandering()
    cut = 450
    changed = frame.copy()
    changed.iloc[cut:] = changed.iloc[cut:] * 3.0
    before, after = RULES[name](frame), RULES[name](changed)
    if isinstance(before, list) and isinstance(after, list):
        boundary = frame.index[cut]
        assert [d for d in before if d < boundary] == [d for d in after if d < boundary]
    else:
        assert isinstance(before, pd.Series | pd.DataFrame)
        assert isinstance(after, pd.Series | pd.DataFrame)
        assert pd.DataFrame(before).iloc[:cut].equals(pd.DataFrame(after).iloc[:cut])


def test_days_to_the_next_event_counts_down_and_is_capped() -> None:
    gap = technical.days_to_event(days(40), [date(2024, 1, 20)], cap=10)
    assert gap.iloc[0] == 10
    assert gap.iloc[17] == 2
    assert gap.iloc[19] == 0
    assert gap.iloc[25] == 10  # nothing further is scheduled


def test_the_target_is_missing_where_the_later_day_has_not_happened() -> None:
    close = pd.Series([1.0, 2, 1, 3, 2], index=days(5))
    target = technical.rises(close, 2)
    assert target.iloc[:3].tolist() == [0.0, 1.0, 1.0]
    assert target.iloc[3:].isna().all()


def test_a_model_is_fitted_only_on_days_whose_outcome_was_already_known() -> None:
    n, steps = 60, 5
    table = pd.DataFrame({"x": np.arange(n, dtype=float)}, index=days(n))
    target = pd.Series(np.tile([0.0, 1.0], n // 2), index=days(n))
    seen: list[tuple[int, float]] = []

    def fit(x: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
        seen.append((len(x), float(x.max())))
        return lambda rows: np.full(len(rows), 0.5)

    chance = technical.walk_forward(table, target, steps, fit, min_train=30, refit_every=10)
    # At the fit on row 30 the last usable row is 25: its outcome is known on row 30.
    # The loop needs 100 rows to fit at all, so on this short series it never fits.
    assert seen == []
    assert chance.isna().all()

    n = 400
    table = pd.DataFrame({"x": np.arange(n, dtype=float)}, index=days(n))
    target = pd.Series(np.tile([0.0, 1.0], n // 2), index=days(n))
    chance = technical.walk_forward(table, target, steps, fit, min_train=200, refit_every=50)
    assert [last for _, last in seen] == [195.0, 245.0, 295.0, 345.0]
    assert chance.iloc[:200].isna().all()
    assert chance.iloc[200:].notna().all()


def test_a_forecast_does_not_change_when_later_days_change() -> None:
    frame = wandering(500)
    table = technical.features(frame, [])
    target = technical.rises(frame["close"], 5)
    first = technical.walk_forward(
        table, target, 5, technical.fit_trees, min_train=300, refit_every=50
    )
    cut = 420
    changed = frame.copy()
    changed.iloc[cut:] = changed.iloc[cut:] * 2.0
    second = technical.walk_forward(
        technical.features(changed, []),
        technical.rises(changed["close"], 5),
        5,
        technical.fit_trees,
        min_train=300,
        refit_every=50,
    )
    # Forecasts made before the changed days cannot have seen them. Fits at rows 300,
    # 350 and 400 all use outcomes known by row 400, which is before the change.
    pd.testing.assert_series_equal(first.iloc[:cut], second.iloc[:cut])
