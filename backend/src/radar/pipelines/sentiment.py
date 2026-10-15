"""Score stored articles for tone, then summarise tone per asset over time.

Scoring needs the language model (the `nlp` extra). Summarising needs only the stored
scores, so it runs anywhere.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import Engine, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import (
    ModelRegistry,
    NewsArticle,
    NewsSentiment,
    NewsSymbol,
    NewsTopic,
    SentimentAggregate,
)
from radar.db.session import session_scope
from radar.features.calendars import nyse_schedule
from radar.logging import get_logger
from radar.models import dataset, sentiment, topics
from radar.universe import Asset, Universe

log = get_logger(__name__)

SCORE_BATCH = 512
WRITE_BATCH = 2_000
BUCKETS = ("1Hour", "1Day")

# Notebook 04 trains the tone model and saves it here, merged so that it loads as a plain
# Hugging Face model, with `model_card.json` beside it. The app only scores with it.
TUNED_DIR = Path("data/models/finbert-tone")
CARD_FILE = "model_card.json"


class ModelCard(BaseModel):
    """What notebook 04 writes beside the model it saves: what it is and how it scored on
    test headlines it never saw while training or choosing settings."""

    version: str
    base_model: str
    input: str  # "headline": the cleaned headline alone is scored
    max_length: int
    labelled_by: list[str]
    # First and last day (ISO dates) of the headlines trained on, and of those tested on.
    train_window: tuple[str, str]
    test_window: tuple[str, str]
    # Reports in the shape of `classification.ClassificationReport`.
    test: dict[str, Any]
    base_test: dict[str, Any] | None = None
    direction: dict[str, Any] | None = None
    by_symbol: dict[str, dict[str, Any]] = {}


def read_card(folder: Path = TUNED_DIR) -> ModelCard | None:
    """The card of the tuned model, or None when no tuned model is on this machine."""
    path = folder / CARD_FILE
    if not path.is_file():
        return None
    return ModelCard.model_validate(json.loads(path.read_text(encoding="utf-8")))


def active_version(engine: Engine | None = None, folder: Path = TUNED_DIR) -> str:
    """The tone model in use: the tuned one when it is on this machine, else the original."""
    card = read_card(folder)
    return card.version if card is not None else sentiment.MODEL_VERSION


def load_scorer(engine: Engine | None = None, folder: Path = TUNED_DIR) -> sentiment.Scorer | None:
    """The language model in use, or None where the libraries are not installed."""
    try:
        card = read_card(folder)
        if card is not None:
            return sentiment.FinbertScorer(
                str(folder),
                card.version,
                max_length=card.max_length,
                headline_only=card.input == "headline",
            )
        return sentiment.FinbertScorer()
    except ImportError:
        log.warning("sentiment_model_missing", hint="install with `uv sync --extra nlp`")
        return None


def scored_text(scorer: sentiment.Scorer, headline: str, summary: str) -> str:
    """The text a scorer reads: the cleaned headline for a headline model, else both."""
    if getattr(scorer, "headline_only", False):
        return dataset.clean_headline(headline)
    return sentiment.article_text(headline, summary)


def score_articles(engine: Engine, scorer: sentiment.Scorer, *, limit: int | None = None) -> int:
    """Score every article that has no score from this model version. Returns how many."""
    done = 0
    while limit is None or done < limit:
        with session_scope(engine) as session:
            scored = select(NewsSentiment.article_id).where(
                NewsSentiment.model_version == scorer.version
            )
            articles = session.execute(
                select(NewsArticle.id, NewsArticle.headline, NewsArticle.summary)
                .where(NewsArticle.id.not_in(scored))
                .order_by(NewsArticle.id)
                .limit(SCORE_BATCH)
            ).all()
            if not articles:
                break
            texts = [scored_text(scorer, a.headline, a.summary) for a in articles]
            probabilities = scorer.probabilities(texts)
            scores = sentiment.score_of(probabilities)
            session.execute(
                insert(NewsSentiment)
                .values(
                    [
                        {
                            "article_id": article.id,
                            "model_version": scorer.version,
                            "p_pos": float(p[0]),
                            "p_neg": float(p[1]),
                            "p_neu": float(p[2]),
                            "score": float(score),
                        }
                        for article, p, score in zip(articles, probabilities, scores, strict=True)
                    ]
                )
                .on_conflict_do_nothing()
            )
        done += len(articles)
        log.info("articles_scored", total=done)
    return done


def load_topic_scorer() -> topics.TopicScorer | None:
    """The topic model, or None where it is not installed."""
    try:
        return topics.ZeroShotTopics(topics.MODEL_ID)
    except ImportError:
        return None


def classify_articles(
    engine: Engine, scorer: topics.TopicScorer, *, limit: int | None = None
) -> int:
    """Give a topic to every article that has none from this model version."""
    done = 0
    while limit is None or done < limit:
        with session_scope(engine) as session:
            classified = select(NewsTopic.article_id).where(
                NewsTopic.model_version == scorer.version
            )
            articles = session.execute(
                select(NewsArticle.id, NewsArticle.headline, NewsArticle.summary)
                .where(NewsArticle.id.not_in(classified))
                .order_by(NewsArticle.id)
                .limit(SCORE_BATCH)
            ).all()
            if not articles:
                break
            texts = [
                sentiment.article_text(a.headline, a.summary)[: topics.MAX_CHARACTERS]
                for a in articles
            ]
            names, confidence = topics.pick(scorer.scores(texts))
            session.execute(
                insert(NewsTopic)
                .values(
                    [
                        {
                            "article_id": article.id,
                            "model_version": scorer.version,
                            "topic": name,
                            "confidence": float(share),
                        }
                        for article, name, share in zip(articles, names, confidence, strict=True)
                    ]
                )
                .on_conflict_do_nothing()
            )
        done += len(articles)
        log.info("articles_classified", total=done)
    return done


def daily_edges(asset: Asset, first: pd.Timestamp, last: pd.Timestamp) -> pd.DatetimeIndex:
    """Where each day's bucket ends: midnight UTC for crypto, the market close for stocks.

    For stocks this puts weekend and overnight news into the next session's bucket, the
    same day whose price move could reflect it.
    """
    if asset.asset_class == "crypto":
        return pd.date_range(first.floor("D"), last.floor("D"), freq="D")
    closes = pd.DatetimeIndex(nyse_schedule(first, last)["close"]).tz_convert("UTC")
    return closes[closes <= last]


def asset_scores(session: Session, asset: Asset, version: str) -> pd.DataFrame:
    """Time and score of every article about the asset, repeats left out."""
    rows = session.execute(
        select(NewsArticle.created_at, NewsSentiment.score)
        .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
        .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
        .where(
            NewsSymbol.symbol == asset.symbol,
            NewsSentiment.model_version == version,
            NewsArticle.duplicate_of.is_(None),
            NewsArticle.created_at >= news_start(asset),
        )
        .order_by(NewsArticle.created_at)
    ).all()
    frame = pd.DataFrame(rows, columns=["ts", "score"])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


def build_aggregates(asset: Asset, scores: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Hourly and daily summaries for one asset, for buckets that have ended by `now`."""
    start = news_start(asset)
    times = pd.DatetimeIndex(scores["ts"])
    values = scores["score"].to_numpy(dtype=float)
    hourly = pd.date_range(start, now.floor("h"), freq="h")
    daily = daily_edges(asset, start, now)
    frames = []
    for bucket, edges in (("1Hour", hourly), ("1Day", daily)):
        if len(edges) < 2:
            continue
        frames.append(sentiment.aggregate(times, values, edges).assign(bucket=bucket))
    if not frames:
        return pd.DataFrame(columns=["article_count", "score_mean", "score_decayed", "bucket"])
    return pd.concat(frames)


