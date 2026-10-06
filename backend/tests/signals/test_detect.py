"""The signal rules on series whose answers can be worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.signals import detect

DAYS = pd.date_range("2024-01-01", periods=8, tz="UTC")


def states(labels: list[str], probabilities: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"label": labels, "probability": probabilities}, index=DAYS[: len(labels)])


def test_a_change_of_state_counts_only_when_the_new_state_is_probable_enough() -> None:
    found = detect.regime_changes(
        states(
            ["calm", "calm", "turbulent", "turbulent", "calm", "calm"],
            [0.9, 0.9, 0.6, 0.85, 0.7, 0.95],
        )
    )
    # Day 3 changed but at 60%; it counts on day 4 at 85%. Day 5 is at exactly 70%,
    # which does not exceed the threshold; the change back counts on day 6.
    assert [(o.day, o.variant) for o in found] == [
        (DAYS[3], "to turbulent"),
        (DAYS[5], "to calm"),
    ]
    assert found[0].detail == {"from": "calm", "to": "turbulent", "probability": 0.85}


def test_a_day_of_doubt_does_not_turn_one_change_into_two() -> None:
    found = detect.regime_changes(states(["calm", "normal", "calm", "calm"], [0.9, 0.55, 0.9, 0.9]))
    assert found == []


def observations(n: int = 640, seed: int = 3) -> pd.DataFrame:
    """Calm and rough stretches, long enough to fit the regime model on."""
    rng = np.random.default_rng(seed)
    rough = (np.arange(n) // 80) % 2 == 1
    volatility = np.where(rough, 0.03, 0.008) * np.exp(rng.normal(0, 0.1, n))
    return pd.DataFrame(
        {"ret": rng.normal(0, 1, n) * volatility, "log_rv": np.log(volatility), "rv": volatility},
        index=pd.date_range("2020-01-01", periods=n, tz="UTC"),
    )


def test_past_states_never_see_later_days() -> None:
    data = observations()
    known = detect.walk_forward_states(data, min_train=500, step=63)
    assert known.index[0] == data.index[500]
    assert len(known) == len(data) - 500
    assert set(known["label"]) <= {"calm", "normal", "turbulent"}
    assert known["probability"].between(0, 1).all()

    # Rewrite everything from day 600 on. The second refit happens at day 563, before
    # it, so every state up to day 599 must be exactly as it was.
    changed = data.copy()
    late = changed.index[600:]
    changed.loc[late, "log_rv"] = changed.loc[late, "log_rv"] + 3.0
    changed.loc[late, "ret"] = changed.loc[late, "ret"] * 20.0
    again = detect.walk_forward_states(changed, min_train=500, step=63)
    pd.testing.assert_frame_equal(known.iloc[:100], again.iloc[:100])
    assert not known.iloc[100:].equals(again.iloc[100:])


def test_too_little_history_gives_no_states() -> None:
    assert detect.walk_forward_states(observations(300), min_train=500).empty


def hourly(sizes: dict[int, float], hours: int = 24) -> tuple[pd.Series, pd.Index, pd.Series]:
    """Hourly returns alternating +size and -size on each day, all days calm."""
    n_days = len(sizes)
    stamps = pd.date_range("2024-01-01", periods=n_days * hours, freq="h", tz="UTC")
    values = np.concatenate(
        [sizes[d] * np.where(np.arange(hours) % 2 == 0, 1.0, -1.0) for d in range(n_days)]
    )
    days = stamps.floor("D")
    labels = pd.Series("calm", index=pd.date_range("2024-01-01", periods=n_days, tz="UTC"))
    return pd.Series(values, index=stamps), days, labels


def test_the_usual_size_of_an_hour_comes_from_earlier_days_in_the_same_state() -> None:
    returns, days, labels = hourly({0: 0.01, 1: 0.01, 2: 0.01, 3: 0.05})
    labels.iloc[2] = "turbulent"  # so day 3 is entered in the turbulent state
    size = detect.usual_hourly_size(returns, days, labels, min_hours=24)
    by_day = size.groupby(days).first()
    # Day 0 has no state going in. Day 1 has no earlier calm day. Day 2 has one.
    assert np.isnan(by_day.iloc[0])
    assert np.isnan(by_day.iloc[1])
    assert by_day.iloc[2] == pytest.approx(0.01)
    # Day 3 is entered turbulent, and no earlier day was: nothing to measure against.
    assert np.isnan(by_day.iloc[3])
    # A day's own hours never count towards its own usual size.
    bigger = returns.copy()
    bigger[days == days[2 * 24]] *= 10
    again = detect.usual_hourly_size(bigger, days, labels, min_hours=24).groupby(days).first()
    assert again.iloc[2] == pytest.approx(0.01)


def test_an_abnormal_move_is_flagged_once_a_day_with_its_direction() -> None:
    returns, days, labels = hourly(dict.fromkeys(range(12), 0.01))
    returns.iloc[10 * 24 + 5] = -0.045  # 4.5 times the usual size, at 05:00 on day 10
    returns.iloc[10 * 24 + 9] = 0.08  # a second one the same day is not another signal
    returns.iloc[11 * 24 + 2] = 0.025  # 2.5 times: not abnormal
    found = detect.abnormal_moves(returns, days, labels, min_hours=48)
    (only,) = found
    assert (only.day, only.variant) == (pd.Timestamp("2024-01-11", tz="UTC"), "down")
    assert only.detail["hour"] == "2024-01-11T05:00:00+00:00"
    assert only.detail["usual"] == pytest.approx(0.01)
    assert only.detail["multiple"] == pytest.approx(4.5)


def test_unusual_news_tone_is_measured_against_the_days_before_it() -> None:
    rng = np.random.default_rng(1)
    tone = pd.Series(
        rng.normal(0, 0.1, 200), index=pd.date_range("2023-01-01", periods=200, tz="UTC")
    )
    tone.iloc[150] = 1.5
    tone.iloc[151] = 1.4  # the next day belongs to the same shock
    tone.iloc[180] = -1.5
    found = detect.sentiment_shocks(tone)
    picked = [(o.day, o.variant) for o in found if abs(o.detail["z"]) > 5]
    assert picked == [(tone.index[150], "positive"), (tone.index[180], "negative")]
    # A later day cannot change an earlier day's reading.
    changed = tone.copy()
    changed.iloc[160:] = 9.0
    earlier = [o for o in detect.sentiment_shocks(changed) if o.day < tone.index[160]]
    assert [(o.day, o.variant) for o in earlier] == [
        (o.day, o.variant) for o in found if o.day < tone.index[160]
    ]
