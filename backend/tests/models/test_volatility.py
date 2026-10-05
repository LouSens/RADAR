"""The volatility forecast on series whose answers are known."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from radar.features.volatility import smoothed_log_volatility
from radar.models import volatility as vol


def series(values: list[float] | np.ndarray) -> pd.Series:
    index = pd.date_range("2021-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.Series(np.asarray(values, dtype=float), index=index)


def market(n: int = 900, seed: int = 0) -> pd.DataFrame:
    """Volatility that drifts slowly, as real volatility does, with noisy daily readings."""
    rng = np.random.default_rng(seed)
    log_level = np.empty(n)
    log_level[0] = np.log(0.02)
    for t in range(1, n):
        log_level[t] = np.log(0.02) + 0.97 * (log_level[t - 1] - np.log(0.02)) + rng.normal(0, 0.1)
    rv = series(np.exp(log_level + rng.normal(0, 0.25, n)))
    frame = pd.DataFrame({"ret": rng.normal(0, np.exp(log_level)), "rv": rv})
    frame["log_rv"] = smoothed_log_volatility(frame["rv"])
    return frame


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return market()


@pytest.fixture(scope="module")
def walks(frame: pd.DataFrame) -> dict[int, vol.WalkForward]:
    return vol.walk_forward(frame, (1, 7), min_train=500, refit_every=100)


def test_features_use_trailing_windows_only() -> None:
    rv = series(np.linspace(0.01, 0.05, 60))
    before = vol.har_features(rv)
    changed = rv.copy()
    changed.iloc[40:] = 9.0
    after = vol.har_features(changed)
    assert before.iloc[:40].equals(after.iloc[:40])
    # A week is the root mean square of the last five days, including today.
    assert before["log_week"].iloc[10] == pytest.approx(
        0.5 * np.log(np.mean(rv.iloc[6:11].to_numpy() ** 2))
    )
    assert before["log_month"].iloc[:21].isna().all()


def test_target_is_the_volatility_of_the_days_that_follow() -> None:
    rv = series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert vol.target(rv, 1).tolist()[:4] == [2.0, 3.0, 4.0, 5.0]
    assert np.isnan(vol.target(rv, 1).iloc[-1])
    week = vol.target(rv, 2)
    assert week.iloc[0] == pytest.approx(np.sqrt((4 + 9) / 2))
    assert week.iloc[-2:].isna().all()  # the future is not complete


def test_har_recovers_a_constant_and_round_trips(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    rv = series(0.02 * np.exp(rng.normal(0, 0.05, 400)))
    model = vol.fit(rv, 1)
    forecast = vol.predict(model, rv).dropna()
    assert forecast.mean() == pytest.approx(0.02, rel=0.03)
    assert model.n_train == 400 - 21 - 1
    path = tmp_path / "har.json"
    vol.save(model, path)
    assert vol.load(path) == model
    with pytest.raises(ValueError, match="at least 60"):
        vol.fit(rv.iloc[:50], 1)


def test_walk_forward_covers_every_day_after_training(
    frame: pd.DataFrame, walks: dict[int, vol.WalkForward]
) -> None:
    week = walks[7].forecasts
    assert list(week.columns) == ["har", "gbt", "carry", "regime", "realised"]
    assert len(week) == 400
    assert week.index[0] == frame.index[500]
    assert not week[list(vol.MODELS)].isna().any().any()
    assert (week[list(vol.MODELS)] > 0).all().all()
    # The last seven days have no outcome yet; one day for the one-day horizon.
    assert week["realised"].isna().sum() == 7
    assert walks[1].forecasts["realised"].isna().sum() == 1
    # Carrying forward is exactly the day's own reading.
    assert week["carry"].equals(frame["rv"].iloc[500:].rename("carry"))
    assert week["realised"].iloc[0] == pytest.approx(
        np.sqrt(np.mean(frame["rv"].iloc[501:508].to_numpy() ** 2))
    )
    assert walks[7].latest.train_end < frame.index[900 - 1].date()


def test_walk_forward_has_no_lookahead(
    frame: pd.DataFrame, walks: dict[int, vol.WalkForward]
) -> None:
    changed = frame.copy()
    later = changed.index[760:]
    changed.loc[later, "rv"] = 0.5
    changed.loc[later, "ret"] = 0.3
    changed["log_rv"] = smoothed_log_volatility(changed["rv"])
    again = vol.walk_forward(changed, (1, 7), min_train=500, refit_every=100)
    # Forecasts made in blocks that ended before day 760 cannot have moved.
    early = slice(0, 200)
    for steps in (1, 7):
        before = walks[steps].forecasts[list(vol.MODELS)].iloc[early]
        after = again[steps].forecasts[list(vol.MODELS)].iloc[early]
        assert before.equals(after)


def test_har_beats_carrying_yesterday_forward(walks: dict[int, vol.WalkForward]) -> None:
    for steps in (1, 7):
        result = vol.evaluate(walks[steps])
        scores = {s.model: s for s in result.scores}
        assert result.n == 400 - steps
        assert scores["har"].qlike < scores["carry"].qlike
        assert scores["har"].qlike < scores["regime"].qlike
        assert scores["har"].dm_p_value_vs_har is None
        carry_p = scores["carry"].dm_p_value_vs_har
        assert carry_p is not None
        assert carry_p < 0.05
        assert result.shown in {"har", "gbt"}
        # The trees are shown only when they are measurably better.
        trees = scores["gbt"]
        better = trees.qlike < scores["har"].qlike and (trees.dm_p_value_vs_har or 1) < 0.05
        assert (result.shown == "gbt") == better


def test_loss_functions_and_the_test_statistic() -> None:
    realised = np.array([0.02, 0.03])
    assert np.allclose(vol.qlike(realised, realised), 0.0)
    assert (vol.qlike(realised, realised * 2) > 0).all()
    assert vol.squared_error(realised, realised + 0.01) == pytest.approx([1e-4, 1e-4])

    rng = np.random.default_rng(2)
    noise = rng.normal(0, 1, 500)
    worse, better = noise**2 + 0.5, noise**2
    statistic, p_value = vol.diebold_mariano(better, worse + rng.normal(0, 0.1, 500))
    assert statistic < 0
    assert p_value < 0.001
    same, same_p = vol.diebold_mariano(rng.normal(0, 1, 500), rng.normal(0, 1, 500), steps=7)
    assert abs(same) < 3
    assert same_p > 0.01
    assert np.isnan(vol.diebold_mariano(np.ones(5), np.zeros(5))[0])
