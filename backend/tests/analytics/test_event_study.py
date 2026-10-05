"""The event study, lead-lag correlations, and the verdict rule, on built examples."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import event_study as es


def days(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")


def series(values: np.ndarray | list[float]) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=float), index=days(len(values)))


def test_zscore_uses_earlier_days_only() -> None:
    rng = np.random.default_rng(0)
    tone = series(rng.normal(0, 0.1, 300))
    before = es.zscore(tone)
    changed = tone.copy()
    changed.iloc[200:] = 5.0
    after = es.zscore(changed)
    assert before.iloc[:200].equals(after.iloc[:200])
    assert before.iloc[: es.ZSCORE_MIN].isna().all()
    # Day 200 is judged against days before it, so its own jump shows up in full.
    assert after.iloc[200] > 20
    flat = es.zscore(series(np.zeros(100)))
    assert flat.isna().all()  # no variation: nothing is unusual


def test_events_are_days_beyond_the_threshold_merged_when_close() -> None:
    z = series(np.zeros(40))
    z.iloc[[5, 6, 7, 20, 30]] = [2.5, 3.0, -4.0, -2.1, 1.9]
    events = es.find_events(z)
    # Days 6 and 7 fall within three days of day 5 and belong to it.
    assert [(e.position, e.sign) for e in events] == [(5, 1), (20, -1)]
    z.iloc[8] = 2.5
    assert [e.position for e in es.find_events(z)] == [5, 8, 20]


def test_paths_remove_the_usual_drift_and_skip_incomplete_windows() -> None:
    returns = series(np.full(200, 0.001))
    returns.iloc[101] = 0.051  # a 5% jump the day after day 100
    paths = es.abnormal_paths(returns, [100, 2, 198])
    assert paths.shape == (1, 5)  # day 2 has no history; day 198 has no future
    assert paths[0] == pytest.approx([0.0, 0.0, 0.05, 0.05, 0.05])
    # The drift comes from before the window: changing later days cannot move it.
    later = returns.copy()
    later.iloc[110:] = 0.5
    assert np.array_equal(es.abnormal_paths(later, [100]), paths)
    assert es.abnormal_paths(returns, []).shape == (0, 5)


def test_average_path_has_a_band_that_contains_the_mean() -> None:
    rng = np.random.default_rng(1)
    paths = np.cumsum(rng.normal(0.01, 0.02, (60, 5)), axis=1)
    result = es.average_path(paths)
    assert result.n == 60
    assert result.offsets == [-1, 0, 1, 2, 3]
    assert all(lo < m < hi for lo, m, hi in zip(result.low, result.mean, result.high, strict=True))
    assert result.low[-1] > 0  # a real drift of 1% a day is clear of zero by the end
    assert es.average_path(np.empty((0, 5))).n == 0


def test_random_days_avoid_events_and_match_the_regime() -> None:
    labels = np.array(["calm"] * 50 + ["turbulent"] * 50)
    events = [es.Event(10, 1), es.Event(70, -1)]
    picks = es.matched_positions(events, labels, 100, seed=3)
    assert picks[0] < 50 <= picks[1]
    assert not {10, 70} & set(picks)
    assert len(es.matched_positions(events, None, 100)) == 2


def test_lead_lag_finds_which_series_comes_first() -> None:
    rng = np.random.default_rng(2)
    n = 1500
    tone = rng.normal(0, 1, n)
    # Returns follow yesterday's tone.
    follows = series(0.3 * np.roll(tone, 1) + rng.normal(0, 1, n))
    lags = {c.lag: c for c in es.lead_lag(series(tone), follows)}
    assert lags[1].significant
    assert lags[1].correlation > 0.2
    assert not lags[-1].significant
    assert lags[0].n == n
    assert lags[5].n == n - 5
    # Tone follows yesterday's return.
    returns = rng.normal(0, 1, n)
    chasing = series(0.3 * np.roll(returns, 1) + rng.normal(0, 1, n))
    reverse = {c.lag: c for c in es.lead_lag(chasing, series(returns))}
    assert reverse[-1].significant
    assert not reverse[1].significant


def lag(k: int, correlation: float, significant: bool) -> es.LagCorrelation:
    return es.LagCorrelation(lag=k, correlation=correlation, n=1000, significant=significant)


def test_verdict_rule() -> None:
    quiet = [lag(k, 0.01, False) for k in range(-5, 6)]
    assert es.verdict(29, quiet) == "not enough events"
    assert es.verdict(30, quiet) == "no measurable relationship"
    tone_first = [*quiet, lag(2, 0.12, True)]
    assert es.verdict(40, tone_first) == "sentiment leads price"
    price_first = [*quiet, lag(-1, -0.15, True)]
    assert es.verdict(40, price_first) == "price leads sentiment"
    # Both sides significant: the stronger one decides.
    assert es.verdict(40, [*tone_first, lag(-1, -0.15, True)]) == "price leads sentiment"
    # A same-day link cannot say which came first.
    assert es.verdict(40, [*quiet, lag(0, 0.5, True)]) == "no measurable relationship"
    # Too few events wins over everything.
    assert es.verdict(5, tone_first) == "not enough events"
    assert set(es.VERDICTS) >= {es.verdict(40, tone_first), es.verdict(5, quiet)}


def test_study_reports_no_relationship_for_unrelated_series() -> None:
    rng = np.random.default_rng(4)
    n = 1200
    result = es.study(series(rng.normal(0, 0.2, n)), series(rng.normal(0, 0.02, n)))
    assert result.n_events >= 30
    assert result.n_positive + result.n_negative == result.n_events
    assert result.verdict == "no measurable relationship"
    assert result.baseline.n > 0
    assert len(result.lags) == 11
    assert result.first_day == "2022-01-01"


def test_study_says_not_enough_events_for_thin_news() -> None:
    rng = np.random.default_rng(5)
    tone = series(np.full(400, np.nan))
    tone.iloc[::9] = rng.normal(0, 0.2, len(tone.iloc[::9]))  # news on one day in nine
    result = es.study(tone, series(rng.normal(0, 0.01, 400)))
    assert result.n_events < 30
    assert result.verdict == "not enough events"


def study_with(p_values: dict[int, float], n_events: int = 40) -> es.EventStudy:
    empty = es.average_path(np.empty((0, 5)))
    lags = [
        es.LagCorrelation(lag=k, correlation=0.1, n=1000, significant=p < 0.005, p_value=p)
        for k, p in p_values.items()
    ]
    return es.EventStudy(
        verdict=es.verdict(n_events, lags),
        n_events=n_events,
        n_positive=n_events,
        n_negative=0,
        n_days=1000,
        first_day=None,
        last_day=None,
        positive=empty,
        negative=empty,
        baseline=empty,
        lags=lags,
    )


def test_a_family_of_studies_is_judged_together() -> None:
    quiet = dict.fromkeys(range(-5, 6), 0.6)
    # A p-value of 0.004 passes on its own, but not as one of 44 tests.
    lucky = study_with({**quiet, 2: 0.004})
    assert lucky.verdict == "sentiment leads price"
    family = es.correct_family([lucky, study_with(quiet), study_with(quiet), study_with(quiet)])
    assert family[0].verdict == "no measurable relationship"
    assert not any(lag.significant for lag in family[0].lags)

    # A strong result survives the correction.
    strong = study_with({**quiet, -1: 1e-9})
    family = es.correct_family([strong, study_with(quiet), study_with(quiet)])
    assert family[0].verdict == "price leads sentiment"
    assert [lag.lag for lag in family[0].lags if lag.significant] == [-1]
    # Too few events still means no verdict, whatever the p-values.
    thin = es.correct_family([study_with({**quiet, -1: 1e-9}, n_events=5)])
    assert thin[0].verdict == "not enough events"


def test_lag_p_values_are_small_only_for_real_links() -> None:
    rng = np.random.default_rng(6)
    tone = rng.normal(0, 1, 1500)
    follows = series(0.3 * np.roll(tone, 1) + rng.normal(0, 1, 1500))
    lags = {c.lag: c for c in es.lead_lag(series(tone), follows)}
    assert lags[1].p_value is not None
    assert lags[1].p_value < 1e-10
    assert lags[-3].p_value is not None
    assert lags[-3].p_value > 0.01
