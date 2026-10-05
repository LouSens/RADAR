"""Score stored articles for tone, then summarise tone per asset over time.

Scoring needs the language model (the `nlp` extra). Summarising needs only the stored
scores, so it runs anywhere.
"""

from typing import Any

import pandas as pd
from sqlalchemy import Engine, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import NewsArticle, NewsSentiment, NewsSymbol, SentimentAggregate
from radar.db.session import session_scope
from radar.features.calendars import nyse_schedule
from radar.logging import get_logger
from radar.models import sentiment
from radar.universe import Asset, Universe

log = get_logger(__name__)

SCORE_BATCH = 512
WRITE_BATCH = 2_000
BUCKETS = ("1Hour", "1Day")


def load_scorer() -> sentiment.Scorer | None:
    """The language model, or None where it is not installed."""
    try:
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
    version: str = sentiment.MODEL_VERSION,
    now: pd.Timestamp | None = None,
) -> int:
    """Score new articles when the model is available, then refresh every summary."""
    changed = 0
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
