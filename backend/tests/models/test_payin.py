"""The paying-in ensemble's inputs, answers, time order and scoring."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from radar.models import payin


def market(n: int = 700, seed: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    spread = np.abs(rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.005, n)),
            "high": close * (1 + spread),
            "low": close * (1 - spread),
            "close": close,
            "volume": rng.uniform(1, 3, n),
        },
        index=pd.date_range("2022-01-01", periods=n, freq="D"),
    )


def wider(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"]
    return payin.context(close, close * 0.5, close**0.5, close**0.25)


EVENTS = [date(2022, 6, 15), date(2023, 3, 22)]


def test_inputs_of_a_day_do_not_change_when_later_days_change() -> None:
    frame = market()
    cut = 600
    changed = frame.copy()
    changed.iloc[cut:] = changed.iloc[cut:] * 2
    before = payin.inputs(frame, EVENTS, wider(frame), "crypto")
    after = payin.inputs(changed, EVENTS, wider(changed), "crypto")
    assert list(before.columns) == list(payin.INPUTS)
    pd.testing.assert_frame_equal(before.iloc[:cut], after.iloc[:cut])
    assert not before.iloc[300:cut].isna().any().any()


def test_a_weekend_market_carries_the_funds_last_close_forward() -> None:
    frame = market(400)
    funds = wider(frame)
    weekdays = funds[pd.DatetimeIndex(funds.index).dayofweek < 5]
    table = payin.inputs(frame, EVENTS, weekdays, "crypto")
    saturday = next(d for d in frame.index[300:] if d.dayofweek == 5)
    friday = saturday - pd.Timedelta(days=1)
    assert table.loc[saturday, "stocks_ret_20"] == weekdays.loc[friday, "stocks_ret_20"]
    assert table.loc[saturday, "is_crypto"] == 1.0
    assert table.loc[saturday, "is_bonds"] == 0.0


def test_days_left_counts_down_within_each_month() -> None:
    left = payin.days_left(8, np.array([1, 4]), every=3)
    assert np.isnan(left[0])
    assert np.isnan(left[7])
    assert left[1:7].tolist() == [2, 1, 0, 2, 1, 0]


def test_the_first_answer_compares_today_with_the_average_of_the_days_left() -> None:
    close = pd.Series([10.0, 12.0, 11.0, 9.0, 8.0, 10.0, 99.0])
    answer = payin.cheaper_than_rest(close, np.array([0, 3]), every=3)
    # Month one: 10 against 11.5 is cheaper; 12 against 11 is not; the last day has none.
    assert answer.iloc[:3].tolist()[:2] == [1.0, 0.0]
    assert np.isnan(answer.iloc[2])
    # Month two: 9 against 9 is not below; 8 against 10 is.
    assert answer.iloc[3:5].tolist() == [0.0, 1.0]
    assert np.isnan(answer.iloc[5])
    assert np.isnan(answer.iloc[6])


def test_a_dip_is_a_later_close_far_enough_below_and_unknown_near_the_end() -> None:
    close = pd.Series([100.0, 100.0, 94.0, 100.0, 96.0, 100.0])
    answer = payin.dips(close, drop=0.05, days=2)
    assert answer.iloc[:4].tolist() == [1.0, 1.0, 0.0, 0.0]
    assert answer.iloc[4:].isna().all()
    changed = close.copy()
    changed.iloc[5] = 1.0
    assert payin.dips(changed, drop=0.05, days=2).iloc[:3].tolist() == [1.0, 1.0, 0.0]


def test_the_share_so_far_uses_only_answers_whose_days_have_passed() -> None:
    answers = pd.Series(np.tile([1.0, 0.0], 100))
    share = payin.own_share_so_far(answers, days=5)
    assert share.iloc[:65].isna().all()
    changed = answers.copy()
    changed.iloc[151:] = 1.0
    # The answer for day 151 is known on day 157 and not before.
    later = payin.own_share_so_far(changed, days=5)
    assert share.iloc[:157].equals(later.iloc[:157])
    assert later.iloc[157] != share.iloc[157]


def test_folds_keep_fitting_validation_and_test_apart_and_in_order() -> None:
    days = pd.date_range("2018-01-01", "2022-12-31", freq="D").to_numpy()
    folds = payin.by_year(days, 2021, 2022)
    assert [f.year for f in folds] == [2021, 2022]
    for fold in folds:
        fit, validation, test = days[fold.fit], days[fold.validation], days[fold.test]
        gap = np.timedelta64(payin.GAP_DAYS, "D")
        assert validation.min() - fit.max() > gap - np.timedelta64(1, "D")
        assert test.min() - validation.max() > gap - np.timedelta64(1, "D")
        assert pd.Timestamp(test.min()).year == fold.year == pd.Timestamp(test.max()).year
    assert len(folds[1].fit) > len(folds[0].fit)


def test_the_vote_finds_a_planted_pattern_and_is_the_average_of_its_members() -> None:
    rng = np.random.default_rng(2)
    table = pd.DataFrame(
        {
            "stoch_fast": rng.random(6000),
            "ret_20": rng.normal(size=6000),
            "noise": rng.normal(size=6000),
        }
    )
    answers = payin.planted_answers(table, seed=3).to_numpy()
    x = table.to_numpy()
    vote = payin.fit_vote(
        x[:3000], answers[:3000], x[3000:4500], answers[3000:4500], only=("logistic", "boosted")
    )
    chances = vote.chances(x[4500:])
    assert set(chances) == {"logistic", "boosted", "vote"}
    assert np.allclose(chances["vote"], (chances["logistic"] + chances["boosted"]) / 2)
    truth = payin.planted_chance(table.iloc[4500:])
    marked = truth == payin.PLANTED_HIGH
    assert chances["boosted"][marked].mean() > chances["boosted"][~marked].mean() + 0.1
    usual = max(answers[4500:].mean(), 1 - answers[4500:].mean())
    right = ((chances["boosted"] > 0.5) == (answers[4500:] == 1)).mean()
    assert right > usual + 0.02


def test_brier_reliability_and_the_calibration_check() -> None:
    chance = np.array([0.1, 0.1, 0.9, 0.9])
    answers = np.array([0.0, 0.0, 1.0, 0.0])
    assert payin.brier(chance, answers) == pytest.approx((0.01 + 0.01 + 0.01 + 0.81) / 4)
    table = payin.reliability(chance, answers, bands=2)
    assert table["days"].tolist() == [2, 2]
    assert table["stated"].tolist() == pytest.approx([0.1, 0.9])
    assert table["happened"].tolist() == pytest.approx([0.0, 0.5])
    assert not payin.calibrated(table, least=2)
    assert payin.calibrated(table, least=3)  # no band is large enough to be judged


def test_a_model_with_smaller_loss_every_month_gains_in_every_resample() -> None:
    days = pd.date_range("2023-01-01", periods=200, freq="D").to_numpy()
    keys = payin.month_keys(days)
    base = np.full(200, 0.25)
    gain, no_gain = payin.resampled_gain(keys, base * 0.8, base, draws=300)
    assert gain == pytest.approx(0.2)
    assert no_gain == 0.0
    rng = np.random.default_rng(0)
    noisy = base + rng.normal(0, 0.05, 200)
    _, share = payin.resampled_gain(keys, noisy, base, draws=300)
    assert 0.05 < share < 0.95
