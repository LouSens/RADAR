"""The data checks and the adoption rule around fine-tuning. Training itself needs the
language-model libraries and a graphics card, so it is exercised by the real run."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, NewsArticle
from radar.models import classification, dataset
from radar.pipelines import finetune as job
from radar.pipelines.labels import load_labels


def test_stored_training_labels_are_complete_and_separate_from_the_reference_sample() -> None:
    training = job.load_training_labels()
    assert len(training) == 1800
    assert training["article_id"].is_unique
    assert set(training["sentiment"]) == {"positive", "negative", "neutral"}
    assert training["split"].value_counts().to_dict() == {
        "train": 1261,
        "validation": 270,
        "test": 269,
    }
    assert set(training["labelled_by"]) == {"claude"}
    assert not set(training["article_id"]) & set(load_labels()["article_id"])


def labelled(headlines: list[str], first_id: int = 1) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "article_id": range(first_id, first_id + len(headlines)),
            "headline": headlines,
            "created_at": pd.date_range("2024-01-01", periods=len(headlines), freq="D", tz="UTC"),
        }
    )
    return dataset.time_split(frame)


def test_dataset_check_rejects_overlap_with_the_reference_sample() -> None:
    training = labelled([f"headline {chr(97 + i)}" for i in range(20)])
    reference = labelled(["something else", "another thing"], first_id=100)
    job.check_dataset(training, reference)

    same_article = reference.copy()
    same_article.loc[0, "article_id"] = 3
    with pytest.raises(ValueError, match="both labelled sets"):
        job.check_dataset(training, same_article)

    same_headline = reference.copy()
    same_headline.loc[0, "headline"] = "HEADLINE a!"
    with pytest.raises(ValueError, match="repeats one in the reference"):
        job.check_dataset(training, same_headline)


def test_text_is_joined_from_stored_articles_only(session: Session) -> None:
    when = datetime(2024, 1, 1, tzinfo=UTC)
    session.add(
        NewsArticle(id=1, created_at=when, updated_at=when, headline="Gold rises", summary="More.")
    )
    session.commit()
    labels = pd.DataFrame({"article_id": [1, 2], "sentiment": ["positive", "neutral"]})
    frame = job.with_text(session, labels)
    assert frame["article_id"].tolist() == [1]  # article 2 is not stored
    assert frame["text"].tolist() == ["Gold rises. More."]
    assert frame["created_at"].iloc[0] == pd.Timestamp(when)


def report(accuracy: float) -> classification.ClassificationReport:
    return classification.ClassificationReport(
        n=269, accuracy=accuracy, macro_f1=accuracy, classes=[]
    )


def compare(p_value: float) -> classification.Comparison:
    return classification.Comparison(
        n=269, only_first_right=5, only_second_right=30, p_value=p_value
    )


def test_the_fine_tuned_model_is_adopted_only_when_measurably_better() -> None:
    assert job.decide(report(0.65), report(0.78), compare(0.001)) == (True, "measurably_better")
    assert job.decide(report(0.65), report(0.67), compare(0.40)) == (
        False,
        "difference_not_measurable",
    )
    assert job.decide(report(0.65), report(0.60), compare(0.001)) == (False, "not_more_accurate")
    assert job.decide(report(0.65), report(0.65), compare(1.0)) == (False, "not_more_accurate")


def register(session: Session, *, adopted: bool, path: Path) -> None:
    day = datetime(2025, 1, 1, tzinfo=UTC).date()
    session.add(
        ModelRegistry(
            name=job.MODEL_NAME,
            version="finbert-radar-1",
            train_start=day,
            train_end=day + timedelta(days=1),
            is_current=True,
            params={},
            metrics={"adopted": adopted},
            artefact_path=str(path),
        )
    )
    session.commit()


def test_adopted_model_needs_the_decision_and_the_files(session: Session, tmp_path: Path) -> None:
    assert job.adopted_model(session) is None
    register(session, adopted=False, path=tmp_path)
    assert job.adopted_model(session) is None  # trained, but not adopted

    session.query(ModelRegistry).delete()
    register(session, adopted=True, path=tmp_path / "missing")
    assert job.adopted_model(session) is None  # adopted, but the files are not on this machine

    session.query(ModelRegistry).delete()
    register(session, adopted=True, path=tmp_path)
    found = job.adopted_model(session)
    assert found is not None
    assert found.version == "finbert-radar-1"
