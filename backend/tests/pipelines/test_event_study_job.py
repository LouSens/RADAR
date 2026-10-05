"""The sentiment-versus-price study against the real test database."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import ModelRegistry, SentimentAggregate
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import event_study as job
from tests.pipelines.test_regime_job import wire
from tests.pipelines.test_sentiment_job import BTC, GLD, UNIVERSE

START = datetime(2024, 1, 1, tzinfo=UTC)
DAY = timedelta(days=1)


def seed_bitcoin(session: Session, days: int, news_every: int = 1) -> np.ndarray:
    """Daily bars and daily tone where each day's return follows the previous day's tone."""
    sync_assets(session, UNIVERSE)
    rng = np.random.default_rng(0)
    tone = rng.normal(0, 0.3, days)
    returns = 0.02 * np.roll(tone, 1) + rng.normal(0, 0.01, days)
    prices = 100 * np.exp(np.cumsum(returns))
    upsert_bars(
        session,
        [
            bar_row("BTC/USD", "1Day", "us-1", wire(START + d * DAY, float(prices[d])))
            for d in range(days)
        ],
    )
    for d in range(0, days, news_every):
        session.add(
            SentimentAggregate(
                symbol="BTC/USD",
                bucket="1Day",
                ts=START + (d + 1) * DAY,  # a day's bucket ends at the next midnight
                model_version="words-1",
                article_count=3,
                score_mean=float(tone[d]),
                score_decayed=float(tone[d]),
            )
        )
    session.commit()
    return tone


def test_buckets_map_back_to_the_day_they_describe() -> None:
    ends = pd.DatetimeIndex(["2024-01-02T00:00:00Z"])
    assert job.day_of(BTC, ends)[0] == pd.Timestamp("2024-01-01", tz="UTC")
    close = pd.DatetimeIndex(["2024-01-08T21:00:00Z"])  # Monday's close in New York
    assert job.day_of(GLD, close)[0] == pd.Timestamp("2024-01-08")


def test_study_is_stored_and_finds_tone_leading_price(engine: Engine, session: Session) -> None:
    tone = seed_bitcoin(session, 900)
    with Session(engine) as fresh:
        frame = job.daily_inputs(fresh, BTC)
    # Tone for 1 January sits on the row for 1 January, beside that day's return.
    assert frame["tone"].iloc[5] == tone[5]
    assert frame.index[5] == pd.Timestamp("2024-01-06", tz="UTC")

    result = job.run_asset(engine, BTC)
    assert result is not None
    assert result["n_events"] >= 30
    assert result["verdict"] == "sentiment leads price"
    assert result["days_with_news"] == 900
    lags = {c["lag"]: c for c in result["lags"]}
    assert lags[1]["significant"]
    assert lags[1]["correlation"] > 0.3
    # After unusually good news the price rose on the following day; after bad, it fell.
    assert result["positive"]["mean"][2] > result["positive"]["mean"][1]
    assert result["negative"]["mean"][2] < result["negative"]["mean"][1]

    stored = session.scalars(select(ModelRegistry)).one()
    assert stored.name == "event_study"
    assert stored.metrics["verdict"] == "sentiment leads price"
    job.run_asset(engine, BTC)
    session.expire_all()
    assert len(session.scalars(select(ModelRegistry).where(ModelRegistry.is_current)).all()) == 1
    found = job.current(session, "BTC/USD")
    assert found is not None


def test_thin_news_gives_not_enough_events(engine: Engine, session: Session) -> None:
    seed_bitcoin(session, 400, news_every=10)
    result = job.run_asset(engine, BTC)
    assert result is not None
    assert result["verdict"] == "not enough events"
    assert result["days_with_news"] == 40


def test_no_news_at_all_stores_nothing(engine: Engine, session: Session) -> None:
    sync_assets(session, UNIVERSE)
    upsert_bars(
        session,
        [bar_row("BTC/USD", "1Day", "us-1", wire(START + d * DAY, 100.0 + d)) for d in range(50)],
    )
    session.commit()
    assert job.run_asset(engine, BTC) is None
    assert job.run(engine, UNIVERSE) == 0


def test_each_topic_gets_its_own_verdict(engine: Engine, session: Session) -> None:
    from radar.db.models import NewsArticle, NewsSentiment, NewsSymbol, NewsTopic
    from radar.models import sentiment, topics

    seed_bitcoin(session, 300)
    # One "price" article a day for 200 days, and three "security" articles in all.
    rng = np.random.default_rng(1)
    for i in range(203):
        when = START + (i if i < 200 else i - 150) * DAY + timedelta(hours=6)
        topic = "price" if i < 200 else "security"
        session.add(NewsArticle(id=i + 1, created_at=when, updated_at=when, headline=f"h{i}"))
        session.flush()
        session.add(NewsSymbol(article_id=i + 1, symbol="BTC/USD"))
        session.add(
            NewsSentiment(
                article_id=i + 1,
                model_version=sentiment.MODEL_VERSION,
                p_pos=0.3,
                p_neg=0.3,
                p_neu=0.4,
                score=float(rng.normal(0, 0.3)),
            )
        )
        session.add(
            NewsTopic(
                article_id=i + 1,
                model_version=topics.version_of(topics.MODEL_ID),
                topic=topic,
                confidence=0.6,
            )
        )
    session.commit()

    result = job.run_asset(engine, BTC)
    assert result is not None
    by_topic = {t["topic"]: t for t in result["by_topic"]}
    assert set(by_topic) == {"price", "security"}
    assert by_topic["price"]["days_with_news"] == 200
    assert by_topic["security"]["days_with_news"] == 3
    assert by_topic["security"]["verdict"] == "not enough events"
    assert by_topic["price"]["verdict"] in {"not enough events", "no measurable relationship"}
