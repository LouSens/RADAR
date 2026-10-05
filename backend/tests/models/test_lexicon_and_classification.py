"""The word-list baseline and the classification scores, on hand-checked cases."""

from pathlib import Path

import pytest

from radar.models import classification
from radar.models.lexicon import Lexicon

DICTIONARY = (
    "Word,Seq_num,Negative,Positive,Uncertainty\n"
    "GAIN,1,0,2009,0\n"
    "STRONG,2,0,2009,0\n"
    "LOSS,3,2009,0,0\n"
    "FRAUD,4,2009,0,0\n"
    "MAYBE,5,0,0,2009\n"
    "TABLE,6,0,0,0\n"
)


@pytest.fixture
def lexicon(tmp_path: Path) -> Lexicon:
    path = tmp_path / "words.csv"
    path.write_text(DICTIONARY, encoding="utf-8")
    return Lexicon.load(path)


def test_dictionary_keeps_only_positive_and_negative_words(lexicon: Lexicon) -> None:
    assert lexicon.positive == {"GAIN", "STRONG"}
    assert lexicon.negative == {"LOSS", "FRAUD"}


def test_label_follows_the_word_counts(lexicon: Lexicon) -> None:
    assert lexicon.counts("Strong gain despite one loss.") == (2, 1)
    assert lexicon.label("Strong gain despite one loss.") == "positive"
    assert lexicon.label("FRAUD: a loss") == "negative"
    assert lexicon.label("A gain and a loss") == "neutral"  # a tie
    assert lexicon.label("The table, maybe") == "neutral"  # no tone words
    assert lexicon.label("gains") == "neutral"  # only exact dictionary words count
    assert lexicon.labels(["gain", "loss"]) == ["positive", "negative"]


def test_report_matches_a_hand_calculation() -> None:
    truth = ["pos", "pos", "pos", "neg", "neg", "neu"]
    predicted = ["pos", "pos", "neg", "neg", "neu", "neu"]
    result = classification.report(truth, predicted, ["pos", "neg", "neu"])
    assert result.n == 6
    assert result.accuracy == pytest.approx(4 / 6)
    by_label = {c.label: c for c in result.classes}
    assert by_label["pos"].precision == 1.0
    assert by_label["pos"].recall == pytest.approx(2 / 3)
    assert by_label["pos"].f1 == pytest.approx(0.8)
    assert by_label["neg"].f1 == pytest.approx(0.5)
    assert by_label["neu"].f1 == pytest.approx(2 / 3)
    assert result.macro_f1 == pytest.approx((0.8 + 0.5 + 2 / 3) / 3)


def test_report_handles_labels_that_never_occur() -> None:
    result = classification.report(["a", "a"], ["a", "b"], ["a", "b", "c"])
    assert result.accuracy == 0.5
    # "b" and "c" have no true items, so only "a" enters the average.
    assert result.macro_f1 == pytest.approx(2 / 3)
    assert {c.label: c.support for c in result.classes} == {"a": 2, "b": 0, "c": 0}
    with pytest.raises(ValueError, match="same length"):
        classification.report(["a"], [], ["a"])


def test_mcnemar_uses_only_the_items_where_the_two_differ() -> None:
    truth = ["a"] * 40
    first = ["a"] * 20 + ["b"] * 20  # right on the first 20
    second = ["a"] * 38 + ["b"] * 2  # right on the first 38
    result = classification.mcnemar(truth, first, second)
    assert (result.only_first_right, result.only_second_right) == (0, 18)
    assert result.p_value < 0.001
    same = classification.mcnemar(truth, first, first)
    assert same.p_value == 1.0
    # Five wins against four is well within chance.
    close = classification.mcnemar(["a"] * 9, ["a"] * 5 + ["b"] * 4, ["b"] * 5 + ["a"] * 4)
    assert (close.only_first_right, close.only_second_right) == (5, 4)
    assert close.p_value == 1.0
