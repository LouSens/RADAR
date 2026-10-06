"""Regular buying on returns whose answers can be worked out by hand."""

import numpy as np
import pytest

from radar.models import regular_buying as dca


def test_purchases_are_made_at_a_fixed_interval() -> None:
    assert dca.purchase_days(21, 4).tolist() == [0, 21, 42, 63]


def test_each_purchase_grows_only_from_the_day_it_was_made() -> None:
    # One asset gaining 1% every session; 100 bought at the start of sessions 0 and 2.
    daily = np.full((1, 4, 1), np.log(1.01))
    plan, at_once = dca.run_plan(daily, np.array([1.0]), 100.0, every=2, purchases=2)
    expected = [
        100 * 1.01,
        100 * 1.01**2,
        100 * 1.01**3 + 100 * 1.01,
        100 * 1.01**4 + 100 * 1.01**2,
    ]
    np.testing.assert_allclose(plan[0], expected)
    # The same 200 put in on the first day has all of it growing throughout.
    np.testing.assert_allclose(at_once[0], [200 * 1.01**k for k in range(1, 5)])


def test_a_purchase_is_split_among_the_assets() -> None:
    # The first asset doubles in the one session; the second does nothing.
    daily = np.log(np.array([[[2.0, 1.0]]]))
    plan, _ = dca.run_plan(daily, np.array([0.25, 0.75]), 100.0, every=1, purchases=1)
    assert plan[0, 0] == pytest.approx(25 * 2 + 75)


def test_in_a_falling_market_buying_bit_by_bit_ends_ahead_of_all_at_once() -> None:
    daily = np.full((1, 6, 1), np.log(0.9))
    plan, at_once = dca.run_plan(daily, np.array([1.0]), 100.0, every=2, purchases=3)
    assert plan[0, -1] > at_once[0, -1]
    rising = np.full((1, 6, 1), np.log(1.1))
    plan, at_once = dca.run_plan(rising, np.array([1.0]), 100.0, every=2, purchases=3)
    assert plan[0, -1] < at_once[0, -1]


def width(found: dca.Spread) -> float:
    return found.quantiles["0.95"] - found.quantiles["0.05"]


def history(n: int = 900, seed: int = 6) -> np.ndarray:
    rng = np.random.default_rng(seed)
    common = rng.normal(0.0004, 0.01, n)
    return np.column_stack([common + rng.normal(0, 0.004, n), 2 * common])


def test_same_seed_gives_the_same_futures_for_both_ways_of_investing() -> None:
    returns, weights = history(), np.array([0.6, 0.4])
    a = dca.simulate(returns, weights, 100.0, 21, 6, n_paths=200, seed=3)
    b = dca.simulate(returns, weights, 100.0, 21, 6, n_paths=200, seed=3)
    assert a[0].shape == (200, 126)
    assert np.array_equal(a[0], b[0])
    assert np.array_equal(a[1], b[1])
    assert not np.array_equal(a[0], dca.simulate(returns, weights, 100.0, 21, 6, 200, seed=4)[0])


def test_a_past_plan_is_simulated_from_the_days_before_it_only() -> None:
    returns, weights = history(), np.array([0.6, 0.4])
    records = dca.backtest(returns, weights, 21, 3, n_paths=200)
    assert [r.origin for r in records] == list(range(250, 838, 63))
    changed = returns.copy()
    changed[500:] = 0.3
    again = dca.backtest(changed, weights, 21, 3, n_paths=200)
    for before, after in zip(records, again, strict=True):
        if before.origin <= 500:
            assert before.bounds == after.bounds
        if before.origin + 63 <= 500:
            assert before.realised == after.realised
    # What happened is the real plan run through the days that followed.
    actual, _ = dca.run_plan(returns[250:313][None, :, :], weights, 1.0, 21, 3)
    assert records[0].realised == pytest.approx(actual[0, -1] / 3)
    assert [(c.level, c.n) for c in dca.coverage(records)] == [(0.5, 10), (0.8, 10), (0.95, 10)]


def test_the_result_is_in_money_and_says_how_much_evidence_it_rests_on() -> None:
    returns, weights = history(), np.array([0.6, 0.4])
    result = dca.run(returns, weights, 100.0, 21, 12, n_paths=1000)
    assert (result.paid_in, result.sessions, result.n_days) == (1200.0, 252, 900)
    assert result.separate_periods == 3
    quantiles = [result.plan.quantiles[f"{q:g}"] for q in dca.QUANTILES]
    assert quantiles == sorted(quantiles)
    assert 0.0 <= result.plan.below_paid_in <= 1.0
    assert 0.0 <= result.plan_ahead <= 1.0
    # All at once has the money in the market longer, so its outcomes are wider apart.
    assert width(result.at_once) > width(result.plan)
    assert len(result.paid_in_path) == 252
    assert (result.paid_in_path[0], result.paid_in_path[20], result.paid_in_path[21]) == (
        100,
        100,
        200,
    )
    assert result.paid_in_path[-1] == 1200
    assert all(len(path) == 252 for path in result.fan.values())


def test_plans_that_cannot_be_simulated_are_refused_with_the_reason() -> None:
    weights = np.array([0.6, 0.4])
    with pytest.raises(ValueError, match="share 200 days"):
        dca.run(history(200), weights, 100.0, 21, 6)
    with pytest.raises(ValueError, match="longer than 504"):
        dca.run(history(), weights, 100.0, 21, 30)
