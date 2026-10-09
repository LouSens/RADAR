"""The parts of the tone pipeline that need no model and no database."""

import numpy as np
import pandas as pd

from radar.pipelines import tone


def part(ids: list[int], headlines: list[str], start: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "article_id": ids,
            "headline": headlines,
            "created_at": pd.date_range(start, periods=len(ids), freq="D", tz="UTC"),
        }
    )


def test_guards_count_every_way_the_test_could_leak() -> None:
    clean = tone.Data(
        labelled=part([1, 2], ["Gold rises", "Stocks fall"], "2026-01-01"),
        test=part([3], ["Bitcoin jumps"], "2026-08-02"),
        held_back=part([4], ["Fed holds"], "2026-09-01"),
    )
    assert set(tone.guards(clean).values()) == {0}

    leaky = tone.Data(
        # the same article as the test, a near-copy of it, and a row inside the test period
        labelled=part([3, 5, 6], ["Bitcoin jumps", "bitcoin JUMPS!", "Oil up"], "2026-07-30"),
        test=part([3, 7], ["Bitcoin jumps", "Fed holds 2 meetings"], "2026-07-31"),
        held_back=part([7, 8], ["Something else", "Fed holds 3 meetings"], "2026-09-01"),
    )
    found = tone.guards(leaky)
    assert found["articles in both training and test"] == 1
    assert found["near-copies in both training and test"] == 1
    assert found["test articles labelled before"] == 1
    assert found["test near-copies of something labelled before"] == 1
    assert found["near-copies appearing twice in training"] == 1
    assert found["training headlines dated inside the test period"] == 1
    assert found["test headlines dated before the test period"] == 1


def test_two_labelling_passes_that_differ_count_half_each() -> None:
    frame = pd.DataFrame(
        {
            "first": ["positive", "neutral", "negative"],
            "second": [None, "neutral", "neutral"],
        }
    )
    # columns are positive, negative, neutral
    assert tone.shares(frame).tolist() == [[1, 0, 0], [0, 0, 1], [0, 0.5, 0.5]]


def test_sure_level_is_the_lowest_confidence_that_is_right_often_enough() -> None:
    # Ten headlines: the six most confident are all right, the four least are all wrong.
    confidence = np.array([0.99, 0.95, 0.9, 0.85, 0.8, 0.75, 0.6, 0.55, 0.5, 0.45])
    probabilities = np.column_stack([confidence, 1 - confidence, np.zeros(10)])
    truth = ["positive"] * 6 + ["negative"] * 4
    # 6 right of the top 7 is 86%, of the top 8 only 75%: the level is the seventh's.
    assert tone.sure_from(truth, probabilities) == 0.6
    # Never right: no level qualifies.
    assert tone.sure_from(["neutral"] * 10, probabilities) is None
