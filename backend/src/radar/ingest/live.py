"""Live ingestion: stream consumers that reconnect, and the REST gap-fill behind them.

Stored bars always come from the REST API, through the same backfill used for history.
The streams do two things: push live prices and new articles to the app, and tell the
worker when to run the gap-fill. So a dropped connection or a restarted worker can
never leave a hole: the next connection fills everything since the last stored bar.
"""

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine, text

from radar.db.session import session_scope
from radar.ingest.backfill import Backfill, BackfillResult
from radar.ingest.upsert import upsert_news
from radar.logging import get_logger
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.schemas import NewsArticle
from radar.universe import Universe

log = get_logger(__name__)

NOTIFY_CHANNEL = "radar_live"
MAX_BACKOFF_SECONDS = 60.0


class StreamError(Exception):
    """The stream refused authentication or a subscription, or reported an error."""


class Session(Protocol):
    """The part of `StreamSession` the consumer uses; tests supply a fake."""

    def read(self, timeout: float | None = None) -> list[dict[str, Any]]: ...
    def read_control(self, timeout: float = 5.0) -> list[dict[str, Any]]: ...
    def authenticate(self, key_id: SecretStr, secret_key: SecretStr) -> list[dict[str, Any]]: ...
    def subscribe(self, channels: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class StreamSpec:
    name: str
    url: str
    channels: Mapping[str, Sequence[str]]


def _raise_on_error(step: str, messages: Sequence[Mapping[str, Any]]) -> None:
    for message in messages:
        if message.get("T") == "error":
            raise StreamError(f"{step}: {message.get('code')} {message.get('msg')}")


class LiveConsumer:
    """Keep one stream connected; call `on_connect` after every (re)connection."""

    def __init__(
        self,
        spec: StreamSpec,
        key_id: SecretStr,
        secret_key: SecretStr,
        *,
        on_message: Callable[[dict[str, Any]], None],
        on_connect: Callable[[], object],
        connect: Callable[[str], Session],
        stop: threading.Event,
        sleep: Callable[[float], None] = time.sleep,
        idle_timeout: float = 30.0,
    ) -> None:
        self.spec = spec
        self._key_id = key_id
        self._secret_key = secret_key
        self._on_message = on_message
        self._on_connect = on_connect
        self._connect = connect
        self._stop = stop
        self._sleep = sleep
        self._idle_timeout = idle_timeout
        self.connections = 0

    def _serve(self, session: Session) -> None:
        _raise_on_error("connect", session.read_control())
        _raise_on_error("authenticate", session.authenticate(self._key_id, self._secret_key))
        _raise_on_error("subscribe", session.subscribe(self.spec.channels))
        self.connections += 1
        log.info("stream_connected", stream=self.spec.name, connections=self.connections)
        self._on_connect()  # fill whatever was missed while disconnected
        while not self._stop.is_set():
            try:
                messages = session.read(timeout=self._idle_timeout)
            except TimeoutError:
                continue  # quiet markets and quiet news are normal
            _raise_on_error("stream", messages)
            for message in messages:
                if message.get("T") not in ("success", "subscription"):
                    self._on_message(message)

    def run(self) -> None:
        """Serve the stream until `stop` is set, reconnecting with backoff."""
        delay = 1.0
        while not self._stop.is_set():
            connected_before = self.connections
            session: Session | None = None
            try:
                session = self._connect(self.spec.url)
                self._serve(session)
            except Exception as exc:
                detail = str(exc) if isinstance(exc, StreamError) else type(exc).__name__
                log.warning("stream_dropped", stream=self.spec.name, error=detail, retry_in=delay)
            finally:
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        log.debug("stream_close_failed", stream=self.spec.name)
            if self._stop.is_set():
                return
            if self.connections > connected_before:
                delay = 1.0  # it worked for a while; start the backoff again
            self._sleep(delay)
            delay = min(MAX_BACKOFF_SECONDS, delay * 2)


class Syncer:
    """Runs the incremental backfill. Only one sync runs at a time."""

    def __init__(self, client: AlpacaDataClient, engine: Engine, universe: Universe) -> None:
        self._client = client
        self._engine = engine
        self._universe = universe
        self._lock = threading.Lock()

    def sync(self, *, bars: bool = True, news: bool = True) -> BackfillResult:
        with self._lock:
            result = Backfill(self._client, self._engine, self._universe).run(bars=bars, news=news)
        log.info(
            "sync_done",
            rows_changed=result.rows_changed,
            windows_fetched=result.windows_fetched,
            failures=len(result.failures),
        )
        return result


def notify(engine: Engine, payload: Mapping[str, Any]) -> None:
    """Publish a live event to every listening API process."""
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": NOTIFY_CHANNEL, "payload": json.dumps(payload, default=str)},
        )


class BarHandler:
    """Forward live minute bars to the app. They are not stored (see the module note)."""

    def __init__(self, universe: Universe, publish: Callable[[Mapping[str, Any]], None]) -> None:
        self._symbols = {asset.bars_symbol: asset.symbol for asset in universe.assets}
        self._publish = publish

    def __call__(self, message: dict[str, Any]) -> None:
        symbol = self._symbols.get(str(message.get("S")))
        if message.get("T") != "b" or symbol is None:
            return
        self._publish(
            {
                "type": "bar",
                "symbol": symbol,
                "ts": message.get("t"),
                "open": message.get("o"),
                "high": message.get("h"),
                "low": message.get("l"),
                "close": message.get("c"),
                "volume": message.get("v"),
            }
        )


class NewsHandler:
    """Store each new article for the assets it concerns, then tell the app."""

    def __init__(
        self, universe: Universe, engine: Engine, publish: Callable[[Mapping[str, Any]], None]
    ) -> None:
        self._universe = universe
        self._engine = engine
        self._publish = publish

    def __call__(self, message: dict[str, Any]) -> None:
        if message.get("T") != "n":
            return
        try:
            article = NewsArticle.model_validate(message)
        except ValidationError:
            log.warning("news_message_invalid", id=message.get("id"))
            return
        symbols = [
            asset.symbol
            for asset in self._universe.assets
            if set(asset.news_symbols) & set(article.symbols)
        ]
        if not symbols:
            return
        with session_scope(self._engine) as session:
            for symbol in symbols:
                upsert_news(session, [article], symbol)
        self._publish({"type": "news", "id": article.id, "symbols": symbols})
