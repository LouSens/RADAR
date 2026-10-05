"""The quality job against the real test database."""

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import Bar, DataQualityReport, NewsArticle
from radar.ingest.upsert import bar_row, upsert_bars, upsert_news
from radar.pipelines.quality import run_quality
from radar.providers import schemas
from radar.universe import Universe

T0 = datetime(2024, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)

UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2024-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            }
        ],
    }
)


def bar(i: int, close: float) -> dict[str, object]:
    wire = {"t": T0 + i * HOUR, "o": close, "h": close, "l": close, "c": close, "v": 1, "n": 1}
    return bar_row("BTC/USD", "1Hour", "us-1", schemas.Bar.model_validate({**wire, "vw": close}))


def article(i: int, hour: int, headline: str) -> schemas.NewsArticle:
    stamp = (T0 + hour * HOUR).isoformat()
    return schemas.NewsArticle.model_validate(
        {"id": i, "headline": headline, "created_at": stamp, "updated_at": stamp}
    )


def seed(session: Session) -> None:
    sync_assets(session, UNIVERSE)
    steps = np.random.default_rng(0).normal(0, 0.01, 200)
    closes = [float(c) for c in 100 * np.exp(np.cumsum(steps))]
    closes[120:] = [c * 3 for c in closes[120:]]  # one wild jump at hour 120
    rows = [bar(i, c) for i, c in enumerate(closes) if i not in (50, 51, 52)]  # a 3-hour gap
    upsert_bars(session, rows)
    upsert_news(
        session,
        [
            article(1, 0, "Bitcoin falls"),
            article(2, 3, "Bitcoin falls"),
            article(3, 5, "Something else"),
        ],
        "BTC/USD",
    )
    session.commit()


def test_quality_job_reports_gaps_flags_outliers_and_marks_duplicates(
    engine: Engine, session: Session
) -> None:
    seed(session)
    findings = {f.check: f for f in run_quality(engine, UNIVERSE)}

    gaps = findings["gaps:1Hour"].detail
    assert (gaps["expected"], gaps["missing"], gaps["gap_count"]) == (200, 3, 1)
    assert gaps["largest_gaps"][0]["missing"] == 3
    assert findings["bar_schema:1Hour"].status == "ok"
    assert findings["outliers:1Hour"].detail["flagged"] == 1
    assert findings["news_duplicates"].detail["duplicates"] == 1

    session.expire_all()
    flagged = session.scalars(select(Bar.ts).where(Bar.is_outlier)).all()
    assert flagged == [T0 + 120 * HOUR]
    assert session.scalar(select(Bar.close).where(Bar.ts == T0 + 120 * HOUR)) is not None
    duplicates = dict(session.execute(select(NewsArticle.id, NewsArticle.duplicate_of)).all())
    assert duplicates == {1: None, 2: 1, 3: None}
    assert len(session.scalars(select(DataQualityReport)).all()) == len(findings)


def test_quality_job_is_idempotent(engine: Engine, session: Session) -> None:
    seed(session)
    run_quality(engine, UNIVERSE)
    second = {f.check: f for f in run_quality(engine, UNIVERSE)}
    assert second["outliers:1Hour"].detail == {
        "flagged": 1,
        "suspect_wicks": 0,
        "newly_changed": 0,
        "examples": [(T0 + 120 * HOUR).isoformat()],
    }
    assert second["news_duplicates"].detail["newly_changed"] == 0
    assert second["news_text"].detail["cleaned"] == 0


def test_news_text_is_cleaned_when_stored(session: Session) -> None:
    sync_assets(session, UNIVERSE)
    upsert_news(session, [article(9, 0, "<b>Bitcoin</b> &amp; gold")], "BTC/USD")
    session.flush()
    assert session.scalars(select(NewsArticle.headline)).one() == "Bitcoin & gold"
