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
    # Flagged by the quality job: an unusual jump, or a high or low that looks like a bad print.
    is_outlier: bool


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


class RegimeStateOut(BaseModel):
    label: str
    # Average size of a day's price swing in this state, as a fraction (0.02 is 2%).
    typical_daily_volatility: float
    typical_duration_days: float
    # Probability of each other state being next, once this one ends.
    next_states: dict[str, float]


class RegimePoint(BaseModel):
    ts: AwareDatetime
    label: str
    probability: float


class RegimeEvaluationOut(BaseModel):
    """Walk-forward results: every figure is from days the model had not seen."""

    n_days: int
    first_test_day: date
    last_test_day: date
    next_day_volatility: dict[str, float]
    volatility_is_ordered: bool
    model_log_density: float
    baseline_log_density: float
    average_run_length: float


class RegimeModelOut(BaseModel):
    version: str
    trained_at: AwareDatetime
    train_start: date
    train_end: date
    n_train: int
    bic_by_states: dict[str, float]


class RegimeOut(BaseModel):
    symbol: str
    # When the latest reading became known: the end of the day it describes.
    as_of: AwareDatetime
    label: str
    probability: float
    probabilities: dict[str, float]
    # Consecutive days, counting back from the latest, with this label.
    days_in_state: int
    states: list[RegimeStateOut]
    history: list[RegimePoint]
    model: RegimeModelOut
    evaluation: RegimeEvaluationOut | None
