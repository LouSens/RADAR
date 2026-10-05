"""Tail risk measures and their backtest, on inputs whose answers are known."""

import numpy as np
import pandas as pd
import pytest

from radar.models import tail_risk as risk


def inputs(returns: np.ndarray, volatility: np.ndarray | None = None) -> risk.RiskInputs:
    n = len(returns)
    return risk.RiskInputs(
        returns=returns,
        volatility_forecast=np.full(n, np.nan) if volatility is None else volatility,
        simulated_days=np.array([], dtype=int),
        simulated=np.empty((0, 0)),
    )


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")


def test_forward_returns_sum_the_days_that_follow() -> None:
    returns = np.array([0.01, 0.02, 0.03, 0.04])
    assert risk.forward_returns(returns, 1)[:3] == pytest.approx([0.02, 0.03, 0.04])
    assert np.isnan(risk.forward_returns(returns, 1)[3])
    two = risk.forward_returns(returns, 2)
    assert two[:2] == pytest.approx([0.05, 0.07])
    assert np.isnan(two[2:]).all()


def test_var_and_shortfall_match_a_hand_calculation() -> None:
    # 100 outcomes: losses of 1% to 100% in simple terms.
    losses = np.arange(1, 101) / 100.0
    outcomes = np.log(1.0 - np.minimum(losses, 0.999))
    var, shortfall = risk.tail(outcomes, 0.95)
    assert var == pytest.approx(0.9505, abs=1e-4)
    assert shortfall == pytest.approx(np.mean([0.96, 0.97, 0.98, 0.99, 0.999]), abs=1e-4)
    assert shortfall > var
    # Gains only: there is no loss to report.
    assert risk.tail(np.full(50, 0.01), 0.95)[0] < 0


def test_estimates_use_only_outcomes_complete_by_the_day() -> None:
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.02, 700)
    first = risk.estimate(inputs(returns), steps=5)
    changed = returns.copy()
    changed[600:] = -0.5
    second = risk.estimate(inputs(changed), steps=5)
    key = ("historical", 0.95)
    # An estimate for day 599 or earlier cannot see day 600 onward.
    assert np.array_equal(first.var[key][:600], second.var[key][:600], equal_nan=True)
    assert not np.array_equal(first.var[key][600:], second.var[key][600:], equal_nan=True)
    # Too little history at the start: no estimate.
    assert np.isnan(first.var[key][: risk.MIN_WINDOW + 4]).all()
    assert not np.isnan(first.var[key][risk.MIN_WINDOW + 4])
    assert np.isnan(first.var[("filtered", 0.95)]).all()  # no forecasts were given
    assert first.es[key][650] >= first.var[key][650]


def test_filtered_estimates_follow_the_volatility_forecast() -> None:
    rng = np.random.default_rng(1)
    n = 900
    volatility = np.where(np.arange(n) < 800, 0.01, 0.04)
    returns = rng.normal(0, volatility)
    made = np.roll(volatility, -1)  # the forecast made on day t for day t+1, here exact
    result = risk.estimate(inputs(returns, made), steps=1)
    filtered = result.var[("filtered", 0.99)]
    historical = result.var[("historical", 0.99)]
    # When volatility quadruples, the filtered limit widens at once; history lags.
    assert filtered[810] == pytest.approx(4 * filtered[790], rel=0.25)
    assert historical[810] < 2 * historical[790]


def test_simulator_estimates_come_from_that_days_simulation() -> None:
    rng = np.random.default_rng(2)
    returns = rng.normal(0, 0.02, 400)
    simulated = rng.normal(0, 0.02, (2, 4000))
    given = risk.RiskInputs(returns, np.full(400, np.nan), np.array([300, 301]), simulated)
    result = risk.estimate(given, steps=1)
    key = ("simulator", 0.95)
    assert result.var[key][300] == pytest.approx(1 - np.exp(-1.645 * 0.02), rel=0.08)
    assert np.isnan(result.var[key][299])
    assert not np.isnan(result.var[key][301])


def test_kupiec_accepts_the_stated_rate_and_rejects_a_wrong_one() -> None:
    assert risk.kupiec(50, 1000, 0.95) == pytest.approx(1.0)
    assert risk.kupiec(52, 1000, 0.95) > 0.5
    assert risk.kupiec(90, 1000, 0.95) < 0.001  # broken far too often
    assert risk.kupiec(20, 1000, 0.95) < 0.001  # far too cautious
    assert risk.kupiec(0, 1000, 0.99) < 0.001
    assert np.isnan(risk.kupiec(0, 0, 0.95))


