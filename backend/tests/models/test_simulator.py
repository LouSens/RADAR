"""The outcome simulator on inputs whose answers can be worked out by hand."""

import numpy as np
import pytest

from radar.models import simulator as sim


def inputs(
    start: list[float], transition: list[list[float]], pools: list[list[float]]
) -> sim.SimulationInputs:
    arrays = tuple(np.array(p, dtype=float) for p in pools)
    return sim.SimulationInputs(
        start_probabilities=np.array(start),
        transition=np.array(transition),
        pools=arrays,
        all_returns=np.concatenate(arrays),
    )


# Two regimes that never switch: calm always returns +1%, wild always returns -5%.
STUCK = inputs([1.0, 0.0], [[1.0, 0.0], [0.0, 1.0]], [[0.01], [-0.05]])


def test_same_seed_gives_identical_paths() -> None:
    mixed = inputs([0.5, 0.5], [[0.9, 0.1], [0.2, 0.8]], [[0.01, -0.01, 0.0], [0.05, -0.06]])
    a = sim.simulate(mixed, horizon=30, n_paths=500, seed=42)
    b = sim.simulate(mixed, horizon=30, n_paths=500, seed=42)
    c = sim.simulate(mixed, horizon=30, n_paths=500, seed=43)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert a.shape == (500, 30)


def test_returns_come_from_the_regime_the_path_is_in() -> None:
    paths = sim.simulate(STUCK, horizon=5, n_paths=200, seed=1)
    assert np.all(paths == 0.01)  # started calm and calm never ends
    wild = inputs([0.0, 1.0], [[1.0, 0.0], [0.0, 1.0]], [[0.01], [-0.05]])
    assert np.all(sim.simulate(wild, horizon=5, n_paths=200, seed=1) == -0.05)


def test_regimes_follow_the_transition_matrix() -> None:
    # From calm, the next day is wild 30% of the time.
    switching = inputs([1.0, 0.0], [[0.7, 0.3], [0.0, 1.0]], [[0.0], [1.0]])
    first_day = sim.simulate(switching, horizon=1, n_paths=20_000, seed=3)[:, 0]
    assert first_day.mean() == pytest.approx(0.3, abs=0.015)
    # Wild is absorbing here, so the share of wild days can only grow.
    week = sim.simulate(switching, horizon=7, n_paths=20_000, seed=3)
    share = week.mean(axis=0)
    assert np.all(np.diff(share) > 0)
    assert share[-1] == pytest.approx(1 - 0.7**7, abs=0.02)


def test_bootstrap_keeps_fat_tails() -> None:
    # One return in a hundred is a crash. A normal fit would almost never produce it.
    pool = [0.001] * 99 + [-0.30]
    crashy = inputs([1.0], [[1.0]], [pool])
    paths = sim.simulate(crashy, horizon=1, n_paths=50_000, seed=5)[:, 0]
    assert (paths == -0.30).mean() == pytest.approx(0.01, abs=0.003)
    assert set(np.unique(paths)) == {0.001, -0.30}


def test_pools_group_returns_by_regime_and_fall_back_when_thin() -> None:
    returns = np.arange(100, dtype=float)
    labels = np.array([0] * 70 + [1] * 25 + [2] * 5)
    pools, thin = sim.build_pools(returns, labels, n_states=3)
    assert len(pools[0]) == 70
    assert len(pools[1]) == 25
    assert thin == [2]
    assert len(pools[2]) == 100  # too few days of its own: uses every return


