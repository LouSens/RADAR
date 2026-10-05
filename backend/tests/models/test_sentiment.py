"""Sentiment scoring helpers and aggregation, on inputs worked out by hand."""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import pytest

from radar.models import sentiment


def stamps(*hours: float) -> pd.DatetimeIndex:
    start = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DatetimeIndex([start + pd.Timedelta(hours=h) for h in hours])


EDGES = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")  # three daily buckets


def test_text_is_the_headline_then_a_summary_that_adds_something() -> None:
    assert sentiment.article_text("  Gold   rises ", "") == "Gold rises"
    assert sentiment.article_text("Gold rises", "Gold rises") == "Gold rises"
    assert sentiment.article_text("Gold rises", "Dollar\nweakens.") == "Gold rises. Dollar weakens."
    assert sentiment.article_text("Why now?", "Rates.") == "Why now? Rates."
    assert len(sentiment.article_text("a" * 5000)) == sentiment.MAX_CHARACTERS


def test_score_is_positive_minus_negative() -> None:
    probabilities = np.array([[0.7, 0.1, 0.2], [0.05, 0.9, 0.05], [0.2, 0.2, 0.6]])
    assert sentiment.score_of(probabilities) == pytest.approx([0.6, -0.85, 0.0])


def test_buckets_count_and_average_their_own_articles() -> None:
    result = sentiment.aggregate(stamps(1, 5, 30), np.array([0.4, 0.8, -1.0]), EDGES)
    assert list(result.index) == list(EDGES[1:])  # each row is stamped at its bucket's end
    assert result["article_count"].tolist() == [2, 1, 0]
    assert result["score_mean"].iloc[0] == pytest.approx(0.6)
    assert result["score_mean"].iloc[1] == pytest.approx(-1.0)
    assert np.isnan(result["score_mean"].iloc[2])  # no articles: no average, not zero


def test_decayed_score_halves_an_articles_weight_each_half_life() -> None:
    # One article at the very start of day 1 (+1) and one at the very start of day 2 (-1).
    result = sentiment.aggregate(stamps(0, 24), np.array([1.0, -1.0]), EDGES)
    assert result["score_decayed"].iloc[0] == pytest.approx(1.0)
    # At the end of day 2 the first is 48 hours old (weight 1/4), the second 24 (1/2).
    assert result["score_decayed"].iloc[1] == pytest.approx((0.25 - 0.5) / 0.75)
    # A day with no news keeps the same blend: both weights halve together.
    assert result["score_decayed"].iloc[2] == pytest.approx((0.25 - 0.5) / 0.75)
    quick = sentiment.aggregate(
        stamps(0, 24), np.array([1.0, -1.0]), EDGES, half_life=pd.Timedelta(hours=6)
    )
    assert quick["score_decayed"].iloc[1] < -0.85  # the older article has all but faded


def test_decayed_score_is_empty_before_the_first_article() -> None:
    result = sentiment.aggregate(stamps(30), np.array([0.5]), EDGES)
    assert np.isnan(result["score_decayed"].iloc[0])
    assert result["score_decayed"].iloc[1] == pytest.approx(0.5)


def test_aggregation_has_no_lookahead_and_ignores_input_order() -> None:
    rng = np.random.default_rng(0)
    hours = np.sort(rng.uniform(0, 72, 200))
    scores = rng.uniform(-1, 1, 200)
    full = sentiment.aggregate(stamps(*hours), scores, EDGES)
    # Changing articles published on day 3 cannot move days 1 and 2.
    changed = scores.copy()
    changed[hours >= 48] = 1.0
    again = sentiment.aggregate(stamps(*hours), changed, EDGES)
    assert full.iloc[:2].equals(again.iloc[:2])
    assert not full.iloc[2].equals(again.iloc[2])
    shuffled = rng.permutation(200)
    mixed = sentiment.aggregate(stamps(*hours[shuffled]), scores[shuffled], EDGES)
    pd.testing.assert_frame_equal(full, mixed)
    # An article exactly on an edge belongs to the bucket that starts there.
    edge = sentiment.aggregate(stamps(24), np.array([1.0]), EDGES)
    assert edge["article_count"].tolist() == [0, 1, 0]


class FakeScorer:
    version = "fake-1"

    def probabilities(self, texts: Sequence[str]) -> np.ndarray:
        return np.array([[0.8, 0.1, 0.1] if "rises" in t else [0.1, 0.8, 0.1] for t in texts])


def test_any_scorer_with_the_same_shape_can_stand_in() -> None:
    scorer: sentiment.Scorer = FakeScorer()
    scores = sentiment.score_of(scorer.probabilities(["Gold rises", "Gold falls"]))
    assert scores == pytest.approx([0.7, -0.7])
