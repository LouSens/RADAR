"""Splits, the walk-forward backtest, and risk levels, on made-up returns."""

import numpy as np
import pandas as pd
import pytest

from radar.models import allocation
from radar.models.allocation import METHODS


def returns(days: int = 700, seed: int = 4) -> pd.DataFrame:
    """Four holdings: a wild one, one that follows it, a steady one, and a calm one."""
    rng = np.random.default_rng(seed)
    wild = rng.normal(0.0004, 0.035, days)
    index = pd.bdate_range("2021-01-04", periods=days, tz="UTC")
    return pd.DataFrame(
        {
            "WILD": wild,
            "FOLLOW": 0.6 * wild + rng.normal(0.0002, 0.015, days),
            "STEADY": rng.normal(0.0003, 0.010, days),
            "CALM": rng.normal(0.0001, 0.004, days),
        },
        index=index,
    )


CURRENT = np.array([0.4, 0.3, 0.2, 0.1])


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("cap", [0.6, 0.4, 0.3])
def test_every_split_is_long_only_sums_to_one_and_respects_the_cap(
    method: allocation.Method, cap: float
) -> None:
    cov = allocation.shrunk_covariance(returns().to_numpy())
    weights = allocation.split(method, cov, CURRENT, cap)
    assert weights.sum() == pytest.approx(1.0)
    assert (weights >= -1e-12).all()
    if method != "current":  # the split as it is now is reported as it is
        assert weights.max() <= cap + 1e-9


def test_the_cap_gives_way_when_there_are_too_few_holdings_for_it() -> None:
    assert allocation.cap_for(4, 0.6) == 0.6
    assert allocation.cap_for(2, 0.3) == 0.5
    assert allocation.cap_for(1, 0.6) == 1.0
    np.testing.assert_allclose(allocation.capped(np.array([9.0, 0.5, 0.5]), 0.5), [0.5, 0.25, 0.25])
    assert allocation.hierarchical(np.array([[0.01]]), 1.0).tolist() == [1.0]


def test_each_rule_does_what_its_name_says() -> None:
    cov = allocation.shrunk_covariance(returns().to_numpy())
    cap = 1.0

    def swing(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    smallest = allocation.min_variance(cov, cap)
    for method in METHODS:
        other = allocation.split(method, cov, CURRENT, cap)
        assert swing(smallest) <= swing(other) + 1e-12
    assert smallest[3] > 0.7  # nearly all in the calm holding

    even = allocation.equal_risk(cov, cap)
    contribution = even * (cov @ even) / swing(even)
    np.testing.assert_allclose(contribution, 0.25, atol=0.01)
    assert even[0] < even[2] < even[3]  # the wilder the holding, the less of it

    grouped = allocation.hierarchical(cov, cap)
    assert grouped[3] == grouped.max()
    assert grouped[0] == grouped.min()


def test_rebalance_weights_use_only_returns_before_each_rebalance() -> None:
    data = returns()
    changed = data.copy()
    cut = 500
    changed.iloc[cut:] *= 6
    for method in ("min_variance", "equal_risk", "hierarchical"):
        before = allocation.rebalance_weights(data, method, CURRENT)
        after = allocation.rebalance_weights(changed, method, CURRENT)
        seen = before.index <= data.index[cut]
        assert seen.sum() > 5
        pd.testing.assert_frame_equal(before[seen], after[seen])
        assert not np.allclose(before[~seen].to_numpy(), after[~seen].to_numpy())
    # The first split applies from the session after the first full window.
    first = allocation.rebalance_weights(data, "equal", CURRENT)
    assert first.index[0] == data.index[allocation.WINDOW]
    assert (first.index[1] - first.index[0]).days >= 28


def test_the_backtest_charges_for_trading_and_holds_cash_still() -> None:
    data = returns()
    free = allocation.backtest(data, "equal", CURRENT, cost=0.0)
    charged = allocation.backtest(data, "equal", CURRENT, cost=0.01)
    assert free.n_days == len(data) - allocation.WINDOW
    assert free.rebalances == len(free.path) - 1
    assert free.turnover > 0
    assert free.cost_paid == 0
    assert charged.cost_paid > 0
    assert charged.total_return < free.total_return
    assert free.deepest_fall < 0
    assert sum(free.weights_now.values()) == pytest.approx(1.0)

    # Half in cash: half the swings, and a shallower fall.
    half = allocation.backtest(data, "equal", CURRENT, cash=0.5, cost=0.0)
    assert half.daily_volatility == pytest.approx(free.daily_volatility / 2, rel=0.05)
    assert half.deepest_fall > free.deepest_fall

    # The steadiest split swings least; the split as it is now is never traded away from.
    by_method = {m: allocation.backtest(data, m, CURRENT) for m in METHODS}
    assert by_method["min_variance"].daily_volatility == min(
        b.daily_volatility for b in by_method.values()
    )
    assert by_method["current"].weights_now == pytest.approx(
        dict(zip(data.columns, CURRENT, strict=True))
    )


def test_too_little_history_is_refused() -> None:
    with pytest.raises(ValueError, match="Not enough history"):
        allocation.backtest(returns(200), "equal", CURRENT)


def test_a_risk_level_fixes_the_cash_share() -> None:
    # Holdings that swing 1.5 times as much as stocks when fully invested.
    low = allocation.level_plan("low", 1.5)
    moderate = allocation.level_plan("moderate", 1.5)
    high = allocation.level_plan("high", 1.5)
    assert low.cash_share == pytest.approx(1 - 0.25 / 1.5)
    assert moderate.cash_share == pytest.approx(0.5)
    assert high.cash_share == 0.0
    assert [p.ratio for p in (low, moderate, high)] == pytest.approx([0.25, 0.75, 1.5])
    assert all(p.reachable for p in (low, moderate, high))
    assert low.cash_share > moderate.cash_share > high.cash_share
    assert (moderate.band_low, moderate.band_high) == (0.5, 1.0)

    # Calmer holdings cannot reach a high level without borrowing: say so, hold no cash.
    stuck = allocation.level_plan("high", 0.9)
    assert not stuck.reachable
    assert stuck.cash_share == 0.0
    assert stuck.ratio == pytest.approx(0.9)

    assert [allocation.level_of(r) for r in (0.1, 0.5, 0.99, 1.0, 1.99, 2.0)] == [
        "low",
        "moderate",
        "moderate",
        "high",
        "high",
        "very high",
    ]


def test_moves_flag_only_gaps_wider_than_the_threshold() -> None:
    rows = allocation.moves(
        {"A": 0.30, "B": 0.10, "USD": 0.60},
        {"A": 0.22, "B": 0.13, "USD": 0.65},
        value=1000.0,
    )
    by_symbol = {r.symbol: r for r in rows}
    assert by_symbol["A"].drifted
    assert by_symbol["A"].change_value == pytest.approx(-80.0)
    assert not by_symbol["B"].drifted
    assert by_symbol["B"].change_value == pytest.approx(30.0)
    assert not by_symbol["USD"].drifted  # exactly at the threshold is not past it
    assert sum(r.change_value for r in rows) == pytest.approx(0.0)
    # A holding in the target but not held yet, and one held but not in the target.
    extra = allocation.moves({"A": 1.0}, {"C": 1.0}, value=10.0)
    assert [(r.symbol, r.change_value) for r in extra] == [("A", -10.0), ("C", 10.0)]
