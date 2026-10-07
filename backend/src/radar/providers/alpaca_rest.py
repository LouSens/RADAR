"""Alpaca market data and news REST client.

This client can only talk to `data.alpaca.markets`. It has no order, position, account,
or transfer methods, and must never gain any.
"""

import random
import re
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Literal, Self

import httpx
from pydantic import SecretStr

from radar.logging import get_logger
from radar.providers.errors import (
    AlpacaError,
    AlpacaHTTPError,
    AlpacaTransportError,
    DisallowedURLError,
)
from radar.providers.rate_limit import TokenBucket
from radar.providers.schemas import (
    Bar,
    BarsPage,
    CorporateActionsPage,
    CryptoSnapshots,
    LatestBars,
    LatestQuotes,
    LatestTrades,
    NewsPage,
    OptionSnapshotsPage,
    Snapshot,
)

log = get_logger(__name__)

REST_HOST = "data.alpaca.markets"
DEFAULT_BASE_URL = f"https://{REST_HOST}"

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 60.0

Sort = Literal["asc", "desc"]
Param = str | int | bool | None
PageHook = Callable[[str, Mapping[str, Param], dict[str, Any]], object]

_LOC = re.compile(r"^[a-z]{2}(-\d)?$")
_TIMEFRAME = re.compile(r"^\d{1,2}(Min|T|Hour|H|Day|D|Week|W|Month|M)$")


