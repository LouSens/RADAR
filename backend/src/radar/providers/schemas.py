"""Typed Alpaca market data and news responses.

Field names follow our own vocabulary; aliases are Alpaca's wire names. Every timestamp
is timezone-aware.
"""

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