def test_christoffersen_detects_breaches_that_cluster() -> None:
    rng = np.random.default_rng(3)
    scattered = rng.random(2000) < 0.05
    assert risk.christoffersen(scattered) > 0.05
    clustered = np.zeros(2000, dtype=bool)
    for start in range(100, 2000, 200):
        clustered[start : start + 10] = True  # the same number of breaches, in runs
    assert risk.christoffersen(clustered) < 0.001
    assert np.isnan(risk.christoffersen(np.zeros(100, dtype=bool)))


def test_backtest_counts_breaches_over_periods_that_do_not_overlap() -> None:
    rng = np.random.default_rng(4)
    n = 2000
    returns = rng.normal(0, 0.02, n)
    estimates = risk.estimate(inputs(returns), steps=5)
    rows = risk.backtest(estimates, days(n))
    assert {(r.method, r.level) for r in rows} == {("historical", 0.95), ("historical", 0.99)}
    row = next(r for r in rows if r.level == 0.95)
    usable = n - (risk.MIN_WINDOW + 4) - 5
    assert row.n == -(-usable // 5)  # every fifth day
    assert row.expected_breaches == pytest.approx(row.n * 0.05)
    assert row.breach_rate == pytest.approx(0.05, abs=0.03)
    assert row.reliable
    assert row.first_day == days(n)[risk.MIN_WINDOW + 4].date()


def test_a_limit_that_breaks_too_often_is_marked_unreliable() -> None:
    rng = np.random.default_rng(5)
    n = 1500
    returns = rng.normal(0, 0.02, n)
    estimates = risk.estimate(inputs(returns), steps=1)
    estimates.var[("historical", 0.95)] *= 0.4  # a limit set far too tight
    row = next(r for r in risk.backtest(estimates, days(n)) if r.level == 0.95)
    assert row.breach_rate > 0.15
    assert not row.reliable


def score(method: str, level: float, rate: float, reliable: bool = True) -> risk.Backtest:
    return risk.Backtest(
        method=method,
        level=level,
        n=1000,
        breaches=int(rate * 1000),
        expected_breaches=1000 * (1 - level),
        breach_rate=rate,
        kupiec_p_value=0.5 if reliable else 0.001,
        clustering_p_value=0.5,
        reliable=reliable,
        first_day=days(1)[0].date(),
        last_day=days(1)[0].date(),
    )


def test_the_method_shown_is_the_one_with_the_best_backtest() -> None:
    rows = [
        score("historical", 0.95, 0.070, reliable=False),
        score("historical", 0.99, 0.011),
        score("filtered", 0.95, 0.052),
        score("filtered", 0.99, 0.013),
        score("simulator", 0.95, 0.058),
        score("simulator", 0.99, 0.016),
    ]
    assert risk.choose(rows) == "filtered"
    # A method with an unreliable limit loses to one without, however close its rates.
    rows[2] = score("filtered", 0.95, 0.051, reliable=False)
    rows[3] = score("filtered", 0.99, 0.010, reliable=False)
    assert risk.choose(rows) == "simulator"
    assert risk.choose([]) is None


def test_worst_drawdowns_are_found_with_their_dates() -> None:
    close = pd.Series(
        [100, 110, 88, 99, 112, 120, 60, 90, 80, 125, 100], index=days(11), dtype=float
    )
    worst = risk.worst_drawdowns(close, count=2)
    assert [round(d.depth, 3) for d in worst] == [-0.5, -0.2]
    deep = worst[0]
    assert deep.peak_day == days(11)[5].date()
    assert deep.trough_day == days(11)[6].date()
    assert deep.recovered_day == days(11)[9].date()
    # The fall still under way at the end has no recovery date.
    everything = risk.worst_drawdowns(close, count=5)
    assert len(everything) == 3
    assert everything[1].recovered_day == days(11)[4].date()
    assert everything[2].depth == pytest.approx(-0.2)
    assert everything[2].recovered_day is None
    assert risk.worst_drawdowns(pd.Series(dtype=float)) == []
