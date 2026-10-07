"""Public market data read without any key (decisions 066 and 067).

Some research data is published openly: a regulator's weekly positioning report, an
exchange's hourly bars and funding rates. This reader fetches such data and nothing else:
it only sends GET requests, only to the host-and-path pairs it was built with, never
follows a redirect, and has no way to carry a key. It is separate from the signed
account reader in `binance.py` on purpose, so that one never grows.
"""

import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

import httpx

TIMEOUT_SECONDS = 30.0
Param = str | int | float


class PublicDataError(Exception):
    """The source did not answer, or answered with an error."""


class DisallowedPublicRequestError(PublicDataError):
    """A request to somewhere this reader was not built to read."""


class PublicReader:
    """GET requests to a fixed list of public endpoints, a short pause apart."""

    def __init__(
        self,
        allowed: frozenset[tuple[str, str]],
        *,
        pause_seconds: float = 0.25,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.allowed = allowed
        self._pause = pause_seconds
        self._sleep = sleep
        self._http = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json"},
        )

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
        self._http.close()

    def get(self, host: str, path: str, params: dict[str, Param]) -> Any:
        if (host, path) not in self.allowed:
            raise DisallowedPublicRequestError(f"{host}{path} is not a public source RADAR reads")
        try:
            response = self._http.get(f"https://{host}{path}", params=params)
        except httpx.HTTPError as error:
            raise PublicDataError(f"{host} could not be reached") from error
        if response.status_code != 200:
            raise PublicDataError(f"{host}{path} answered {response.status_code}")
        self._sleep(self._pause)
        return response.json()
