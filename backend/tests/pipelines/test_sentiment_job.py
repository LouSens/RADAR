"""Sentiment scoring and aggregation against the real test database."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import (
    ModelRegistry,
    NewsArticle,
    NewsSentiment,
    NewsSymbol,
    NewsTopic,
    SentimentAggregate,
)
from radar.models import topics
from radar.models.lexicon import Lexicon
from radar.pipelines import sentiment as job
from radar.universe import Universe

UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2024-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2024-01-01",
            },
            {
                "symbol": "GLD",
                "name": "Gold",
                "asset_class": "stock",
                "is_primary": True,
                "bars_symbol": "GLD",
                "history_start": "2024-01-01",
                "news_symbols": ["GLD"],
                "news_start": "2024-01-01",
            },
        ],
    }
)
BTC = UNIVERSE.get("BTC/USD")
GLD = UNIVERSE.get("GLD")
NOW = pd.Timestamp("2024-01-09T12:00:00Z")


class WordScorer:
    """Stands in for the language model: 'rises' is good news, 'falls' is bad."""

    version = "words-1"

    def __init__(self) -> None:
        self.seen = 0

    def probabilities(self, texts: Sequence[str]) -> np.ndarray:
        self.seen += len(texts)
        rows = {"rises": [0.9, 0.05, 0.05], "falls": [0.05, 0.9, 0.05]}
        return np.array(
            [next((v for k, v in rows.items() if k in t), [0.1, 0.1, 0.8]) for t in texts]
        )


def article(
    session: Session, id_: int, when: datetime, headline: str, symbol: str, dup: int | None = None
) -> None:
    session.add(
        NewsArticle(id=id_, created_at=when, updated_at=when, headline=headline, duplicate_of=dup)
    )
    session.flush()
    session.add(NewsSymbol(article_id=id_, symbol=symbol))


def seed(session: Session) -> None:
    sync_assets(session, UNIVERSE)
    monday = datetime(2024, 1, 1, tzinfo=UTC)
    article(session, 1, monday + timedelta(hours=3), "Bitcoin rises", "BTC/USD")
    article(session, 2, monday + timedelta(hours=5), "Bitcoin falls", "BTC/USD")
    article(session, 3, monday + timedelta(days=1, hours=1), "Bitcoin rises again", "BTC/USD")
    article(session, 4, monday + timedelta(days=1, hours=2), "Bitcoin rises again", "BTC/USD", 3)
    # Saturday 6 January: gold news while the market is shut.
    article(session, 5, monday + timedelta(days=5, hours=15), "Gold falls", "GLD")
    session.commit()


def test_every_article_is_scored_once(engine: Engine, session: Session) -> None:
    seed(session)
    scorer = WordScorer()
    assert job.score_articles(engine, scorer) == 5
    assert job.score_articles(engine, scorer) == 0  # nothing left to score
    assert scorer.seen == 5
    stored = {
        r.article_id: r
        for r in session.scalars(select(NewsSentiment).order_by(NewsSentiment.article_id))
    }
    assert stored[1].score == 0.9 - 0.05
    assert stored[2].score == 0.05 - 0.9
    assert stored[1].model_version == "words-1"
    assert abs(stored[1].p_pos + stored[1].p_neg + stored[1].p_neu - 1.0) < 1e-9


def test_crypto_days_end_at_midnight_and_repeats_are_left_out(
    engine: Engine, session: Session
) -> None:
    seed(session)
    changed = job.run(engine, UNIVERSE, WordScorer(), now=NOW)
    assert changed > 5
    daily = {
        r.ts: r
        for r in session.scalars(
            select(SentimentAggregate).where(
                SentimentAggregate.symbol == "BTC/USD", SentimentAggregate.bucket == "1Day"
            )
        )
    }
    first = daily[datetime(2024, 1, 2, tzinfo=UTC)]  # the bucket for 1 January
    assert first.article_count == 2
    assert first.score_mean == 0.0  # one good, one bad
    second = daily[datetime(2024, 1, 3, tzinfo=UTC)]
    assert second.article_count == 1  # the repeat is not counted
    assert second.score_mean == 0.85
    quiet = daily[datetime(2024, 1, 5, tzinfo=UTC)]
    assert quiet.article_count == 0
    assert quiet.score_mean is None
    assert quiet.score_decayed is not None  # earlier news still echoes, fading
    assert max(daily) == datetime(2024, 1, 9, tzinfo=UTC)  # only days that have ended

    hours = session.scalar(
        select(func.count())
        .select_from(SentimentAggregate)
        .where(SentimentAggregate.symbol == "BTC/USD", SentimentAggregate.bucket == "1Hour")
    )
    assert hours == 8 * 24 + 12

    assert job.run(engine, UNIVERSE, WordScorer(), now=NOW) == 0  # a rerun changes nothing


def test_stock_days_end_at_the_close_so_weekend_news_lands_on_monday(
    engine: Engine, session: Session
) -> None:
    seed(session)
    job.run(engine, UNIVERSE, WordScorer(), now=NOW)
    daily = {
        r.ts: r
        for r in session.scalars(
            select(SentimentAggregate).where(
                SentimentAggregate.symbol == "GLD", SentimentAggregate.bucket == "1Day"
            )
        )
    }
    friday_close = datetime(2024, 1, 5, 21, tzinfo=UTC)  # 16:00 in New York
    monday_close = datetime(2024, 1, 8, 21, tzinfo=UTC)
    assert daily[friday_close].article_count == 0
    assert daily[monday_close].article_count == 1  # Saturday's article
    assert daily[monday_close].score_mean == 0.05 - 0.9
    assert datetime(2024, 1, 6, 21, tzinfo=UTC) not in daily  # no bucket ends on a Saturday


def test_summaries_refresh_without_the_model(engine: Engine, session: Session) -> None:
    seed(session)
    job.score_articles(engine, WordScorer())
    # No scorer here, as on a machine without the language model.
    assert job.run(engine, UNIVERSE, None, version="words-1", now=NOW) > 0
    assert job.run(engine, UNIVERSE, None, version="other", now=NOW) > 0  # nothing scored: empties
    empty = session.scalars(
        select(SentimentAggregate.article_count).where(SentimentAggregate.symbol == "BTC/USD")
    ).all()
    assert set(empty) == {0}


class SubjectScorer:
    """Stands in for the topic model: Bitcoin headlines are price talk, the rest macro."""

    version = topics.version_of(topics.MODEL_ID)

    def scores(self, texts: Sequence[str]) -> np.ndarray:
        names = list(topics.TOPICS)
        rows = np.full((len(texts), len(names)), 0.05)
        for i, text in enumerate(texts):
            rows[i, names.index("price" if "Bitcoin" in text else "macro")] = 0.7
        return rows


def test_every_article_gets_one_topic(engine: Engine, session: Session) -> None:
    seed(session)
    assert job.classify_articles(engine, SubjectScorer()) == 5
    assert job.classify_articles(engine, SubjectScorer()) == 0
    stored = {t.article_id: t for t in session.scalars(select(NewsTopic))}
    assert stored[1].topic == "price"
    assert stored[5].topic == "macro"
    assert stored[1].confidence == 0.7


def test_accuracy_is_measured_against_the_labels_and_recorded(
    engine: Engine, session: Session, tmp_path: Path
) -> None:
    seed(session)
    job.score_articles(engine, WordScorer())
    job.classify_articles(engine, SubjectScorer())
    labels = pd.DataFrame(
        {
            "article_id": [1, 2, 3, 5, 99],  # 99 is not stored and is ignored
            "symbol": ["BTC/USD", "BTC/USD", "BTC/USD", "GLD", "GLD"],
            "sentiment": ["positive", "negative", "neutral", "negative", "neutral"],
            "topic": ["price", "price", "regulation", "macro", "other"],
            "labelled_by": ["claude"] * 5,
        }
    )
    assert job.evaluate(engine, version="missing", labels=labels) is None

    words = tmp_path / "words.csv"
    words.write_text("Word,Negative,Positive\nRISES,0,2009\nFALLS,2009,0\n", encoding="utf-8")
    metrics = job.evaluate(engine, version="words-1", lexicon=Lexicon.load(words), labels=labels)
    assert metrics is not None
    assert metrics["model"]["n"] == 4
    assert metrics["model"]["accuracy"] == 0.75  # article 3 was labelled neutral
    assert metrics["baseline"]["accuracy"] == 0.75
    assert metrics["by_symbol"]["GLD"] == {"n": 1, "accuracy": 1.0, "macro_f1": 1.0}
    assert metrics["topics"]["accuracy"] == 0.75  # article 3 was labelled regulation
    assert metrics["labelled_by"] == ["claude"]
    stored = session.scalars(select(ModelRegistry)).one()
    assert stored.name == "sentiment"
    assert stored.metrics["model"]["accuracy"] == 0.75
