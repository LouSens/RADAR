"""API response models. The OpenAPI schema built from these generates the frontend types.

Every timestamp is timezone-aware UTC. The frontend converts to the viewer's zone.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel


class AssetOut(BaseModel):
    symbol: str
    # URL-safe form of the symbol, for example "btc-usd". Routes accept either.
    slug: str
    name: str
    asset_class: Literal["crypto", "stock"]
    is_primary: bool
    history_start: date
    news_start: date | None
    # False for assets that only trade during US market hours.
    trades_continuously: bool


class BarOut(BaseModel):
    ts: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_quote_only: bool


class BarsOut(BaseModel):
    symbol: str
    timeframe: str
    # Where the bars come from: the crypto location, or the stock feed.
    source: str | None
    count: int
    bars: list[BarOut]


class SeriesStatus(BaseModel):
    symbol: str
    timeframe: str
    is_primary: bool
    bars: int
    first_ts: AwareDatetime
    last_ts: AwareDatetime
    # Seconds since the end of the latest stored bar.
    lag_seconds: float
    stale: bool
    # Share of expected bars that are missing, from the latest quality report.
    missing_share: float | None


class QualitySummary(BaseModel):
    last_run: AwareDatetime | None
    findings: int
    warnings: int
    failures: int


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    generated_at: AwareDatetime
    database: bool
    last_sync: AwareDatetime | None
    stream_clients: int
    quality: QualitySummary
    series: list[SeriesStatus]


class LiveBar(BaseModel):
    """A live one-minute bar pushed over `WS /stream`. Not stored."""

    type: Literal["bar"]
    symbol: str
    ts: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class LiveNews(BaseModel):
    """A new article pushed over `WS /stream`."""

    type: Literal["news"]
    id: int
    symbols: list[str]
