"""Intervals, the many-tests correction, and direction scores, on hand-checked cases."""

import pytest

from radar.models import evidence


def test_wilson_interval_matches_known_values() -> None:
    low, high = evidence.wilson(131, 200)  # 65.5% of 200
    assert low == pytest.approx(0.587, abs=0.002)
    assert high == pytest.approx(0.717, abs=0.002)
    # More data, narrower range around the same share.
    wide = evidence.wilson(13, 20)
    narrow = evidence.wilson(1300, 2000)
    assert wide[1] - wide[0] > 4 * (narrow[1] - narrow[0])
    # Never outside 0 to 1, even at the edges, and never a zero-width range from a sample.
    assert evidence.wilson(0, 30)[0] == 0.0
    assert 0.0 < evidence.wilson(0, 30)[1] < 0.15
    assert evidence.wilson(30, 30)[1] == pytest.approx(1.0)
    assert evidence.wilson(0, 0) == (0.0, 1.0)
    assert evidence.share_interval(0.655, 200) == pytest.approx(evidence.wilson(131, 200))


def test_benjamini_hochberg_matches_a_hand_calculation() -> None:
    # Sorted: 0.01, 0.02, 0.03, 0.5 with m = 4 -> 0.04, 0.04, 0.04, 0.5.
    adjusted = evidence.benjamini_hochberg([0.5, 0.01, 0.03, 0.02])
    assert adjusted == pytest.approx([0.5, 0.04, 0.04, 0.04])
    # One small p-value among many tests no longer counts as a finding.
    many = evidence.benjamini_hochberg([0.03] + [0.6] * 19)
    assert many[0] == pytest.approx(0.6)
    assert all(a is not None and a >= p for a, p in zip(many, [0.03] + [0.6] * 19, strict=True))


def test_benjamini_hochberg_leaves_missing_values_out() -> None:
    adjusted = evidence.benjamini_hochberg([0.01, None, 0.04, float("nan")])
    assert adjusted[1] is None
    assert adjusted[3] is None
    assert adjusted[0] == pytest.approx(0.02)  # two real tests, not four
    assert adjusted[2] == pytest.approx(0.04)
    assert evidence.benjamini_hochberg([]) == []


def test_direction_counts_outright_reversals() -> None:
    truth = ["positive", "positive", "negative", "negative", "neutral", "neutral"]
    predicted = ["positive", "negative", "negative", "neutral", "positive", "neutral"]
    result = evidence.direction(truth, predicted)
    assert result.n == 6
    assert result.opposite == 1  # one positive called negative
    assert result.opposite_rate == pytest.approx(1 / 6)
    assert result.both_polar == 3
    assert result.same_direction == pytest.approx(2 / 3)
    nothing = evidence.direction(["neutral"], ["neutral"])
    assert nothing.same_direction is None
    assert nothing.opposite_rate == 0.0
