"""The tables notebook 04 shows, worked out from small made-up results."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from radar.models import classification
from radar.pipelines import tone, tone_report


def labelled(n: int = 12) -> pd.DataFrame:
    labels = ["positive", "negative", "neutral"]
    return pd.DataFrame(
        {
            "article_id": range(n),
            "headline": [f"headline {chr(97 + i)}" for i in range(n)],
            "summary": "",
            "created_at": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
            "market": ["Bitcoin", "Gold"] * (n // 2),
            "sentiment": [labels[i % 3] for i in range(n)],
            "first": [labels[i % 3] for i in range(n)],
            "second": [None] * n,
        }
    )


def run(block: int, seed: int, loss: float, accuracy: float) -> dict[str, float]:
    return {"block": block, "seed": seed, "loss": loss, "accuracy": accuracy, "kept": 2,
            "training_loss": 0.5}  # fmt: skip


def test_kappa_is_one_for_full_agreement_and_zero_for_chance() -> None:
    labels = ["positive", "negative", "neutral"]
    same = ["positive", "negative", "neutral", "neutral"]
    assert classification.cohen_kappa(same, same, labels) == pytest.approx(1.0)
    # Each pass says each label half the time and they agree half the time: pure chance.
    first = ["positive", "positive", "negative", "negative"]
    second = ["positive", "negative", "positive", "negative"]
    assert classification.cohen_kappa(first, second, labels) == pytest.approx(0.0)
    with pytest.raises(ValueError, match="same, non-zero length"):
        classification.cohen_kappa(first, second[:2], labels)


def test_agreement_counts_only_headlines_labelled_twice() -> None:
    frame = labelled()
    frame.loc[[0, 1, 2, 3], "second"] = ["positive", "negative", "neutral", "neutral"]
    data = tone.Data(labelled=frame, test=frame.iloc[0:0], held_back=frame.iloc[0:0])
    table = tone_report.agreement(data)
    # Four were labelled twice; the fourth (first "positive", second "neutral") differs.
    assert table.loc["all", "headlines"] == 4
    assert table.loc["all", "agreement"] == pytest.approx(0.75)
    grid = tone_report.agreement_grid(data)
    assert grid.loc["positive", "neutral"] == 1
    assert int(grid.to_numpy().sum()) == 4


def test_reachable_range_runs_from_agreement_to_its_square_root() -> None:
    low, high = tone_report.reachable(0.81)
    assert (low, high) == pytest.approx((0.81, 0.9))


def test_options_show_the_mean_and_the_spread_of_the_runs() -> None:
    found = {
        "a": {"runs": [run(1, 13, 0.70, 0.70), run(1, 17, 0.74, 0.68)]},
        "b": {"runs": [run(1, 13, 0.71, 0.69), run(1, 17, 0.75, 0.69)]},
    }
    table = tone_report.options(found)
    assert list(table.index) == ["a", "b"]
    assert table.loc["a", "validation loss"] == pytest.approx(0.72)
    assert table.loc["a", "spread (sd of runs)"] == pytest.approx(np.std([0.70, 0.74], ddof=1))
    # Two seeds of one candidate differ by 0.04; the candidates differ by 0.01.
    assert tone_report.seed_spread(found)["loss"] == pytest.approx(0.04)
    verdict = tone_report.difference(found)
    assert verdict["winner"] == "a"
    assert verdict["gap"] == pytest.approx(0.01)
    assert verdict["measurable"] is False


def test_a_gap_larger_than_seed_spread_is_measurable() -> None:
    found = {
        "a": {"runs": [run(1, 13, 0.60, 0.75), run(1, 17, 0.61, 0.75)]},
        "b": {"runs": [run(1, 13, 0.80, 0.65), run(1, 17, 0.81, 0.65)]},
    }
    assert tone_report.difference(found)["measurable"] is True


def test_majority_baseline_uses_the_training_part_only(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = labelled(12)
    frame["sentiment"] = ["neutral"] * 8 + ["positive"] * 4
    data = tone.Data(labelled=frame, test=frame.iloc[0:0], held_back=frame.iloc[0:0])
    monkeypatch.setattr(tone, "BLOCK", 2)
    monkeypatch.setattr(tone, "BLOCKS", 2)
    table = tone_report.majority(data)
    # Block 1 trains on eight neutrals and validates on two positives: never right.
    assert table.loc["block 1", "answer"] == "neutral"
    assert table.loc["block 1", "accuracy"] == 0.0
    assert table.loc["block 2", "accuracy"] == 0.0


def test_reliability_and_its_gap() -> None:
    # Says 90% every time and is right half the time: 40 points too sure.
    probabilities = np.tile([[0.9, 0.05, 0.05]], (10, 1))
    truth = ["positive"] * 5 + ["negative"] * 5
    table = tone_report.reliability(truth, probabilities)
    assert table["headlines"].sum() == 10
    assert tone_report.calibration_gap(truth, probabilities) == pytest.approx(0.4)


def test_temperature_is_undone_to_recover_the_probabilities_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = labelled(12)
    data = tone.Data(labelled=frame, test=frame.iloc[0:0], held_back=frame.iloc[0:0])
    monkeypatch.setattr(tone, "OUT", tmp_path)
    monkeypatch.setattr(tone, "BLOCK", 3)
    monkeypatch.setattr(tone, "BLOCKS", 2)
    assert tone_report.validation_probabilities(data, {"temperature": 1.5}) is None
    before = np.array([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1], [0.3, 0.3, 0.4]])
    np.save(tmp_path / "validation_final.npy", classification.with_temperature(before, 1.5))
    found = tone_report.validation_probabilities(data, {"temperature": 1.5})
    assert found is not None
    truth, recovered, after = found
    assert truth == frame["sentiment"].tolist()[-3:]
    assert recovered == pytest.approx(before)
    assert (after.max(axis=1) < before.max(axis=1)).all()

    errors = tone_report.validation_errors(data, {"temperature": 1.5})
    assert errors is not None
    assert int(errors["grid"].to_numpy().sum()) == 3
    assert errors["by market"]["headlines"].sum() == 3


def test_missing_results_are_named_not_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tone, "OUT", tmp_path)
    assert tone_report.stored("final") is None
    assert tone_report.not_available("final").startswith("not available: ")
    assert tone_report.not_available("final").endswith("final.json")


def test_test_scores_take_the_baseline_from_the_stored_table() -> None:
    score = {"accuracy": 0.7, "from": 0.66, "to": 0.74, "loss": 0.7, "macro_f1": 0.69}
    test = {
        # rows are the labels: 50 positive, 30 negative, 20 neutral
        "table": [[40, 5, 5], [5, 20, 5], [5, 5, 10]],
        "scores": {"in use": score, "new": score},
    }
    table = tone_report.test_scores(test)
    assert table.loc["baseline: always the commonest label", "accuracy"] == pytest.approx(0.5)
    assert table.loc["the new model", "95% from"] == 0.66
