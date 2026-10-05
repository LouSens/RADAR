"""Minimal Alpaca market data WebSocket session.

Phase 0 uses this only to probe connection behaviour. The live consumers with reconnect
and gap-fill are built in Phase 1. The only host allowed is `stream.data.alpaca.markets`.
"""

import json
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import SecretStr
from websockets.sync.client import ClientConnection, connect

from radar.providers.errors import DisallowedURLError

STREAM_HOST = "stream.data.alpaca.markets"
CRYPTO_STREAM_URL = f"wss://{STREAM_HOST}/v1beta3/crypto/us"
NEWS_STREAM_URL = f"wss://{STREAM_HOST}/v1beta1/news"

CONTROL_TYPES = frozenset({"success", "error", "subscription"})


def validate_stream_url(url: str) -> str:
    """Return `url` unchanged if it is a wss URL on the stream host, else raise."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise DisallowedURLError("Stream URL is not a valid URL") from exc
    allowed = (
        parsed.scheme == "wss"
        and parsed.host == STREAM_HOST
        and parsed.port is None
        and not parsed.userinfo
        and not parsed.query
    )
    if not allowed:
        raise DisallowedURLError(
            f"Refusing stream URL with host {parsed.host!r}: only wss://{STREAM_HOST} is allowed"
        )
    return url


def control_messages(raw: str | bytes) -> list[dict[str, Any]]:
    """Parse one frame and keep only control messages (not market data)."""
    payload = json.loads(raw)
    messages = payload if isinstance(payload, list) else [payload]
    return [m for m in messages if isinstance(m, dict) and m.get("T") in CONTROL_TYPES]


class StreamSession:
    def __init__(self, url: str, *, open_timeout: float = 10.0) -> None:
        self.url = validate_stream_url(url)
        self._ws: ClientConnection = connect(self.url, open_timeout=open_timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._ws.close()

    def read_control(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        """Read frames until one carries a control message. Raises TimeoutError if none."""
        while True:
            messages = control_messages(self._ws.recv(timeout=timeout))
            if messages:
                return messages

    def authenticate(self, key_id: SecretStr, secret_key: SecretStr) -> list[dict[str, Any]]:
        self._ws.send(
            json.dumps(
                {
                    "action": "auth",
                    "key": key_id.get_secret_value(),
                    "secret": secret_key.get_secret_value(),
                }
            )
        )
        return self.read_control()

    def subscribe(self, channels: Mapping[str, Sequence[str]]) -> list[dict[str, Any]]:
        self._ws.send(
            json.dumps({"action": "subscribe", **{k: list(v) for k, v in channels.items()}})
        )
        return self.read_control()
