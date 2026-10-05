"""Walk-forward calibration and the conformal adjustment."""

import numpy as np
import pandas as pd
import pytest

from radar.models import calibration as cal


def market(n: int = 900, seed: int = 0) -> pd.DataFrame:
    """A market that alternates quiet and wild stretches of 60 days."""
    rng = np.random.default_rng(seed)
    wild = (np.arange(n) // 60) % 2 == 1
    volatility = np.where(wild, 0.04, 0.01)
    return pd.DataFrame(
        {"ret": rng.normal(0, volatility), "log_rv": np.log(volatility) + rng.normal(0, 0.1, n)},
        index=pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC"),
    )


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return market()


@pytest.fixture(scope="module")
def forecasts(frame: pd.DataFrame) -> dict[int, cal.ForecastSet]:
    return cal.walk_forward_forecasts(
        frame, (1, 7), min_train=500, refit_every=200, n_paths=400, seed=3
    )


def test_one_forecast_per_day_after_the_training_window(
    frame: pd.DataFrame, forecasts: dict[int, cal.ForecastSet]
) -> None:
    week = forecasts[7]
    assert list(week.origins) == list(range(500, 900))
    assert week.samples.shape == (400, 400)
    assert np.all(np.diff(week.samples, axis=1) >= 0)  # each row is sorted
    # The outcome is the sum of the next seven returns.
    returns = frame["ret"].to_numpy()
    assert week.realised[0] == pytest.approx(returns[501:508].sum())
    # The last seven forecasts have no outcome yet.
    assert np.isnan(week.realised[-7:]).all()
    assert not np.isnan(week.realised[:-7]).any()
    assert np.isnan(forecasts[1].realised).sum() == 1


def test_forecasts_have_no_lookahead(
    frame: pd.DataFrame, forecasts: dict[int, cal.ForecastSet]
) -> None:
    changed = frame.copy()
    later = changed.index[760:]
    changed.loc[later, "ret"] = 0.2
    changed.loc[later, "log_rv"] = 1.0
    again = cal.walk_forward_forecasts(
        changed, (1, 7), min_train=500, refit_every=200, n_paths=400, seed=3
    )
    # Forecasts made before day 760 used a model fitted earlier and returns up to their
    # own day, so rewriting later days cannot move them.
    early = forecasts[7].origins < 700
    assert np.array_equal(forecasts[7].samples[early], again[7].samples[early])
    assert np.array_equal(forecasts[1].baseline[early], again[1].baseline[early])


def test_coverage_is_close_to_nominal_on_a_market_the_model_fits(
    frame: pd.DataFrame, forecasts: dict[int, cal.ForecastSet]
) -> None:
    rows = cal.evaluate(forecasts, {1: 1, 7: 7}, pd.DatetimeIndex(frame.index))
    assert {(r.horizon_days, r.nominal) for r in rows} == {
        (h, level) for h in (1, 7) for level in (0.5, 0.8, 0.95)
    }
    for row in rows:
        assert row.empirical == pytest.approx(row.nominal, abs=0.12)
        assert row.empirical_conformal == pytest.approx(row.nominal, abs=0.08)
        assert 0 < row.conformal_miss_rate < 1
    day = next(r for r in rows if r.horizon_days == 1 and r.nominal == 0.8)
    assert day.n == 399
    assert day.first_origin == "2022-05-16"
    # A regime-aware forecast beats a constant-volatility one when volatility switches.
    assert day.pinball_model < day.pinball_baseline


def overconfident(n: int = 1500, steps: int = 1) -> cal.ForecastSet:
    """Forecasts whose ranges are half as wide as they should be."""
    rng = np.random.default_rng(1)
    samples = np.sort(rng.normal(0, 0.5, (n, 500)), axis=1).astype(np.float32)
    return cal.ForecastSet(
        steps=steps,
        origins=np.arange(n),
        samples=samples,
        realised=rng.normal(0, 1.0, n),
        baseline=np.zeros((n, len(cal.QUANTILE_LEVELS))),
    )


def test_conformal_adjustment_repairs_ranges_that_are_too_narrow() -> None:
    forecast = overconfident()
    raw = float(np.nanmean(cal.raw_hits(forecast, 0.8)))
    adjusted, miss_rate = cal.conformal_hits(forecast, 0.8)
    assert raw < 0.55  # the raw 80% range holds far less than 80% of the time
    assert float(np.nanmean(adjusted)) == pytest.approx(0.8, abs=0.04)
    assert miss_rate < 0.2  # it learned to ask for a wider range


def test_conformal_adjustment_learns_only_from_known_outcomes() -> None:
    forecast = overconfident(n=400, steps=30)
    hits, _ = cal.conformal_hits(forecast, 0.8)
    # Until the first 30-day outcome is known nothing can be learned, so the first 30
    # ranges are the raw ones.
    assert np.array_equal(hits[:30], cal.raw_hits(forecast, 0.8)[:30])
    # Changing outcomes that are not yet known at a forecast cannot change its hit.
    changed = cal.ForecastSet(
        steps=30,
        origins=forecast.origins,
        samples=forecast.samples,
        realised=np.concatenate([forecast.realised[:200], np.full(200, 9.0)]),
        baseline=forecast.baseline,
    )
    again, _ = cal.conformal_hits(changed, 0.8)
    assert np.array_equal(hits[:200], again[:200])
