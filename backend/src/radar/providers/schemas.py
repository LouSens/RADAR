"""Typed Alpaca market data and news responses.

Field names follow our own vocabulary; aliases are Alpaca's wire names. Every timestamp
is timezone-aware.
"""

from datetime import date
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field


def _none_to_empty_dict(value: Any) -> Any:
    return {} if value is None else value


def _none_to_empty_list(value: Any) -> Any:
    return [] if value is None else value


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class Bar(_Wire):
    timestamp: AwareDatetime = Field(alias="t")
    open: float = Field(alias="o")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    close: float = Field(alias="c")
    volume: float = Field(alias="v")
    trade_count: int = Field(alias="n")
    vwap: float = Field(alias="vw")


class Quote(_Wire):
    timestamp: AwareDatetime = Field(alias="t")
    bid_price: float = Field(alias="bp")
    bid_size: float = Field(alias="bs")
    ask_price: float = Field(alias="ap")
    ask_size: float = Field(alias="as")


class Trade(_Wire):
    timestamp: AwareDatetime = Field(alias="t")
    price: float = Field(alias="p")
    size: float = Field(alias="s")
    taker_side: str | None = Field(default=None, alias="tks")
    trade_id: int | None = Field(default=None, alias="i")


class _Page(_Wire):
    next_page_token: str | None = None


_BarsBySymbol = Annotated[dict[str, list[Bar]], BeforeValidator(_none_to_empty_dict)]


class BarsPage(_Page):
    """One page of historical bars, crypto or stock, keyed by provider symbol."""

    bars: _BarsBySymbol = Field(default_factory=dict)


class LatestBars(_Wire):
    bars: dict[str, Bar] = Field(default_factory=dict)


class LatestQuotes(_Wire):
    quotes: dict[str, Quote] = Field(default_factory=dict)


class LatestTrades(_Wire):
    trades: dict[str, Trade] = Field(default_factory=dict)


class NewsImage(_Wire):
    size: str
    url: str


class NewsArticle(_Wire):
    id: int
    headline: str
    author: str = ""
    created_at: AwareDatetime
    updated_at: AwareDatetime
    summary: str = ""
    content: str = ""
    url: str | None = None
    images: Annotated[list[NewsImage], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )
    symbols: Annotated[list[str], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )
    source: str = ""


class NewsPage(_Page):
    news: Annotated[list[NewsArticle], BeforeValidator(_none_to_empty_list)] = Field(
        default_factory=list
    )


class Snapshot(_Wire):
    """Where a market stands right now: the day so far, the day before, and the latest
    quote and trade. Any part can be missing outside trading hours."""

    daily_bar: Bar | None = Field(default=None, alias="dailyBar")
    previous_daily_bar: Bar | None = Field(default=None, alias="prevDailyBar")
    minute_bar: Bar | None = Field(default=None, alias="minuteBar")
    latest_quote: Quote | None = Field(default=None, alias="latestQuote")
    latest_trade: Trade | None = Field(default=None, alias="latestTrade")


class CryptoSnapshots(_Wire):
    snapshots: dict[str, Snapshot] = Field(default_factory=dict)


class CashDividend(_Wire):
    symbol: str
    ex_date: date
    payable_date: date | None = None
    rate: float
    special: bool = False


class Split(_Wire):
    """`new_rate` new shares for every `old_rate` old ones."""

    symbol: str
    ex_date: date
    new_rate: float
    old_rate: float


_Dividends = Annotated[list[CashDividend], BeforeValidator(_none_to_empty_list)]
_Splits = Annotated[list[Split], BeforeValidator(_none_to_empty_list)]


class CorporateActions(_Wire):
    cash_dividends: _Dividends = Field(default_factory=list)
    forward_splits: _Splits = Field(default_factory=list)
    reverse_splits: _Splits = Field(default_factory=list)


class CorporateActionsPage(_Page):
    corporate_actions: Annotated[CorporateActions, BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=CorporateActions
    )


class Greeks(_Wire):
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None


class OptionSnapshot(_Wire):
    """One option contract now. `implied_volatility` is the yearly swing the option's
    price implies, as a fraction; missing when the contract has no usable quote."""

    implied_volatility: float | None = Field(default=None, alias="impliedVolatility")
    greeks: Greeks | None = None
    latest_quote: Quote | None = Field(default=None, alias="latestQuote")


class OptionSnapshotsPage(_Page):
    snapshots: Annotated[dict[str, OptionSnapshot], BeforeValidator(_none_to_empty_dict)] = Field(
        default_factory=dict
    )
