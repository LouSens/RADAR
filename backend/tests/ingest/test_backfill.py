"""Backfill against a mocked Alpaca API and the real test database."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import Bar, IngestionRun, NewsArticle, NewsSymbol
from radar.ingest.backfill import Backfill, completed_bars, month_windows, year_windows
from radar.ingest.raw_store import RawStore
from radar.providers import schemas
from radar.providers.alpaca_rest import DEFAULT_BASE_URL, AlpacaDataClient
from radar.providers.rate_limit import TokenBucket
from radar.universe import Universe

NOW = datetime(2024, 3, 10, 12, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)
BARS_PATH = "/v1beta3/crypto/us-1/bars"

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
                "history_start": date(2024, 1, 1),
                "news_symbols": ["BTCUSD"],
                "news_start": date(2022, 1, 1),
            }
        ],
    }
)


def wire_bar(ts: datetime, close: float = 100.0) -> dict[str, Any]:
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "t": stamp,
        "o": close,
        "h": close,
        "l": close,
        "c": close,
        "v": 1.5,
        "n": 3,
        "vw": close,
    }


def bars_response(request: httpx.Request) -> httpx.Response:
    """Two bars at the start of the window; March also has a finished and an open hour."""
    start = datetime.fromisoformat(request.url.params["start"].replace("Z", "+00:00"))
    bars = [wire_bar(start), wire_bar(start + HOUR)]
    if start.month == 3:
        bars += [wire_bar(datetime(2024, 3, 10, 11, tzinfo=UTC)), wire_bar(NOW.replace(minute=0))]
    return httpx.Response(200, json={"bars": {"BTC/USD": bars}, "next_page_token": None})


def news_response(request: httpx.Request) -> httpx.Response:
    start = request.url.params["start"]
    news = []
    if start.startswith("2024-02"):
        news = [
            {
                "id": 7,
                "headline": "Synthetic headline",
                "author": "Test Author",
                "created_at": "2024-02-03T10:00:00Z",
                "updated_at": "2024-02-03T10:00:00Z",
                "summary": "Synthetic summary",
                "content": "",
                "url": "https://example.invalid/news/7",
                "images": [],
                "symbols": ["BTCUSD", "ETHUSD"],
                "source": "benzinga",
            }
        ]
    return httpx.Response(200, json={"news": news, "next_page_token": None})


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=DEFAULT_BASE_URL, assert_all_called=False) as router:
        router.get(BARS_PATH).mock(side_effect=bars_response)
        router.get("/v1beta1/news").mock(side_effect=news_response)
        yield router


@pytest.fixture
def client(api: respx.MockRouter, tmp_path: Path) -> Iterator[AlpacaDataClient]:
    limiter = TokenBucket(rate_per_minute=600_000, capacity=10_000)
    with AlpacaDataClient(
        SecretStr("test-key"),
        SecretStr("test-secret"),
        rate_limiter=limiter,
        max_retries=0,
        sleep=lambda _: None,
    ) as c:
        c.on_page = RawStore(tmp_path / "raw").record
        yield c


@pytest.fixture
def seeded(session: Session, engine: Engine) -> Engine:
    sync_assets(session, UNIVERSE)
    session.commit()
    return engine


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_windows_are_calendar_aligned() -> None:
    start = datetime(2024, 1, 15, tzinfo=UTC)
    months = list(month_windows(start, NOW))
    assert months == [
        (start, datetime(2024, 2, 1, tzinfo=UTC)),
        (datetime(2024, 2, 1, tzinfo=UTC), datetime(2024, 3, 1, tzinfo=UTC)),
        (datetime(2024, 3, 1, tzinfo=UTC), datetime(2024, 4, 1, tzinfo=UTC)),
    ]
    assert list(year_windows(datetime(2022, 6, 1, tzinfo=UTC), NOW))[-1] == (
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_bars_still_forming_are_dropped() -> None:
    bars = [
        schemas.Bar.model_validate(wire_bar(datetime(2024, 3, 10, 11, tzinfo=UTC))),
        schemas.Bar.model_validate(wire_bar(datetime(2024, 3, 10, 12, tzinfo=UTC))),
    ]
    kept = completed_bars(bars, "1Hour", NOW)
    assert [b.timestamp.hour for b in kept] == [11]


def test_backfill_stores_bars_news_and_raw_files(
    client: AlpacaDataClient, seeded: Engine, session: Session, tmp_path: Path
) -> None:
    result = Backfill(client, seeded, UNIVERSE, now=NOW).run()

    assert result.failures == []
    assert count(session, Bar) == 7  # 2 + 2 + 3; the hour still forming is not stored
    assert session.scalar(select(func.max(Bar.ts))) == datetime(2024, 3, 10, 11, tzinfo=UTC)
    bar = session.scalars(select(Bar).order_by(Bar.ts)).first()
    assert bar is not None
    assert (bar.symbol, bar.timeframe, bar.loc) == ("BTC/USD", "1Hour", "us-1")
    assert bar.is_quote_only is False

    assert count(session, NewsArticle) == 1
    link = session.scalars(select(NewsSymbol)).one()
    assert (link.article_id, link.symbol) == (7, "BTC/USD")  # canonical symbol, not BTCUSD
    assert result.rows_changed == 7 + 2

    raw = tmp_path / "raw"
    assert len(list((raw / "alpaca_crypto_bars_us-1").rglob("*.parquet"))) == 3
    assert len(list((raw / "alpaca_news").rglob("*.parquet"))) == 1


def test_rerun_changes_zero_rows_and_skips_finished_windows(
    client: AlpacaDataClient, seeded: Engine, session: Session, api: respx.MockRouter
) -> None:
    first = Backfill(client, seeded, UNIVERSE, now=NOW).run()
    calls_after_first = len(api.calls)
    received = dict(session.execute(select(Bar.ts, Bar.received_at)).all())

    second = Backfill(client, seeded, UNIVERSE, now=NOW).run()

    assert first.rows_changed > 0
    assert second.rows_changed == 0
    assert second.failures == []
    # Only the two windows that contain "now" are fetched again: one of bars, one of news.
    assert len(api.calls) - calls_after_first == 2
    assert second.windows_fetched == 2
    assert second.windows_skipped == first.windows_fetched - 2
    session.expire_all()
    assert dict(session.execute(select(Bar.ts, Bar.received_at)).all()) == received

    runs = {
        (r.window_start.month, r.status)
        for r in session.scalars(select(IngestionRun).where(IngestionRun.key.like("bars:%")))
    }
    assert runs == {(1, "done"), (2, "done"), (3, "partial")}


def test_a_revised_bar_is_updated_in_place(
    client: AlpacaDataClient, seeded: Engine, session: Session, api: respx.MockRouter
) -> None:
    Backfill(client, seeded, UNIVERSE, now=NOW).run(news=False)

    def revised(request: httpx.Request) -> httpx.Response:
        bar = wire_bar(datetime(2024, 3, 10, 11, tzinfo=UTC), close=250.0)
        return httpx.Response(200, json={"bars": {"BTC/USD": [bar]}, "next_page_token": None})

    api.get(BARS_PATH).mock(side_effect=revised)
    result = Backfill(client, seeded, UNIVERSE, now=NOW).run(news=False)

    assert result.rows_changed == 1
    assert count(session, Bar) == 7
    latest = session.scalars(select(Bar).order_by(Bar.ts.desc())).first()
    assert latest is not None
    assert latest.close == 250.0


def test_a_failed_window_is_retried_on_the_next_run(
    client: AlpacaDataClient, seeded: Engine, session: Session, api: respx.MockRouter
) -> None:
    def february_fails(request: httpx.Request) -> httpx.Response:
        if request.url.params["start"].startswith("2024-02"):
            return httpx.Response(500, json={"message": "boom"})
        return bars_response(request)

    api.get(BARS_PATH).mock(side_effect=february_fails)
    first = Backfill(client, seeded, UNIVERSE, now=NOW).run(news=False)

    assert len(first.failures) == 1
    assert "2024-02-01" in first.failures[0]
    assert count(session, Bar) == 5  # January and March arrived; the job carried on
    failed = session.scalars(select(IngestionRun).where(IngestionRun.status == "failed")).one()
    assert failed.window_start.month == 2
    assert failed.error is not None

    api.get(BARS_PATH).mock(side_effect=bars_response)
    before = len(api.calls)
    second = Backfill(client, seeded, UNIVERSE, now=NOW).run(news=False)

    assert second.failures == []
    assert second.rows_changed == 2
    assert len(api.calls) - before == 2  # February again, plus the open March window
    assert count(session, Bar) == 7
    session.expire_all()
    assert session.scalars(select(IngestionRun).where(IngestionRun.status == "failed")).all() == []


def test_an_older_news_revision_does_not_replace_a_newer_one(
    seeded: Engine, session: Session
) -> None:
    from radar.ingest.upsert import upsert_news

    def article(updated: str, headline: str) -> schemas.NewsArticle:
        return schemas.NewsArticle.model_validate(
            {
                "id": 9,
                "headline": headline,
                "created_at": "2024-02-01T00:00:00Z",
                "updated_at": updated,
                "symbols": ["BTCUSD"],
            }
        )

    assert upsert_news(session, [article("2024-02-02T00:00:00Z", "second")], "BTC/USD") == 2
    assert upsert_news(session, [article("2024-02-01T00:00:00Z", "first")], "BTC/USD") == 0
    assert upsert_news(session, [article("2024-02-03T00:00:00Z", "third")], "BTC/USD") == 1
    session.flush()
    session.expire_all()
    assert session.scalars(select(NewsArticle.headline)).one() == "third"
