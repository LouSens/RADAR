"""Live ingestion: reconnecting consumers, handlers, notifications, and restart safety."""

import json
import threading
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pandas as pd
import pytest
import respx
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import Bar, NewsArticle, NewsSymbol
from radar.ingest.backfill import Backfill
from radar.ingest.live import (
    NOTIFY_CHANNEL,
    BarHandler,
    LiveConsumer,
    NewsHandler,
    StreamSpec,
    notify,
)
from radar.providers.alpaca_rest import DEFAULT_BASE_URL, AlpacaDataClient
from radar.providers.alpaca_stream import crypto_stream_url
from radar.providers.rate_limit import TokenBucket
from radar.quality.gaps import expected_crypto, find_gaps
from radar.universe import Universe, load_universe

KEY, SECRET = SecretStr("test-key"), SecretStr("test-secret")
SPEC = StreamSpec("crypto", crypto_stream_url("us-1"), {"bars": ["BTC/USD"]})
OK = [{"T": "success", "msg": "ok"}]


class FakeSession:
    """Plays back a script of frames; an exception in the script is raised."""

    def __init__(self, frames: Sequence[Any], auth: Sequence[Mapping[str, Any]] = OK) -> None:
        self._frames = list(frames)
        self._auth = list(auth)
        self.closed = False

    def read_control(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        return [dict(m) for m in OK]

    def authenticate(self, key_id: SecretStr, secret_key: SecretStr) -> list[dict[str, Any]]:
        return [dict(m) for m in self._auth]

    def subscribe(self, channels: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
        return [{"T": "subscription", **{k: list(v) for k, v in channels.items()}}]

    def read(self, timeout: float | None = None) -> list[dict[str, Any]]:
        frame = self._frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return list(frame)

    def close(self) -> None:
        self.closed = True


def consumer_for(sessions: list[FakeSession]) -> tuple[LiveConsumer, dict[str, list[Any]]]:
    seen: dict[str, list[Any]] = {"messages": [], "connects": [], "sleeps": []}
    stop = threading.Event()
    queue = list(sessions)

    def connect(url: str) -> FakeSession:
        assert url == SPEC.url
        if not queue:
            stop.set()
            raise ConnectionError("no more sessions")
        return queue.pop(0)

    consumer = LiveConsumer(
        SPEC,
        KEY,
        SECRET,
        on_message=seen["messages"].append,
        on_connect=lambda: seen["connects"].append(len(seen["messages"])),
        connect=connect,
        stop=stop,
        sleep=seen["sleeps"].append,
    )
    return consumer, seen


def test_consumer_reconnects_and_refills_after_every_connection() -> None:
    bar1, bar2, bar3 = ({"T": "b", "S": "BTC/USD", "c": c} for c in (1.0, 2.0, 3.0))
    first = FakeSession([[bar1], TimeoutError(), [bar2], ConnectionError("dropped")])
    second = FakeSession([[bar3], ConnectionError("dropped again")])
    consumer, seen = consumer_for([first, second])

    consumer.run()

    assert seen["messages"] == [bar1, bar2, bar3]
    # The gap-fill ran once per connection, each time before any message of that connection.
    assert seen["connects"] == [0, 2]
    assert consumer.connections == 2
    assert first.closed
    assert second.closed
    assert seen["sleeps"][:2] == [1.0, 1.0]  # backoff restarts after a connection that worked


def test_refused_connection_backs_off_without_refilling() -> None:
    refused = [{"T": "error", "code": 406, "msg": "connection limit exceeded"}]
    sessions = [FakeSession([], auth=refused) for _ in range(4)]
    consumer, seen = consumer_for(sessions)

    consumer.run()

    assert seen["connects"] == []
    assert seen["messages"] == []
    assert consumer.connections == 0
    assert seen["sleeps"][:4] == [1.0, 2.0, 4.0, 8.0]
    assert all(s.closed for s in sessions)


def test_stream_error_message_forces_a_reconnect() -> None:
    first = FakeSession([[{"T": "error", "code": 500, "msg": "internal"}]])
    second = FakeSession([[{"T": "b", "S": "BTC/USD"}], ConnectionError()])
    consumer, seen = consumer_for([first, second])
    consumer.run()
    assert seen["connects"] == [0, 0]
    assert len(seen["messages"]) == 1


def test_bar_handler_publishes_canonical_bars_only() -> None:
    published: list[Mapping[str, Any]] = []
    handler = BarHandler(load_universe(), published.append)
    handler({"T": "b", "S": "BTC/USD", "t": "2024-01-01T00:01:00Z", "o": 1, "h": 2, "l": 1, "c": 2})
    handler({"T": "b", "S": "DOGE/USD", "c": 1})  # not in the universe
    handler({"T": "q", "S": "BTC/USD", "bp": 1})  # not a bar
    assert [p["symbol"] for p in published] == ["BTC/USD"]
    assert published[0]["type"] == "bar"
    assert published[0]["close"] == 2


def news_message(article_id: int, symbols: list[str]) -> dict[str, Any]:
    return {
        "T": "n",
        "id": article_id,
        "headline": "Synthetic <b>headline</b>",
        "summary": "Synthetic summary",
        "author": "Test Author",
        "created_at": "2024-02-03T10:00:00Z",
        "updated_at": "2024-02-03T10:00:00Z",
        "url": "https://example.invalid/news/1",
        "content": "",
        "symbols": symbols,
        "source": "benzinga",
    }


def test_news_handler_stores_articles_for_universe_assets(engine: Engine, session: Session) -> None:
    universe = load_universe()
    sync_assets(session, universe)
    session.commit()
    published: list[Mapping[str, Any]] = []
    handler = NewsHandler(universe, engine, published.append)

    handler(news_message(1, ["BTCUSD", "ETHUSD"]))
    handler(news_message(2, ["AAPL"]))  # no universe asset uses this tag
    handler(news_message(1, ["BTCUSD", "ETHUSD"]))  # the same article again
    handler({"T": "n", "id": "broken"})

    assert session.scalars(select(NewsArticle.id)).all() == [1]
    assert session.scalars(select(NewsArticle.headline)).one() == "Synthetic headline"
    assert session.scalars(select(NewsSymbol.symbol)).all() == ["BTC/USD"]
    assert [p["id"] for p in published] == [1, 1]
    assert published[0] == {"type": "news", "id": 1, "symbols": ["BTC/USD"]}


def test_notify_reaches_a_listening_connection(engine: Engine) -> None:
    listener = engine.raw_connection()
    try:
        driver = listener.driver_connection
        assert driver is not None
        driver.autocommit = True
        driver.execute(f"LISTEN {NOTIFY_CHANNEL}")
        notify(engine, {"type": "bar", "symbol": "BTC/USD", "close": 2.5})
        received = list(driver.notifies(timeout=5, stop_after=1))
    finally:
        listener.close()
    assert len(received) == 1
    assert json.loads(received[0].payload) == {"type": "bar", "symbol": "BTC/USD", "close": 2.5}


# --- restart safety --------------------------------------------------------------------

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
                "history_start": "2024-02-25",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            }
        ],
    }
)


