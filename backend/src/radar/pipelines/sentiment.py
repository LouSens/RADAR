"""Score stored articles for tone, then summarise tone per asset over time.

Scoring needs the language model (the `nlp` extra). Summarising needs only the stored
scores, so it runs anywhere.
"""

from typing import Any

import pandas as pd
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
from radar.models import classification, evidence, sentiment, topics
from radar.models.lexicon import Lexicon
from radar.pipelines.finetune import adopted_model, adopted_record
from radar.pipelines.labels import load_labels
from radar.universe import Asset, Universe

log = get_logger(__name__)

SCORE_BATCH = 512
WRITE_BATCH = 2_000
BUCKETS = ("1Hour", "1Day")


def active_version(engine: Engine) -> str:
    """The sentiment model in use: the fine-tuned one if it was adopted, else the original."""
    with session_scope(engine) as session:
        adopted = adopted_record(session)
        return adopted.version if adopted is not None else sentiment.MODEL_VERSION


def load_scorer(engine: Engine | None = None) -> sentiment.Scorer | None:
    """The language model in use, or None where the libraries are not installed.

    With an engine, an adopted fine-tuned model is loaded in place of the original.
    """
    try:
        if engine is not None:
            with session_scope(engine) as session:
                adopted = adopted_model(session)
                if adopted is not None and adopted.artefact_path is not None:
                    return sentiment.FinbertScorer(adopted.artefact_path, adopted.version)
        return sentiment.FinbertScorer()
    except ImportError:
        log.warning("sentiment_model_missing", hint="install with `uv sync --extra nlp`")
        return None


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
            texts = [sentiment.article_text(a.headline, a.summary) for a in articles]
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


def evaluate(
    engine: Engine,
    version: str | None = None,
    lexicon: Lexicon | None = None,
    labels: pd.DataFrame | None = None,
) -> dict[str, Any] | None:
    """Score the model and the word-list rival against the labelled sample, and record it.

    Returns the stored metrics, or None when no labelled article has a score yet.
    """
    labels = load_labels() if labels is None else labels
    version = version or active_version(engine)
    with session_scope(engine) as session:
        rows = session.execute(
            select(
                NewsArticle.id,
                NewsArticle.headline,
                NewsArticle.summary,
                NewsSentiment.p_pos,
                NewsSentiment.p_neg,
                NewsSentiment.p_neu,
            )
            .join(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
            .where(
                NewsArticle.id.in_(labels["article_id"].tolist()),
                NewsSentiment.model_version == version,
            )
        ).all()
    if not rows:
        return None
    scored = pd.DataFrame(
        rows, columns=["article_id", "headline", "summary", "p_pos", "p_neg", "p_neu"]
    ).merge(labels, on="article_id")
    truth = scored["sentiment"].tolist()
    predicted = [
        sentiment.LABELS[i]
        for i in scored[["p_pos", "p_neg", "p_neu"]].to_numpy(dtype=float).argmax(axis=1)
    ]
    metrics: dict[str, Any] = {
        "n_labelled": len(labels),
        "labelled_by": sorted(set(labels["labelled_by"])),
        "model": classification.report(truth, predicted, sentiment.LABELS).model_dump(),
        "direction": evidence.direction(truth, predicted).model_dump(),
        "by_symbol": {
            symbol: classification.report(
                [truth[i] for i in group], [predicted[i] for i in group], sentiment.LABELS
            ).model_dump(include={"n", "accuracy", "macro_f1"})
            for symbol, group in scored.groupby("symbol").indices.items()
        },
    }
    topic_version = topics.version_of(topics.MODEL_ID)
    with session_scope(engine) as session:
        assigned = dict(
            session.execute(
                select(NewsTopic.article_id, NewsTopic.topic).where(
                    NewsTopic.article_id.in_(labels["article_id"].tolist()),
                    NewsTopic.model_version == topic_version,
                )
            ).all()
        )
    if assigned:
        known = labels[labels["article_id"].isin(list(assigned))]
        metrics["topics"] = classification.report(
            known["topic"].tolist(),
            [assigned[i] for i in known["article_id"]],
            list(topics.TOPICS),
        ).model_dump()
        metrics["topic_model"] = topics.MODEL_ID
    if lexicon is not None:
        texts = [
            sentiment.article_text(h, s)
            for h, s in zip(scored["headline"], scored["summary"], strict=True)
        ]
        metrics["baseline"] = classification.report(
            truth, lexicon.labels(texts), sentiment.LABELS
        ).model_dump()
    today = pd.Timestamp.now(tz="UTC").date()
    with session_scope(engine) as session:
        session.execute(
            update(ModelRegistry).where(ModelRegistry.name == MODEL_NAME).values(is_current=False)
        )
        session.add(
            ModelRegistry(
                name=MODEL_NAME,
                symbol=None,
                version=version,
                train_start=today,
                train_end=today,
                is_current=True,
                params={"model_id": sentiment.MODEL_ID},
                metrics=metrics,
            )
        )
    log.info(
        "sentiment_evaluated",
        n=metrics["model"]["n"],
        accuracy=round(metrics["model"]["accuracy"], 3),
        macro_f1=round(metrics["model"]["macro_f1"], 3),
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
