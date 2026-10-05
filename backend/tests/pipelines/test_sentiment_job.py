"""Sentiment scoring and aggregation against the real test database."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import NewsArticle, NewsSentiment, NewsSymbol, SentimentAggregate
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