def aggregate_asset(
    engine: Engine, asset: Asset, version: str, now: pd.Timestamp | None = None
) -> int:
    """Store the summaries for one asset. Returns the number of rows changed."""
    if asset.news_start is None:
        return 0
    now = now or pd.Timestamp.now(tz="UTC")
    with session_scope(engine) as session:
        scores = asset_scores(session, asset, version)
    frame = build_aggregates(asset, scores, now)
    if frame.empty:
        return 0
    frame = frame.astype(object).where(frame.notna(), None)
    rows: list[dict[str, Any]] = [
        {
            "symbol": asset.symbol,
            "bucket": record.bucket,
            "ts": ts.to_pydatetime(),
            "model_version": version,
            "article_count": int(str(record.article_count)),
            "score_mean": record.score_mean,
            "score_decayed": record.score_decayed,
        }
        for ts, record in zip(frame.index, frame.itertuples(index=False), strict=True)
    ]
    measured = ("article_count", "score_mean", "score_decayed", "model_version")
    changed = 0
    with session_scope(engine) as session:
        for start in range(0, len(rows), WRITE_BATCH):
            statement = insert(SentimentAggregate).values(rows[start : start + WRITE_BATCH])
            excluded = statement.excluded
            upsert = statement.on_conflict_do_update(
                index_elements=[
                    SentimentAggregate.symbol,
                    SentimentAggregate.bucket,
                    SentimentAggregate.ts,
                ],
                set_={name: getattr(excluded, name) for name in measured},
                where=tuple_(
                    *(getattr(SentimentAggregate, name) for name in measured)
                ).is_distinct_from(tuple_(*(getattr(excluded, name) for name in measured))),
            ).returning(SentimentAggregate.ts)
            changed += len(session.execute(upsert).all())
    log.info("sentiment_aggregated", symbol=asset.symbol, rows=len(rows), changed=changed)
    return changed