def test_summary_matches_a_hand_calculation() -> None:
    daily = sim.simulate(STUCK, horizon=7, n_paths=100, seed=0)
    cumulative = sim.cumulative_returns(daily)
    summary = sim.summarise(cumulative, steps=7, start_price=100.0)
    expected = 100.0 * np.exp(0.07)
    assert summary.quantiles["0.5"] == pytest.approx(expected)
    assert summary.quantiles["0.05"] == pytest.approx(expected)
    assert summary.expected_worst_drawdown == pytest.approx(0.0)  # it only ever rises
    assert summary.mean_return == pytest.approx(np.exp(0.07) - 1)
    assert sum(summary.histogram_counts) == 100
    assert len(summary.histogram_edges) == len(summary.histogram_counts) + 1
    # A shorter horizon reads the same paths, just fewer days of them.
    assert sim.summarise(cumulative, steps=1, start_price=100.0).quantiles["0.5"] == pytest.approx(
        100.0 * np.exp(0.01)
    )


def test_intervals_widen_with_level_and_horizon() -> None:
    rng = np.random.default_rng(0)
    noisy = inputs([1.0], [[1.0]], [list(rng.normal(0, 0.02, 2000))])
    cumulative = sim.cumulative_returns(sim.simulate(noisy, horizon=30, n_paths=5000, seed=2))
    week = sim.summarise(cumulative, steps=7, start_price=100.0)
    month = sim.summarise(cumulative, steps=30, start_price=100.0)
    widths = [i.high - i.low for i in week.intervals]
    assert widths == sorted(widths)
    assert [i.level for i in week.intervals] == [0.5, 0.8, 0.95]
    assert (month.intervals[1].high - month.intervals[1].low) > widths[1]
    assert month.expected_worst_drawdown < week.expected_worst_drawdown < 0


def test_touching_a_level_is_at_least_as_likely_as_ending_beyond_it() -> None:
    rng = np.random.default_rng(1)
    noisy = inputs([1.0], [[1.0]], [list(rng.normal(0, 0.03, 2000))])
    cumulative = sim.cumulative_returns(sim.simulate(noisy, horizon=30, n_paths=10_000, seed=4))
    above = sim.level_probabilities(cumulative, steps=30, start_price=100.0, level=110.0)
    assert above.touches > above.ends_above > 0
    assert above.ends_above + above.ends_below == pytest.approx(1.0)
    below = sim.level_probabilities(cumulative, steps=30, start_price=100.0, level=90.0)
    assert below.touches > below.ends_below > 0
    # The level it starts at has already been touched.
    here = sim.level_probabilities(cumulative, steps=30, start_price=100.0, level=100.0)
    assert here.touches == pytest.approx(1.0, abs=0.02)


def test_fan_starts_at_the_current_price_and_spreads_out() -> None:
    rng = np.random.default_rng(2)
    noisy = inputs([1.0], [[1.0]], [list(rng.normal(0, 0.02, 2000))])
    cumulative = sim.cumulative_returns(sim.simulate(noisy, horizon=10, n_paths=5000, seed=6))
    bands = sim.fan(cumulative, start_price=50.0)
    assert set(bands) == {"0.05", "0.25", "0.5", "0.75", "0.95"}
    assert all(len(path) == 11 and path[0] == 50.0 for path in bands.values())
    spread = np.array(bands["0.95"]) - np.array(bands["0.05"])
    assert np.all(np.diff(spread) > 0)


def test_gbm_baseline_and_pinball_loss() -> None:
    rng = np.random.default_rng(3)
    trailing = rng.normal(0.001, 0.02, 365)
    levels = np.array([0.1, 0.5, 0.9])
    week = sim.gbm_quantiles(trailing, steps=7, levels=levels)
    assert week[0] < week[1] < week[2]
    assert week[1] == pytest.approx(7 * trailing.mean())
    month = sim.gbm_quantiles(trailing, steps=30, levels=levels)
    assert (month[2] - month[0]) > (week[2] - week[0])
    # Pinball loss is zero for a perfect forecast and penalises the costly side more.
    realised = np.array([1.0, 2.0, 3.0])
    assert sim.pinball_loss(realised, realised, 0.9) == 0.0
    assert sim.pinball_loss(realised, realised - 1, 0.9) == pytest.approx(0.9)
    assert sim.pinball_loss(realised, realised + 1, 0.9) == pytest.approx(0.1)
