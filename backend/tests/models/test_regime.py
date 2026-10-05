"""The regime model on synthetic markets whose true states are known."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from radar.models import regime

# True states: calm, normal, turbulent, with the daily volatility of each.
TRUE_VOL = np.array([0.008, 0.02, 0.055])
TRUE_STAY = 0.96


def synthetic(n: int = 1500, seed: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    """A market that switches between three volatility states and stays in each a while."""
    rng = np.random.default_rng(seed)
    states = np.empty(n, dtype=int)
    states[0] = 1
    for t in range(1, n):
        if rng.random() < TRUE_STAY:
            states[t] = states[t - 1]
        else:
            states[t] = rng.choice([s for s in range(3) if s != states[t - 1]])
    vol = TRUE_VOL[states]
    frame = pd.DataFrame(
        {
            "ret": rng.normal(0, vol),
            # Realised volatility measures the true level with some noise.
            "log_rv": np.log(vol) + rng.normal(0, 0.25, n),
        },
        index=pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC"),
    )
    return frame, states


@pytest.fixture(scope="module")
def market() -> tuple[pd.DataFrame, np.ndarray]:
    return synthetic()


@pytest.fixture(scope="module")
def model(market: tuple[pd.DataFrame, np.ndarray]) -> regime.RegimeModel:
    return regime.fit(market[0], n_init=3)


def test_fit_recovers_three_states_ordered_by_volatility(
    market: tuple[pd.DataFrame, np.ndarray], model: regime.RegimeModel
) -> None:
    assert model.n_states == 3
    assert model.labels == ("calm", "normal", "turbulent")
    assert min(model.bic_by_states, key=lambda k: model.bic_by_states[k]) == 3
    summary = regime.transition_summary(model)
    volatility = [s.typical_daily_volatility for s in summary]
    assert volatility == sorted(volatility)
    assert volatility == pytest.approx(TRUE_VOL, rel=0.25)
    # Each true state lasts 25 days on average (1 / (1 - 0.96)).
    assert all(10 < s.typical_duration_days < 60 for s in summary)
    for s in summary:
        assert sum(s.next_states.values()) == pytest.approx(1.0)
        assert s.label not in s.next_states


def test_filtered_states_match_the_truth_most_days(
    market: tuple[pd.DataFrame, np.ndarray], model: regime.RegimeModel
) -> None:
    frame, states = market
    predicted = regime.predict(model, frame)
    truth = pd.Series(np.array(model.labels)[states], index=frame.index)
    assert (predicted == truth).mean() > 0.85
    probabilities = regime.filtered_probabilities(model, frame)
    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert list(probabilities.columns) == list(model.labels)


def test_filtered_probabilities_have_no_lookahead(
    market: tuple[pd.DataFrame, np.ndarray], model: regime.RegimeModel
) -> None:
    frame, _ = market
    cut = 900
    full = regime.filtered_probabilities(model, frame)
    # Using only the first days gives the same answers for those days...
    truncated = regime.filtered_probabilities(model, frame.iloc[:cut])
    pd.testing.assert_frame_equal(full.iloc[:cut], truncated)
    # ...and so does rewriting everything that came after them.
    later = frame.index[cut:]
    changed = frame.copy()
    changed.loc[later, "ret"] = 0.5
    changed.loc[later, "log_rv"] = 3.0
    rewritten = regime.filtered_probabilities(model, changed)
    pd.testing.assert_frame_equal(full.iloc[:cut], rewritten.iloc[:cut])


def test_smoothed_probabilities_do_use_later_days(
    market: tuple[pd.DataFrame, np.ndarray], model: regime.RegimeModel
) -> None:
    frame, _ = market
    cut = 900
    full = regime.smoothed_probabilities(model, frame)
    truncated = regime.smoothed_probabilities(model, frame.iloc[:cut])
    # The hindsight view of a day changes once later days are known, which is exactly
    # why it must never be shown as the current state.
    assert not np.allclose(full.iloc[cut - 5 : cut], truncated.iloc[-5:])
    # On the last day there is nothing later to use, so the two views agree.
    filtered = regime.filtered_probabilities(model, frame)
    assert np.allclose(full.iloc[-1], filtered.iloc[-1])


def test_labels_are_stable_across_refits_on_overlapping_data(
    market: tuple[pd.DataFrame, np.ndarray],
) -> None:
    frame, _ = market
    early = regime.fit(frame.iloc[:1100], candidates=(3,), n_init=3, seed=1)
    late = regime.fit(frame.iloc[:1500], candidates=(3,), n_init=3, seed=99)
    overlap = frame.iloc[:1100]
    agreement = (regime.predict(early, overlap) == regime.predict(late, overlap)).mean()
    assert agreement > 0.9


def test_scaling_is_fitted_on_the_training_window_only(
    market: tuple[pd.DataFrame, np.ndarray],
) -> None:
    frame, _ = market
    train = frame.iloc[:800]
    fitted = regime.fit(train, candidates=(3,), n_init=2)
    assert fitted.feature_mean == pytest.approx(train.mean().tolist())
    assert fitted.n_train == 800
    assert fitted.train_end == train.index[-1].date()


def test_predictive_density_sums_to_the_log_likelihood(
    market: tuple[pd.DataFrame, np.ndarray], model: regime.RegimeModel
) -> None:
    frame, _ = market
    density = regime.predictive_log_density(model, frame)
    scale = float(np.sum(np.log(model.feature_std))) * len(frame)
    assert density.sum() + scale == pytest.approx(model.log_likelihood, rel=1e-6)


def test_save_and_load_round_trip(model: regime.RegimeModel, tmp_path: Path) -> None:
    path = tmp_path / "models" / "regime.json"
    regime.save(model, path)
    assert regime.load(path) == model


def test_too_little_history_is_refused(market: tuple[pd.DataFrame, np.ndarray]) -> None:
    with pytest.raises(ValueError, match="at least"):
        regime.fit(market[0].iloc[:100])


def test_walk_forward_orders_next_day_volatility_by_state(
    market: tuple[pd.DataFrame, np.ndarray],
) -> None:
    frame, _ = market
    result = regime.evaluate(frame, min_train=700, step=100, n_init=2)
    assert result.n_days == 800
    assert result.n_refits == 8
    assert result.volatility_is_ordered
    volatility = result.next_day_volatility
    assert volatility["calm"] < volatility["normal"] < volatility["turbulent"]
    assert result.model_log_density > result.baseline_log_density
    assert result.average_run_length > 5
    assert sum(result.days_per_state.values()) == result.n_days
