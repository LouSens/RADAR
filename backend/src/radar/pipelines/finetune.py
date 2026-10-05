"""Fine-tune the sentiment model, test it once on held-out headlines, and decide.

The steps, in order, so that nothing leaks from the test part into training:

1. Load the labelled headlines with their text from the database.
2. Check the parts: no article or near-identical headline in two parts, none shared with
   the separate 200-headline sample, and train older than validation older than test.
3. Fine-tune on the training part, choosing the epoch by the validation part.
4. Score the original model, the fine-tuned model, and the word list on the test part.
5. Adopt the fine-tuned model only if it is measurably better on the test part.
"""

import csv
import io
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, NewsArticle
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import classification, dataset, finetune, sentiment
from radar.models.lexicon import Lexicon
from radar.pipelines.labels import load_labels

log = get_logger(__name__)

MODEL_NAME = "sentiment_finetune"
TRAINING_LABELS_FILE = "sentiment_training_labels.csv"
MODEL_DIR = Path("data/models") / finetune.MODEL_VERSION
SIGNIFICANCE = 0.05


def load_training_labels() -> pd.DataFrame:
    """`article_id`, `symbol`, `sentiment`, `split`, `labelled_by` for the training set."""
    text = (resources.files("radar") / TRAINING_LABELS_FILE).read_text(encoding="utf-8")
    frame = pd.DataFrame(list(csv.DictReader(io.StringIO(text))))
    frame["article_id"] = frame["article_id"].astype("int64")
    return frame


def with_text(session: Session, labels: pd.DataFrame) -> pd.DataFrame:
    """Join labels to the stored articles. Labels whose article is not stored are dropped."""
    rows = session.execute(
        select(
            NewsArticle.id, NewsArticle.headline, NewsArticle.summary, NewsArticle.created_at
        ).where(NewsArticle.id.in_(labels["article_id"].tolist()))
    ).all()
    articles = pd.DataFrame(rows, columns=["article_id", "headline", "summary", "created_at"])
    articles["created_at"] = pd.to_datetime(articles["created_at"], utc=True)
    frame = labels.merge(articles, on="article_id")
    frame["text"] = [
        sentiment.article_text(h, s or "")
        for h, s in zip(frame["headline"], frame["summary"], strict=True)
    ]
    return frame


def check_dataset(training: pd.DataFrame, reference: pd.DataFrame) -> None:
    """Raise if anything could leak between the parts or from the reference sample."""
    dataset.check_no_leakage(training)
    shared = set(training["article_id"]) & set(reference["article_id"])
    if shared:
        raise ValueError(f"{len(shared)} articles are in both labelled sets")
    keys = set(training["headline"].map(dataset.headline_key))
    if keys & set(reference["headline"].map(dataset.headline_key)):
        raise ValueError("A training headline repeats one in the reference sample")


def _predict(scorer: sentiment.Scorer, texts: list[str]) -> list[str]:
    return [sentiment.LABELS[i] for i in scorer.probabilities(texts).argmax(axis=1)]


def decide(
    base: classification.ClassificationReport,
    tuned: classification.ClassificationReport,
    comparison: classification.Comparison,
) -> tuple[bool, str]:
    """Adopt the fine-tuned model only if it is more accurate on the test part and the
    difference is unlikely to be chance (McNemar p below 0.05)."""
    if tuned.accuracy <= base.accuracy:
        return False, "not_more_accurate"
    if comparison.p_value >= SIGNIFICANCE:
        return False, "difference_not_measurable"
    return True, "measurably_better"


def run(
    engine: Engine,
    *,
    model_dir: Path = MODEL_DIR,
    lexicon: Lexicon | None = None,
    epochs: int = 4,
    seed: int = 13,
) -> dict[str, Any]:
    """Fine-tune, test, decide, and record. Returns the stored metrics."""
    with session_scope(engine) as session:
        training = with_text(session, load_training_labels())
        reference = with_text(session, load_labels())
    check_dataset(training, reference)
    parts = {name: training[training["split"] == name] for name in dataset.SPLITS}
    train, validation, test = (parts[name] for name in dataset.SPLITS)

    result = finetune.fine_tune(
        train["text"].tolist(),
        train["sentiment"].tolist(),
        validation["text"].tolist(),
        validation["sentiment"].tolist(),
        model_dir,
        epochs=epochs,
        seed=seed,
    )

    # The test part is used here, once, after every choice has been made.
    base_scorer = sentiment.FinbertScorer()
    tuned_scorer = sentiment.FinbertScorer(str(model_dir), finetune.MODEL_VERSION)
    truth = test["sentiment"].tolist()
    base_labels = _predict(base_scorer, test["text"].tolist())
    tuned_labels = _predict(tuned_scorer, test["text"].tolist())
    base = classification.report(truth, base_labels, sentiment.LABELS)
    tuned = classification.report(truth, tuned_labels, sentiment.LABELS)
    comparison = classification.mcnemar(truth, base_labels, tuned_labels)
    adopted, reason = decide(base, tuned, comparison)

    reference_truth = reference["sentiment"].tolist()
    metrics: dict[str, Any] = {
        "training": result.model_dump(),
        "splits": {
            name: {
                "n": len(part),
                "first": str(part["created_at"].min().date()),
                "last": str(part["created_at"].max().date()),
            }
            for name, part in parts.items()
        },
        "labelled_by": sorted(set(training["labelled_by"])),
        "test": {
            "base": base.model_dump(),
            "fine_tuned": tuned.model_dump(),
            "comparison": comparison.model_dump(),
        },
        # The older 200-headline sample. Its dates overlap the training period, so it is
        # a second opinion, not the deciding test.
        "reference": {
            "base": classification.report(
                reference_truth, _predict(base_scorer, reference["text"].tolist()), sentiment.LABELS
            ).model_dump(),
            "fine_tuned": classification.report(
                reference_truth,
                _predict(tuned_scorer, reference["text"].tolist()),
                sentiment.LABELS,
            ).model_dump(),
        },
        "adopted": adopted,
        "reason": reason,
    }
    if lexicon is not None:
        metrics["test"]["baseline"] = classification.report(
            truth, lexicon.labels(test["text"].tolist()), sentiment.LABELS
        ).model_dump()

    with session_scope(engine) as session:
        session.execute(
            update(ModelRegistry).where(ModelRegistry.name == MODEL_NAME).values(is_current=False)
        )
        session.add(
            ModelRegistry(
                name=MODEL_NAME,
                symbol=None,
                version=finetune.MODEL_VERSION,
                train_start=train["created_at"].min().date(),
                train_end=train["created_at"].max().date(),
                is_current=True,
                params={"base_model": result.base_model, "seed": seed, "epochs": epochs},
                metrics=metrics,
                artefact_path=str(model_dir),
            )
        )
    log.info(
        "fine_tune_done",
        base_accuracy=round(base.accuracy, 3),
        tuned_accuracy=round(tuned.accuracy, 3),
        p_value=round(comparison.p_value, 4),
        adopted=adopted,
    )
    return metrics


def adopted_model(session: Session) -> ModelRegistry | None:
    """The fine-tuned model in use, if one has been adopted and its files are present."""
    row = session.scalars(
        select(ModelRegistry)
        .where(ModelRegistry.name == MODEL_NAME, ModelRegistry.is_current)
        .order_by(ModelRegistry.trained_at.desc())
        .limit(1)
    ).first()
    if row is None or not row.metrics.get("adopted") or row.artefact_path is None:
        return None
    return row if Path(row.artefact_path).is_dir() else None