def every_hour(request: httpx.Request) -> httpx.Response:
    """A complete market: one bar for every hour in the requested range."""

    def when(name: str) -> datetime:
        return datetime.fromisoformat(request.url.params[name].replace("Z", "+00:00"))

    stamps = pd.date_range(when("start").replace(minute=0, second=0), when("end"), freq="h")
    bars = [
        {
            "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "o": 100.0,
            "h": 101.0,
            "l": 99.0,
            "c": 100.0,
            "v": 1.0,
            "n": 1,
            "vw": 100.0,
        }
        for t in stamps
    ]
    return httpx.Response(200, json={"bars": {"BTC/USD": bars}, "next_page_token": None})


@pytest.fixture
def client() -> Iterator[AlpacaDataClient]:
    with respx.mock(base_url=DEFAULT_BASE_URL, assert_all_called=False) as router:
        router.get("/v1beta3/crypto/us-1/bars").mock(side_effect=every_hour)
        limiter = TokenBucket(rate_per_minute=600_000, capacity=10_000)
        with AlpacaDataClient(KEY, SECRET, rate_limiter=limiter, max_retries=0) as c:
            yield c


def test_a_worker_killed_and_restarted_leaves_no_gaps(
    client: AlpacaDataClient, engine: Engine, session: Session
) -> None:
    sync_assets(session, UNIVERSE)
    session.commit()
    killed_at = datetime(2024, 2, 29, 21, 40, tzinfo=UTC)
    restarted_at = datetime(2024, 3, 2, 9, 15, tzinfo=UTC)  # 36 hours later, across a month end

    Backfill(client, engine, UNIVERSE, now=killed_at).run(news=False)
    before = pd.DatetimeIndex(list(session.scalars(select(Bar.ts).order_by(Bar.ts)).all()))
    assert before[-1] == datetime(2024, 2, 29, 20, tzinfo=UTC)

    # The restart is exactly what the worker does on start and on every reconnect.
    Backfill(client, engine, UNIVERSE, now=restarted_at).run(news=False)
    after = pd.DatetimeIndex(list(session.scalars(select(Bar.ts).order_by(Bar.ts)).all()))

    assert after[0] == datetime(2024, 2, 25, tzinfo=UTC)
    assert after[-1] == datetime(2024, 3, 2, 8, tzinfo=UTC)  # the last hour that had ended
    report = find_gaps(expected_crypto(after[0], after[-1], "1Hour"), after)
    assert report.missing == 0
    assert report.present == len(after) == 153
