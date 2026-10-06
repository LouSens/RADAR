"""The news-and-swings comparison on made-up data."""

import numpy as np
import pandas as pd
import pytest

from radar.models import news_volatility as model

DAYS = 900


def market(news_matters: bool, seed: int = 3) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Daily volatility with its own memory. When `news_matters`, a busy news day is
    followed by a larger swing the next day; otherwise the news is unrelated noise."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2022-01-01", periods=DAYS, freq="D", tz="UTC")
    count = rng.poisson(6, DAYS).astype(float)
    burst = rng.random(DAYS) < 0.08
    count[burst] *= 6
    tone = rng.normal(0, 0.3, DAYS).clip(-1, 1)
    log_vol = np.empty(DAYS)
    log_vol[0] = np.log(0.01)
    for t in range(1, DAYS):
        push = 0.5 * (np.log1p(count[t - 1]) - np.log1p(6)) if news_matters else 0.0
        log_vol[t] = 0.25 * np.log(0.01) + 0.75 * log_vol[t - 1] + push + rng.normal(0, 0.12)
    return (
        pd.Series(np.exp(log_vol), index=index),
        pd.Series(count, index=index),
        pd.Series(tone, index=index),
    )


def test_news_inputs_use_only_that_day_and_earlier_days() -> None:
    _, count, tone = market(news_matters=False)
    before = model.news_features(count, tone)
    later_count, later_tone = count.copy(), tone.copy()
    later_count.iloc[400:] = 500
    later_tone.iloc[400:] = -1
    after = model.news_features(later_count, later_tone)
    pd.testing.assert_frame_equal(before.iloc[:400], after.iloc[:400])

    # The surprise compares a day with the 22 days before it, not with itself.
    day = 100
    usual = np.log1p(count.iloc[day - 22 : day]).mean()
    assert before["news_surprise"].iloc[day] == pytest.approx(np.log1p(count.iloc[day]) - usual)
    assert before["news_surprise"].iloc[:22].isna().all()


def test_a_day_without_articles_is_zero_volume_and_neutral_tone() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    features = model.news_features(
        pd.Series([4.0, np.nan, 0.0], index=index), pd.Series([0.5, np.nan, np.nan], index=index)
    )
    assert features["news_count"].tolist() == pytest.approx([np.log(5), 0.0, 0.0])
    assert features["news_tone"].tolist() == [0.5, 0.0, 0.0]
    assert features["news_tone_size"].tolist() == [0.5, 0.0, 0.0]


def test_forecasts_never_look_ahead() -> None:
    rv, count, tone = market(news_matters=True)
    cut = 600
    changed_rv, changed_count = rv.copy(), count.copy()
    changed_rv.iloc[cut + 1 :] *= 4
    changed_count.iloc[cut + 1 :] = 300
    before = model.walk_forward(rv, model.news_features(count, tone), 1)
    after = model.walk_forward(changed_rv, model.news_features(changed_count, tone), 1)
    upto = rv.index[cut]
    pd.testing.assert_frame_equal(
        before.loc[:upto, list(model.MODELS)], after.loc[:upto, list(model.MODELS)]
    )
    # The first forecast comes only after the warm-up and the training window.
    assert before.index[0] == rv.index[22 + 250]
    assert before[list(model.MODELS)].notna().all().all()
    assert before["realised"].iloc[-1:].isna().all()  # tomorrow is not known yet


def test_news_that_really_leads_swings_is_found() -> None:
    rv, count, tone = market(news_matters=True)
    frame = model.walk_forward(rv, model.news_features(count, tone), 1)
    result = model.evaluate(frame, steps=1, horizon_days=1)
    assert result.n > 500
    linear = next(p for p in result.pairs if p.family == "har")
    assert linear.qlike_with < linear.qlike_without
    assert linear.improvement > 0.1
    assert linear.dm_p_value is not None
    assert linear.dm_p_value < 0.001
    assert model.judge(linear, linear.dm_p_value).verdict == "news helps"


def test_unrelated_news_is_not_credited() -> None:
    rv, count, tone = market(news_matters=False)
    frame = model.walk_forward(rv, model.news_features(count, tone), 1)
    result = model.evaluate(frame, steps=1, horizon_days=1)
    for pair in result.pairs:
        assert abs(pair.improvement) < 0.05
        assert model.judge(pair, pair.dm_p_value).verdict == "no measurable gain"


def test_the_rule_needs_a_lower_loss_and_a_corrected_p_value() -> None:
    base = model.PairResult(
        family="har",
        qlike_without=0.50,
        qlike_with=0.45,
        improvement=0.1,
        dm_statistic=-3.0,
        dm_p_value=0.004,
    )
    assert model.judge(base, 0.03).verdict == "news helps"
    assert model.judge(base, 0.03).dm_p_adjusted == 0.03
    # Significant alone, but not once every comparison is allowed for.
    assert model.judge(base, 0.08).verdict == "no measurable gain"
    assert model.judge(base, None).verdict == "no measurable gain"
    # A measurably different loss that is worse is not a gain.
    worse = base.model_copy(update={"qlike_with": 0.55, "improvement": -0.1})
    assert model.judge(worse, 0.001).verdict == "no measurable gain"


def test_too_little_history_is_refused() -> None:
    rv, count, tone = market(news_matters=False)
    with pytest.raises(ValueError, match="Not enough history"):
        model.walk_forward(rv.iloc[:200], model.news_features(count.iloc[:200], tone.iloc[:200]), 1)
