"""The news-and-swings job and its route against the real test database."""

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.db.models import ModelRegistry, SentimentAggregate
from radar.pipelines import news_volatility as job
from tests.pipelines.test_regime_job import DAY, DAYS, START, UNIVERSE, seed


def seed_news(session: Session) -> None:
    """A daily article count and tone for every day but a few, which have no row."""
    rng = np.random.default_rng(2)
    session.add_all(
        SentimentAggregate(
            symbol="BTC/USD",
            bucket="1Day",
            ts=START + (d + 1) * DAY,
            model_version="test",
            article_count=int(rng.poisson(8)),
            score_mean=float(rng.normal(0, 0.3)),
            score_decayed=0.0,
        )
        for d in range(DAYS)
        if d % 37 != 0
    )
    session.commit()


def test_the_comparison_is_stored_and_served(engine: Engine, session: Session) -> None:
    seed(session)
    seed_news(session)
    with TestClient(create_app(engine, UNIVERSE)) as client:
        assert client.get("/api/v1/assets/btc-usd/news-and-swings").status_code == 404
        assert job.run(engine, UNIVERSE) == 1
        body = client.get("/api/v1/assets/btc-usd/news-and-swings").json()

    assert body["symbol"] == "BTC/USD"
    assert body["comparisons"] == 4  # two horizons, two model families
    assert [h["horizon_days"] for h in body["horizons"]] == [1, 7]
    day = body["horizons"][0]
    assert day["n"] >= 30
    assert {p["family"] for p in day["pairs"]} == {"har", "gbt"}
    for horizon in body["horizons"]:
        for pair in horizon["pairs"]:
            assert pair["qlike_without"] > 0
            assert pair["qlike_with"] > 0
            assert pair["verdict"] in {"news helps", "no measurable gain"}
            if pair["dm_p_value"] is not None:
                assert pair["dm_p_adjusted"] >= pair["dm_p_value"] - 1e-12
    # Random news was seeded, so nothing should be credited to it.
    assert body["news_helps"] is False

    # Running again keeps one current row.
    assert job.run(engine, UNIVERSE) == 1
    current = session.scalar(
        select(func.count())
        .select_from(ModelRegistry)
        .where(ModelRegistry.name == job.NAME, ModelRegistry.is_current)
    )
    assert current == 1


def test_days_without_a_news_row_count_as_no_articles(engine: Engine, session: Session) -> None:
    seed(session)
    seed_news(session)
    asset = UNIVERSE.get("BTC/USD")
    days = [START + d * DAY for d in range(DAYS)]
    news = job.daily_news(session, asset, pd.DatetimeIndex(days))
    assert len(news) == DAYS
    assert news["count"].iloc[0] == 0  # day 0 had no row
    assert pd.isna(news["tone"].iloc[0])
    assert news["count"].iloc[1] > 0 or news["count"].iloc[2] > 0
    # A bucket ending at midnight describes the day before it.
    stored = session.scalars(
        select(SentimentAggregate.article_count).where(SentimentAggregate.ts == START + 2 * DAY)
    ).one()
    assert news["count"].iloc[1] == stored
