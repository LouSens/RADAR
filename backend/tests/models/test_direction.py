"""The direction models' data handling and scoring, on inputs worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import technical
from radar.models import direction


def hourly(n: int = 900, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    spread = np.abs(rng.normal(0, 0.002, n))
    return pd.DataFrame(
        {
            "high": close * (1 + spread),
            "low": close * (1 - spread),
            "close": close,
            "volume": rng.uniform(1, 3, n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
    )


@pytest.mark.parametrize("build", [direction.bar_inputs, direction.summary_inputs])
def test_inputs_of_a_bar_do_not_change_when_later_bars_change(build) -> None:  # type: ignore[no-untyped-def]
    frame = hourly()
    cut = 700
    changed = frame.copy()
    changed.iloc[cut:, :] = changed.iloc[cut:, :] * 2.0
    assert build(frame).iloc[:cut].equals(build(changed).iloc[:cut])


def test_the_parts_are_in_time_order_with_a_gap_between_them() -> None:
    usable = np.ones(1000, dtype=bool)
    usable[:200] = False
    parts = direction.split(usable, horizon=24, window=48)
    assert parts.train.min() == 200
    assert parts.train.max() == 599
    assert parts.validation.min() == 600 + 72
    assert parts.validation.max() == 799
    assert parts.test.min() == 800 + 72
    # An answer in one part looks `horizon` bars ahead; that never reaches the next part's
    # first input window.
    assert parts.train.max() + 24 < parts.validation.min() - 47
    assert parts.validation.max() + 24 < parts.test.min() - 47


def test_a_row_is_usable_only_with_a_whole_window_and_a_known_answer() -> None:
    frame = hourly(400)
    table = direction.bar_inputs(frame)
    answers = technical.rises(frame["close"], 24)
    usable = direction.usable_rows(table, answers, 48)
    first = int(np.flatnonzero(usable)[0])
    # Volume needs 168 earlier bars, then 48 complete bars in a row.
    assert first == 168 + 47
    assert not usable[-24:].any()
    assert usable[first:-24].all()


def test_scaling_uses_the_training_rows_only() -> None:
    table = pd.DataFrame({"a": [1.0, 3.0, 100.0, -50.0]})
    values = direction.scaled(table, np.array([0, 1]))
    assert values[:2, 0].tolist() == [-1.0, 1.0]
    assert values[2, 0] == pytest.approx(98.0)
    changed = table.copy()
    changed.iloc[2:] = 0.0
    assert np.array_equal(direction.scaled(changed, np.array([0, 1]))[:2], values[:2])


def test_a_window_is_the_bars_ending_at_its_row() -> None:
    values = np.arange(10, dtype=float).reshape(10, 1)
    cut = direction.windows(values, np.array([3, 9]), length=3)
    assert cut.shape == (2, 3, 1)
    assert cut[0, :, 0].tolist() == [1.0, 2.0, 3.0]
    assert cut[1, :, 0].tolist() == [7.0, 8.0, 9.0]


def test_planted_answers_follow_their_rule() -> None:
    recent = pd.Series(np.tile([0.01, -0.01], 5000))
    answers = direction.planted_answers(recent, seed=1)
    assert answers[recent > 0].mean() == pytest.approx(0.65, abs=0.02)
    assert answers[recent < 0].mean() == pytest.approx(0.40, abs=0.02)


def test_scoring_counts_cases_one_horizon_apart_against_the_usual_answer() -> None:
    answers = np.tile([1.0, 1.0, 0.0, 1.0], 50)
    perfect = direction.score(answers.copy(), answers, usual_answer=1.0, horizon=1)
    assert perfect.n == 200
    assert perfect.accuracy == 1.0
    assert perfect.baseline == 0.75
    assert perfect.margin == pytest.approx(0.25)
    assert perfect.p_value < 0.001
    assert direction.passes(perfect, survives=True)
    assert not direction.passes(perfect, survives=False)
    thinned = direction.score(answers.copy(), answers, usual_answer=1.0, horizon=4)
    assert thinned.n == 50
    assert thinned.baseline == 1.0  # every fourth answer is "higher"

    always = direction.score(np.ones(200), answers, usual_answer=1.0, horizon=1)
    assert always.margin == 0.0
    assert always.said_higher == 1.0
    assert not direction.passes(always, survives=True)


def test_a_model_ahead_in_only_one_half_does_not_pass() -> None:
    answers = np.concatenate([np.tile([1.0, 0.0], 100), np.ones(200)])
    chance = np.concatenate([np.tile([1.0, 0.0], 100), np.ones(200)])
    result = direction.score(chance, answers, usual_answer=1.0, horizon=1)
    assert result.margin >= direction.MIN_MARGIN
    assert result.first_half_margin > 0
    assert result.second_half_margin == 0.0
    assert not direction.passes(result, survives=True)


def test_the_share_of_a_planted_gain_recovered() -> None:
    answers = np.tile([1.0, 1.0, 0.0, 1.0], 50)
    result = direction.score(answers.copy(), answers, usual_answer=1.0, horizon=1)
    assert direction.gain_recovered(result, knowing_the_rule=1.0) == pytest.approx(1.0)
    assert direction.gain_recovered(result, knowing_the_rule=0.75) == 0.0


def test_the_lstm_learns_a_pattern_that_is_plainly_there() -> None:
    pytest.importorskip("torch")
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, (1500, 8, 2)).astype(np.float32)
    y = (x[:, -3:, 0].sum(axis=1) > 0).astype(np.float32)
    predict = direction.fit_lstm(x[:1000], y[:1000], x[1000:1250], y[1000:1250], max_passes=25)
    right = ((predict(x[1250:]) > 0.5) == (y[1250:] == 1)).mean()
    assert right > 0.85
