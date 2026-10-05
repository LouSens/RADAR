"""Fan live events out to WebSocket clients.

The worker publishes events with Postgres `NOTIFY`. A background thread listens and hands
each event to the event loop, which sends it to every connected client. The listener is a
plain thread with a blocking connection so it behaves the same on every platform.
"""

import asyncio
import threading
import time

from fastapi import WebSocket
from sqlalchemy import Engine

from radar.ingest.live import NOTIFY_CHANNEL
from radar.logging import get_logger

log = get_logger(__name__)

RECONNECT_SECONDS = 2.0


class LiveHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.listening = threading.Event()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, payload: str) -> None:
        """Send one event to every client; drop clients that have gone away."""
        for client in list(self._clients):
            try:
                await client.send_text(payload)
            except Exception:
                self._clients.discard(client)

    def start(self, engine: Engine, loop: asyncio.AbstractEventLoop) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listen, args=(engine, loop), name="live-listener", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _listen(self, engine: Engine, loop: asyncio.AbstractEventLoop) -> None:
        while not self._stop.is_set():
            try:
                connection = engine.raw_connection()
                try:
                    driver = connection.driver_connection
                    if driver is None:
                        raise RuntimeError("no database connection")
                    driver.autocommit = True
                    driver.execute(f"LISTEN {NOTIFY_CHANNEL}")
                    self.listening.set()
                    while not self._stop.is_set():
                        for message in driver.notifies(timeout=0.5):
                            asyncio.run_coroutine_threadsafe(self.broadcast(message.payload), loop)
                finally:
                    self.listening.clear()
                    connection.close()
            except Exception as exc:
                log.warning("live_listener_error", error=type(exc).__name__)
                time.sleep(RECONNECT_SECONDS)
