"""The portfolio's block bootstrap on inputs whose answers can be worked out by hand."""

import numpy as np
import pytest

from radar.models import portfolio_simulation as sim
from radar.models import simulator


def joint(n: int = 600, seed: int = 4) -> np.ndarray:
    """Two holdings that move together, with a calm half and a rough half."""
    rng = np.random.default_rng(seed)
    scale = np.where(np.arange(n) < n // 2, 0.005, 0.02)
    common = rng.normal(0, 1, n) * scale
    return np.column_stack([common + rng.normal(0, 0.002, n), 2 * common])


def spread(ends: np.ndarray) -> float:
    return float(np.quantile(ends, 0.975) - np.quantile(ends, 0.025))


def width(horizon: sim.Horizon) -> float:
    return horizon.summary.quantiles["0.95"] - horizon.summary.quantiles["0.05"]


def test_same_seed_gives_identical_paths() -> None:
    returns, weights = joint(), np.array([0.5, 0.3])
    a = sim.simulate(returns, weights, 30, n_paths=300, seed=7)
    b = sim.simulate(returns, weights, 30, n_paths=300, seed=7)
    c = sim.simulate(returns, weights, 30, n_paths=300, seed=8)
    assert a.shape == (300, 30)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_days_are_drawn_in_runs_of_consecutive_days() -> None:
    days = sim.sample_days(500, horizon=25, n_paths=200, block=10, rng=np.random.default_rng(1))
    assert days.shape == (200, 25)
    assert days.min() >= 0
    assert days.max() < 500
    steps = np.diff(days, axis=1)
    inside_a_run = np.ones(24, dtype=bool)
    inside_a_run[[9, 19]] = False  # a new run starts at days 10 and 20
    assert np.all(steps[:, inside_a_run] == 1)


def test_every_holding_takes_the_same_day_so_they_still_move_together() -> None:
    # The second holding is always exactly twice the first. Sampling days jointly keeps
    # that; sampling each holding on its own would not.
    rng = np.random.default_rng(2)
    first = rng.normal(0, 0.01, 400)
    returns = np.column_stack([first, 2 * first])
    alone = sim.simulate(returns, np.array([1.0, 0.0]), 20, n_paths=500, seed=3)
    other = sim.simulate(returns, np.array([0.0, 1.0]), 20, n_paths=500, seed=3)
    np.testing.assert_allclose(other, 2 * alone)


def test_cash_does_not_move_and_holdings_are_left_alone() -> None:
    # One holding that gains 1% every day, at half the money; the rest is cash.
    returns = np.full((300, 1), np.log(1.01))
    paths = sim.simulate(returns, np.array([0.5]), 10, n_paths=50, seed=0)
    expected = np.log(0.5 + 0.5 * 1.01 ** np.arange(1, 11))
    np.testing.assert_allclose(paths, np.tile(expected, (50, 1)))
    # All in cash, nothing changes.
    assert np.all(sim.simulate(returns, np.array([0.0]), 10, n_paths=50, seed=0) == 0.0)
    # Widening for newer holdings stretches every path by the same factor.
    wider = sim.simulate(returns, np.array([0.5]), 10, n_paths=50, seed=0, scale=1.2)
    np.testing.assert_allclose(wider, 1.2 * paths)


def test_runs_of_days_keep_rough_patches_together() -> None:
    # Rough days come in one long stretch. Runs of days keep a stretch together, so
    # more paths are rough throughout than when days are drawn one at a time.
    returns, weights = joint(), np.array([0.5, 0.5])
    runs = sim.simulate(returns, weights, 30, n_paths=4000, block=10, seed=5)[:, -1]
    single = sim.simulate(returns, weights, 30, n_paths=4000, block=1, seed=5)[:, -1]
    assert spread(runs) > spread(single) * 1.1


def test_chances_count_paths_at_or_past_each_change() -> None:
    # Four paths over two days, ending at -10.5%, -2%, +3.5%, and +12%.
    ends = np.log(np.array([0.895, 0.98, 1.035, 1.12]))
    # The second path dipped to -8% on the way; the others went straight there.
    middle = np.log(np.array([0.95, 0.92, 1.01, 1.05]))
    found = {c.change: c for c in sim.chances(np.column_stack([middle, ends]), steps=2)}
    assert len(found) == len(sim.CHANGES)
    assert (found[-0.05].ends_beyond, found[-0.05].touches) == (0.25, 0.5)
    assert (found[-0.1].ends_beyond, found[-0.1].touches) == (0.25, 0.25)
    assert (found[0.03].ends_beyond, found[0.03].touches) == (0.5, 0.5)
    assert (found[0.2].ends_beyond, found[0.2].touches) == (0.0, 0.0)
    # No change at all: where the value stands today has already been reached.
    assert (found[0.0].ends_beyond, found[0.0].touches) == (0.5, 1.0)


def test_a_past_range_uses_only_the_days_before_it() -> None:
    returns, weights = joint(), np.array([0.6, 0.2])
    records = sim.backtest(returns, weights, 30, n_paths=300)
    assert [r.origin for r in records] == list(range(250, 571, 30))
    # Rewriting everything from one origin on leaves every earlier range as it was,
    # and the range drawn at that origin too: it never saw those days.
    changed = returns.copy()
    changed[400:] = 0.5
    again = sim.backtest(changed, weights, 30, n_paths=300)
    for before, after in zip(records, again, strict=True):
        if before.origin <= 400:
            assert before.bounds == after.bounds
        if before.origin + 30 <= 400:
            assert before.realised == after.realised
    # What happened is the change in value of holdings left alone through the window.
    first = records[0]
    assert first.realised == pytest.approx(sim.realised_change(returns[250:280], weights))


def test_coverage_counts_ranges_that_held() -> None:
    def record(realised: float) -> sim.PastRange:
        return sim.PastRange(
            origin=0,
            realised=realised,
            bounds={"0.5": (-0.01, 0.01), "0.8": (-0.03, 0.03), "0.95": (-0.06, 0.06)},
        )

    found = sim.coverage([record(0.0), record(0.02), record(-0.05), record(0.2)])
    assert [(c.level, c.n, c.inside) for c in found] == [(0.5, 4, 1), (0.8, 4, 2), (0.95, 4, 3)]


def test_ranges_drawn_from_a_steady_record_hold_about_as_often_as_stated() -> None:
    rng = np.random.default_rng(11)
    returns = rng.normal(0.0003, 0.01, (3000, 2))
    eighty = next(
        c for c in sim.coverage(sim.backtest(returns, np.array([0.5, 0.5]), 30)) if c.level == 0.8
    )
    assert eighty.n == 91
    assert 0.68 <= eighty.inside / eighty.n <= 0.92


def test_the_stored_result_is_in_money_and_needs_enough_history() -> None:
    returns, weights = joint(), np.array([0.5, 0.3])
    assert sim.run(returns[:249], weights, 1000.0) is None
    result = sim.run(returns, weights, 1000.0, n_paths=2000)
    assert result is not None
    assert (result.n_days, result.block, result.start_value) == (600, sim.BLOCK, 1000.0)
    assert [h.summary.steps for h in result.horizons] == [30, 90]
    month, quarter = result.horizons
    for horizon in result.horizons:
        quantiles = [horizon.summary.quantiles[f"{q:g}"] for q in simulator.QUANTILES]
        assert quantiles == sorted(quantiles)
        assert horizon.summary.expected_worst_drawdown < 0
        assert [c.level for c in horizon.coverage] == list(simulator.INTERVALS)
    # Further ahead, a wider range.
    assert width(quarter) > width(month)
    # The fan starts at today's value and runs to the longest horizon.
    assert all(len(path) == 91 and path[0] == 1000.0 for path in result.fan.values())
