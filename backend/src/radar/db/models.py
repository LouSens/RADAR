"""SQLAlchemy models for the clean layer.

Every timestamp is `timestamptz` and holds UTC. Tables are created by Alembic
migrations, never by `metadata.create_all` outside tests of the migrations themselves.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TZDateTime = DateTime(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Asset(Base):
    """One row per asset in the configured universe, keyed by canonical symbol."""

    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    asset_class: Mapped[str] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Per-endpoint symbols, for example {"bars": "BTC/USD", "news": ["BTCUSD"]}.
    provider_symbols: Mapped[dict[str, Any]] = mapped_column(JSONB)
    history_start: Mapped[date] = mapped_column(Date)
    news_start: Mapped[date | None] = mapped_column(Date)


class Bar(Base):
    """OHLCV bar. A TimescaleDB hypertable partitioned on `ts`.

    `loc` is the venue: the Alpaca crypto location, or the feed name for stocks.
    """

    __tablename__ = "bars"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(Text, primary_key=True)
    loc: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    open: Mapped[float] = mapped_column(Double)
    high: Mapped[float] = mapped_column(Double)
    low: Mapped[float] = mapped_column(Double)
    close: Mapped[float] = mapped_column(Double)
    volume: Mapped[float] = mapped_column(Double)
    trade_count: Mapped[int] = mapped_column(BigInteger)
    vwap: Mapped[float] = mapped_column(Double)
    is_quote_only: Mapped[bool] = mapped_column(Boolean)
    is_outlier: Mapped[bool] = mapped_column(Boolean, server_default="false")
    received_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class NewsArticle(Base):
    """A news article, keyed by the provider's article id."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime)
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    author: Mapped[str] = mapped_column(Text, server_default="")
    url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, server_default="")
    received_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())

    __table_args__ = (Index("ix_news_articles_created_at", "created_at"),)


class NewsSymbol(Base):
    """Which universe assets an article is about. `symbol` is the canonical symbol."""

    __tablename__ = "news_symbols"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)

    __table_args__ = (Index("ix_news_symbols_symbol", "symbol"),)


class IngestionRun(Base):
    """One backfill chunk or gap-fill. A finished chunk is never fetched again."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job: Mapped[str] = mapped_column(Text)
    # What was fetched, for example "bars:BTC/USD:1Hour:us-1" or "news:BTCUSD".
    key: Mapped[str] = mapped_column(Text)
    window_start: Mapped[datetime] = mapped_column(TZDateTime)
    window_end: Mapped[datetime] = mapped_column(TZDateTime)
    status: Mapped[str] = mapped_column(Text)
    rows: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (UniqueConstraint("job", "key", "window_start", "window_end"),)


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    symbol: Mapped[str | None] = mapped_column(Text)
    check: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")

    __table_args__ = (Index("ix_data_quality_reports_ts", "ts"),)