def run(
    engine: Engine,
    universe: Universe,
    scorer: sentiment.Scorer | None = None,
    *,
    version: str | None = None,
    now: pd.Timestamp | None = None,
) -> int:
    """Score new articles when the model is available, then refresh every summary."""
    changed = 0
    version = version or active_version(engine)
    if scorer is not None:
        changed += score_articles(engine, scorer)
        version = scorer.version
    for asset in universe.primary:
        changed += aggregate_asset(engine, asset, version, now)
    return changed


def news_start(asset: Asset) -> pd.Timestamp:
    if asset.news_start is None:
        raise ValueError(f"{asset.symbol} has no news")
    return pd.Timestamp(asset.news_start, tz="UTC")


MODEL_NAME = "sentiment"


def evaluate(engine: Engine, folder: Path = TUNED_DIR) -> dict[str, Any] | None:
    """Record how the tone model in use scored on its held-out test headlines.

    The figures are the ones notebook 04 measured once, on headlines later than anything
    the model trained on, and wrote into the model's card. Returns them, or None when
    the original model is in use: it has no test on these labels, and none is shown.
    """
    card = read_card(folder)
    if card is None:
        log.info("sentiment_not_measured", reason="no tuned model on this machine")
        return None
    metrics: dict[str, Any] = {
        "labelled_by": card.labelled_by,
        "model": card.test,
        "original": card.base_test,
        "direction": card.direction,
        "by_symbol": card.by_symbol,
        "held_out": True,
        "fine_tuned": True,
        "test_window": list(card.test_window),
    }
    start, end = (pd.Timestamp(day).date() for day in card.train_window)
    with session_scope(engine) as session:
        session.execute(
            update(ModelRegistry).where(ModelRegistry.name == MODEL_NAME).values(is_current=False)
        )
        session.add(
            ModelRegistry(
                name=MODEL_NAME,
                symbol=None,
                version=card.version,
                train_start=start,
                train_end=end,
                is_current=True,
                params={"model_id": card.base_model, "input": card.input},
                metrics=metrics,
                artefact_path=str(folder),
            )
        )
    log.info(
        "sentiment_evaluated",
        version=card.version,
        n=card.test.get("n"),
        accuracy=card.test.get("accuracy"),
        macro_f1=card.test.get("macro_f1"),
    )
    return metrics


class NewsJob:
    """The worker's news job: score and classify new articles, then refresh summaries.

    The language models are loaded once, on first use. Where they are not installed the
    job still refreshes the summaries from scores already stored.
    """

    def __init__(self, engine: Engine, universe: Universe) -> None:
        self.engine = engine
        self.universe = universe
        self._loaded = False
        self._scorer: sentiment.Scorer | None = None
        self._topics: topics.TopicScorer | None = None

    def __call__(self) -> int:
        if not self._loaded:
            self._scorer = load_scorer(self.engine)
            self._topics = load_topic_scorer() if self._scorer is not None else None
            self._loaded = True
        changed = run(self.engine, self.universe, self._scorer)
        if self._topics is not None:
            changed += classify_articles(self.engine, self._topics)
        return changed