def validate_base_url(url: str, *, scheme: str = "https", host: str = REST_HOST) -> str:
    """Return `url` unchanged if it is exactly the allowed host, else raise."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise DisallowedURLError("Base URL is not a valid URL") from exc
    allowed = (
        parsed.scheme == scheme
        and parsed.host == host
        and parsed.port is None
        and not parsed.userinfo
        and parsed.path in ("", "/")
        and not parsed.query
    )
    if not allowed:
        raise DisallowedURLError(
            f"Refusing base URL with host {parsed.host!r}: only {scheme}://{host} is allowed"
        )
    return url


def _rfc3339(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps sent to Alpaca must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _optional_rfc3339(value: datetime | None) -> str | None:
    return None if value is None else _rfc3339(value)


def _check_timeframe(timeframe: str) -> str:
    if not _TIMEFRAME.match(timeframe):
        raise ValueError(f"Invalid timeframe: {timeframe!r}")
    return timeframe


class AlpacaDataClient:
    """Rate-limited, retried, paginated access to Alpaca market data and news."""

    def __init__(
        self,
        key_id: SecretStr | None = None,
        secret_key: SecretStr | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        rate_limiter: TokenBucket | None = None,
        max_retries: int = 5,
        backoff_base_seconds: float = 0.5,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        validate_base_url(base_url)
        if (key_id is None) != (secret_key is None):
            raise ValueError("Provide both Alpaca keys or neither")
        headers = {"Accept": "application/json"}
        if key_id is not None and secret_key is not None:
            headers["APCA-API-KEY-ID"] = key_id.get_secret_value()
            headers["APCA-API-SECRET-KEY"] = secret_key.get_secret_value()
        self.authenticated = key_id is not None
        self._limiter = rate_limiter or TokenBucket()
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._sleep = sleep
        # Redirects are not followed, so a response can never move a request to another host.
        self._http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout_seconds,
            follow_redirects=False,
            event_hooks={"request": [self._assert_allowed_host]},
        )
        self.last_rate_limit: dict[str, str] = {}
        # Called with (path, params, body) for every page read; the raw layer hooks in here.
        self.on_page: PageHook | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"AlpacaDataClient(host={REST_HOST!r}, authenticated={self.authenticated})"

    def close(self) -> None:
        self._http.close()

    @staticmethod
    def _assert_allowed_host(request: httpx.Request) -> None:
        if request.url.host != REST_HOST or request.url.scheme != "https":
            raise DisallowedURLError(f"Refusing request to host {request.url.host!r}")

    # --- transport -----------------------------------------------------------------

    def get_json(self, path: str, params: Mapping[str, Param] | None = None) -> dict[str, Any]:
        """GET a path on the data host, with rate limiting and retries."""
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise DisallowedURLError("Path must be relative to the market data host")
        query = {k: v for k, v in (params or {}).items() if v is not None}

        for attempt in range(self._max_retries + 1):
            self._limiter.acquire()
            retry_after: float | None = None
            error: AlpacaError
            try:
                response = self._http.get(path, params=query)
            except httpx.TransportError as exc:
                error = AlpacaTransportError(path, type(exc).__name__)
            else:
                self._record_rate_limit(response)
                log.debug("alpaca_response", path=path, status=response.status_code, try_=attempt)
                if response.status_code == httpx.codes.OK:
                    body: dict[str, Any] = response.json()
                    return body
                error = AlpacaHTTPError(response.status_code, path, _error_message(response))
                if response.status_code not in RETRYABLE_STATUS:
                    raise error
                retry_after = _retry_after(response)
            if attempt == self._max_retries:
                raise error
            delay = self._backoff(attempt, retry_after)
            log.warning("alpaca_retry", path=path, attempt=attempt + 1, delay=round(delay, 2))
            self._sleep(delay)
        raise AssertionError("unreachable")

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        """Exponential backoff with jitter, never shorter than the server's Retry-After."""
        ceiling = min(MAX_BACKOFF_SECONDS, self._backoff_base * float(2**attempt))
        delay = ceiling * random.uniform(0.5, 1.0)  # noqa: S311
        if retry_after is not None:
            delay = max(delay, min(retry_after, MAX_BACKOFF_SECONDS))
        return delay

    def _record_rate_limit(self, response: httpx.Response) -> None:
        self.last_rate_limit = {
            name: response.headers[name]
            for name in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")
            if name in response.headers
        }

    def _pages(
        self, path: str, params: Mapping[str, Param], max_pages: int | None
    ) -> Iterator[dict[str, Any]]:
        """Follow `next_page_token` to the end, or until `max_pages` pages were read."""
        token: str | None = None
        count = 0
        while True:
            page = self.get_json(path, {**params, "page_token": token})
            if self.on_page is not None:
                self.on_page(path, params, page)
            yield page
            count += 1
            previous, token = token, page.get("next_page_token")
            if not token or (max_pages is not None and count >= max_pages):
                return
            if token == previous:
                raise AlpacaError(f"Pagination of {path} did not advance; stopping")

    # --- crypto --------------------------------------------------------------------

    @staticmethod
    def _crypto_path(loc: str, suffix: str) -> str:
        if not _LOC.match(loc):
            raise ValueError(f"Invalid crypto location: {loc!r}")
        return f"/v1beta3/crypto/{loc}/{suffix}"

    def iter_crypto_bar_pages(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        *,
        loc: str = "us",
        limit: int = 10_000,
        sort: Sort = "asc",
        max_pages: int | None = None,
    ) -> Iterator[BarsPage]:
        params: dict[str, Param] = {
            "symbols": ",".join(symbols),
            "timeframe": _check_timeframe(timeframe),
            "start": _rfc3339(start),
            "end": _optional_rfc3339(end),
            "limit": limit,
            "sort": sort,
        }
        for page in self._pages(self._crypto_path(loc, "bars"), params, max_pages):
            yield BarsPage.model_validate(page)

    def get_crypto_latest_bars(self, symbols: Sequence[str], *, loc: str = "us") -> LatestBars:
        path = self._crypto_path(loc, "latest/bars")
        return LatestBars.model_validate(self.get_json(path, {"symbols": ",".join(symbols)}))

    def get_crypto_latest_quotes(self, symbols: Sequence[str], *, loc: str = "us") -> LatestQuotes:
        path = self._crypto_path(loc, "latest/quotes")
        return LatestQuotes.model_validate(self.get_json(path, {"symbols": ",".join(symbols)}))

    def get_crypto_latest_trades(self, symbols: Sequence[str], *, loc: str = "us") -> LatestTrades:
        path = self._crypto_path(loc, "latest/trades")
        return LatestTrades.model_validate(self.get_json(path, {"symbols": ",".join(symbols)}))

    def get_crypto_snapshots(self, symbols: Sequence[str], *, loc: str = "us") -> CryptoSnapshots:
        """Where each crypto pair stands now: today so far, yesterday, latest quote."""
        path = self._crypto_path(loc, "snapshots")
        return CryptoSnapshots.model_validate(self.get_json(path, {"symbols": ",".join(symbols)}))

    # --- stocks --------------------------------------------------------------------

    def iter_stock_bar_pages(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        *,
        adjustment: Literal["raw", "split", "dividend", "all"] = "all",
        feed: Literal["iex", "sip"] | None = None,
        limit: int = 10_000,
        sort: Sort = "asc",
        max_pages: int | None = None,
    ) -> Iterator[BarsPage]:
        """Stock bars, split- and dividend-adjusted by default (spec 3.5)."""
        params: dict[str, Param] = {
            "symbols": ",".join(symbols),
            "timeframe": _check_timeframe(timeframe),
            "start": _rfc3339(start),
            "end": _optional_rfc3339(end),
            "adjustment": adjustment,
            "feed": feed,
            "limit": limit,
            "sort": sort,
        }
        for page in self._pages("/v2/stocks/bars", params, max_pages):
            yield BarsPage.model_validate(page)

    def get_stock_snapshots(
        self, symbols: Sequence[str], *, feed: Literal["iex", "sip"] | None = "iex"
    ) -> dict[str, Snapshot]:
        """Where each stock or fund stands now: today so far, yesterday, latest quote."""
        body = self.get_json("/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": feed})
        return {symbol: Snapshot.model_validate(part) for symbol, part in body.items()}

    def iter_corporate_action_pages(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        *,
        types: Sequence[str] = ("cash_dividend", "forward_split", "reverse_split"),
        limit: int = 1000,
        max_pages: int | None = None,
    ) -> Iterator[CorporateActionsPage]:
        """Dividends and splits with an ex-date from `start` to `end`. Announcements
        only: this reads what companies declared, nothing about any account."""
        params: dict[str, Param] = {
            "symbols": ",".join(symbols),
            "types": ",".join(types),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": limit,
        }
        for page in self._pages("/v1/corporate-actions", params, max_pages):
            yield CorporateActionsPage.model_validate(page)

    # --- options (quotes and implied volatility only) ------------------------------

    def iter_option_snapshot_pages(
        self,
        underlying: str,
        *,
        expires_from: date | None = None,
        expires_to: date | None = None,
        strike_from: float | None = None,
        strike_to: float | None = None,
        kind: Literal["call", "put"] | None = None,
        limit: int = 1000,
        max_pages: int | None = None,
    ) -> Iterator[OptionSnapshotsPage]:
        """Option contracts on `underlying` with their implied volatility. Used to read
        how large a swing the options market expects; nothing here can trade one."""
        if not re.fullmatch(r"[A-Z.]{1,6}", underlying):
            raise ValueError(f"Invalid underlying symbol: {underlying!r}")
        params: dict[str, Param] = {
            "feed": "indicative",
            "type": kind,
            "expiration_date_gte": expires_from.isoformat() if expires_from else None,
            "expiration_date_lte": expires_to.isoformat() if expires_to else None,
            "strike_price_gte": None if strike_from is None else str(strike_from),
            "strike_price_lte": None if strike_to is None else str(strike_to),
            "limit": limit,
        }
        for page in self._pages(f"/v1beta1/options/snapshots/{underlying}", params, max_pages):
            yield OptionSnapshotsPage.model_validate(page)

    # --- news ----------------------------------------------------------------------

    def iter_news_pages(
        self,
        symbols: Sequence[str],
        start: datetime | None = None,
        end: datetime | None = None,
        *,
        limit: int = 50,
        sort: Sort = "desc",
        include_content: bool = False,
        max_pages: int | None = None,
    ) -> Iterator[NewsPage]:
        """News for provider-format symbols such as `BTCUSD` (no slash)."""
        params: dict[str, Param] = {
            "symbols": ",".join(symbols),
            "start": _optional_rfc3339(start),
            "end": _optional_rfc3339(end),
            "limit": limit,
            "sort": sort,
            "include_content": include_content,
        }
        for page in self._pages("/v1beta1/news", params, max_pages):
            yield NewsPage.model_validate(page)


def collect_bars(pages: Iterator[BarsPage]) -> dict[str, list[Bar]]:
    """Merge bar pages into one list per symbol, in the order received."""
    merged: dict[str, list[Bar]] = {}
    for page in pages:
        for symbol, bars in page.bars.items():
            merged.setdefault(symbol, []).extend(bars)
    return merged


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return str(body["message"])[:200]
    return response.text[:200]


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None
