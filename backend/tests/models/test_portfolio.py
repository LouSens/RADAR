"""Portfolio risk maths on made-up returns."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from radar.models import portfolio
from radar.models.portfolio import Episode


def panel(days: int = 900, seed: int = 0) -> pd.DataFrame:
    """Three assets: a wild one, a calm one, and one that follows the wild one."""
    rng = np.random.default_rng(seed)
    wild = rng.normal(0, 0.04, days)
    calm = rng.normal(0, 0.005, days)
    follower = 0.5 * wild + rng.normal(0, 0.01, days)
    index = pd.bdate_range("2021-01-04", periods=days, tz="UTC") + pd.Timedelta(hours=21)
    return pd.DataFrame({"WILD": wild, "CALM": calm, "FOLLOW": follower}, index=index)


def test_risk_shares_sum_to_one_and_the_wild_holding_carries_most() -> None:
    returns = panel()
    weights = np.array([0.2, 0.6, 0.2])
    result = portfolio.xray(returns, weights)
    shares = [h.risk_share for h in result.holdings]
    assert sum(shares) == pytest.approx(1.0, abs=1e-12)
    # A fifth of the money, most of the risk.
    assert result.holdings[0].weight == 0.2
    assert result.holdings[0].risk_share > 0.6
    assert result.holdings[1].risk_share < 0.1
    assert result.daily_volatility < result.undiversified_volatility
    assert result.n_days == 900
    assert result.correlation[0][0] == pytest.approx(1.0)
    assert result.correlation[0][2] > 0.7
    assert abs(result.correlation[0][1]) < 0.15
    assert result.deepest_fall.depth < 0
    assert result.deepest_fall.peak_day <= result.deepest_fall.trough_day


def test_one_holding_carries_all_of_its_own_risk() -> None:
    returns = panel()[["CALM"]]
    result = portfolio.xray(returns, np.array([1.0]))
    assert result.holdings[0].risk_share == pytest.approx(1.0)
    assert result.daily_volatility == pytest.approx(result.undiversified_volatility)


def test_only_sessions_every_holding_has_are_used_and_too_few_are_refused() -> None:
    returns = panel()
    returns.iloc[:300, 1] = np.nan
    assert portfolio.xray(returns, np.array([0.3, 0.3, 0.4])).n_days == 600
    with pytest.raises(portfolio.NotEnoughHistoryError, match="249 shared sessions"):
        portfolio.covariance(panel(249))


def test_mix_return_is_the_weighted_simple_return() -> None:
    index = pd.date_range("2024-01-01", periods=1, tz="UTC")
    returns = pd.DataFrame({"A": [np.log(1.10)], "B": [np.log(0.90)]}, index=index)
    mix = portfolio.mix_returns(returns, np.array([0.75, 0.25]))
    assert np.exp(mix.iloc[0]) == pytest.approx(0.75 * 1.10 + 0.25 * 0.90)


def test_recent_volatility_never_looks_ahead() -> None:
    values = panel()["WILD"].to_numpy()
    before = portfolio.recent_volatility(values)
    changed = values.copy()
    changed[500:] *= 10
    after = portfolio.recent_volatility(changed)
    np.testing.assert_array_equal(before[:500], after[:500])
    assert after[520] > before[520] * 3
    assert np.isnan(before[: portfolio.WARM_UP]).all()
    assert not np.isnan(before[portfolio.WARM_UP :]).any()


def test_loss_limits_are_backtested_and_never_look_ahead() -> None:
    returns = panel()
    weights = np.array([0.2, 0.6, 0.2])
    mix = portfolio.mix_returns(returns, weights)
    limits = portfolio.loss_limits(mix)
    assert [h.horizon_days for h in limits] == [1, 7]
    assert [h.steps for h in limits] == [1, 5]
    for horizon in limits:
        assert horizon.shown in {"historical", "filtered"}
        assert [level.level for level in horizon.levels] == [0.95, 0.99]
        for level in horizon.levels:
            assert {m.method for m in level.methods} == {"historical", "filtered"}
            for method in level.methods:
                assert 0 < method.var <= method.expected_shortfall < 1
                assert method.backtest.n > 50
                assert 0 <= method.backtest.breach_rate < 0.2
    day, week = limits
    assert week.levels[0].methods[0].var > day.levels[0].methods[0].var
    assert day.levels[1].methods[0].var > day.levels[0].methods[0].var
    # Non-overlapping weeks: about a fifth as many tests as days.
    assert week.levels[0].methods[0].backtest.n < day.levels[0].methods[0].backtest.n / 4

    # The limit shown on a past day does not change when later days do.
    cut = 700
    inputs = portfolio.tail_risk.RiskInputs(
        returns=mix.to_numpy(),
        volatility_forecast=portfolio.recent_volatility(mix.to_numpy()),
        simulated_days=np.array([], dtype=int),
        simulated=np.empty((0, 0)),
    )
    later = mix.to_numpy().copy()
    later[cut + 1 :] *= 5
    changed = portfolio.tail_risk.RiskInputs(
        returns=later,
        volatility_forecast=portfolio.recent_volatility(later),
        simulated_days=np.array([], dtype=int),
        simulated=np.empty((0, 0)),
    )
    for key in [("historical", 0.95), ("filtered", 0.99)]:
        a = portfolio.tail_risk.estimate(inputs, 1).var[key][: cut + 1]
        b = portfolio.tail_risk.estimate(changed, 1).var[key][: cut + 1]
        np.testing.assert_array_equal(a, b)


def test_stress_replays_the_mix_and_names_what_is_missing() -> None:
    index = pd.DatetimeIndex(
        ["2022-05-03", "2022-05-04", "2022-05-05", "2022-05-06", "2022-05-09"], tz="UTC"
    ) + pd.Timedelta(hours=20)
    prices = pd.DataFrame(
        {
            "A": [100.0, 100.0, 80.0, 90.0, 60.0],
            "B": [50.0, 50.0, 50.0, 55.0, 55.0],
            "NEW": [np.nan, np.nan, np.nan, 10.0, 11.0],
        },
        index=index,
    )
    weights = np.array([0.4, 0.4, 0.2])
    episodes = [
        Episode(name="Fall", start=date(2022, 5, 4), end=date(2022, 5, 9)),
        Episode(name="Before history", start=date(2019, 1, 1), end=date(2019, 2, 1)),
    ]
    fall, early = portfolio.stress(prices, weights, episodes)

    assert fall.available
    assert fall.missing == ["NEW"]
    assert fall.covered_weight == pytest.approx(0.8)
    # A and B are half each of what is covered: -40% and +10%.
    assert fall.change == pytest.approx(0.5 * -0.40 + 0.5 * 0.10)
    assert [(p.symbol, round(p.change, 4), round(p.contribution, 4)) for p in fall.parts] == [
        ("A", -0.40, -0.20),
        ("B", 0.10, 0.05),
    ]
    assert sum(p.contribution for p in fall.parts) == pytest.approx(fall.change)
    assert fall.worst_day == date(2022, 5, 9)
    assert fall.worst_day_change == pytest.approx((0.30 + 0.55) / (0.45 + 0.55) - 1)
    assert fall.deepest_fall == pytest.approx(-0.15)

    assert not early.available
    assert early.missing == ["A", "B", "NEW"]
    assert early.change is None
