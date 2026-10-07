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
    LargeBinary,
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
    # True for an asset found from the user's holdings instead of the configured universe.
    discovered: Mapped[bool] = mapped_column(Boolean, server_default="false")


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
    # Set by the quality job when this article repeats an earlier one; never deleted.
    duplicate_of: Mapped[int | None] = mapped_column(
        ForeignKey("news_articles.id", ondelete="SET NULL")
    )
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
    # What was fetched, for example "bars:BTC/USD:1Hour:us-1" or "news:BTC/USD:BTCUSD".
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


class ModelRegistry(Base):
    """One row per trained model. The parameters are stored here, so scoring needs no file."""

    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(ForeignKey("assets.symbol"))
    version: Mapped[str] = mapped_column(Text)
    trained_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    train_start: Mapped[date] = mapped_column(Date)
    train_end: Mapped[date] = mapped_column(Date)
    # The model in use for this name and symbol. At most one row is current.
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="false")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    artefact_path: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_model_registry_name_symbol", "name", "symbol", "trained_at"),)


class RegimeState(Base):
    """Filtered regime probabilities. `ts` is when the day they describe had ended."""

    __tablename__ = "regime_states"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    model_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Double)
    probs: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Simulation(Base):
    """One simulator run for one asset. Reproducible from `seed` and the data up to `as_of`."""

    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"))
    # When the inputs became known: the end of the last day the run used.
    as_of: Mapped[datetime] = mapped_column(TZDateTime)
    # The regime model the run started from.
    model_id: Mapped[int] = mapped_column(BigInteger)
    model_version: Mapped[str] = mapped_column(Text)
    seed: Mapped[int] = mapped_column(BigInteger)
    n_paths: Mapped[int] = mapped_column(Integer)
    max_steps: Mapped[int] = mapped_column(Integer)
    start_price: Mapped[float] = mapped_column(Double)
    # One entry per horizon: quantiles, ranges, histogram, drawdown.
    horizons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    fan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Compressed float32 cumulative log returns, shape (n_paths, max_steps). Kept for the
    # latest run of each asset only; older runs keep their summaries.
    paths: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("symbol", "as_of", "model_id"),)


class CalibrationReport(Base):
    """How often the simulator's past ranges held, per horizon and range."""

    __tablename__ = "calibration_reports"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    model_version: Mapped[str] = mapped_column(Text, primary_key=True)
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    nominal: Mapped[float] = mapped_column(Double, primary_key=True)
    steps: Mapped[int] = mapped_column(Integer)
    empirical: Mapped[float] = mapped_column(Double)
    empirical_conformal: Mapped[float] = mapped_column(Double)
    n: Mapped[int] = mapped_column(Integer)
    conformal_miss_rate: Mapped[float] = mapped_column(Double)
    pinball_model: Mapped[float] = mapped_column(Double)
    pinball_baseline: Mapped[float] = mapped_column(Double)
    first_origin: Mapped[date] = mapped_column(Date)
    last_origin: Mapped[date] = mapped_column(Date)
    computed_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class VolatilityForecast(Base):
    """A volatility forecast made at `ts` for the following days, by one model.

    `forecast` and `realised` are per-day volatility as a fraction. `realised` is filled
    in once the days it covers have ended.
    """

    __tablename__ = "volatility_forecasts"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "har", "gbt", or one of the simple rivals "carry" and "regime".
    model: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text)
    forecast: Mapped[float] = mapped_column(Double)
    realised: Mapped[float | None] = mapped_column(Double)


class RiskMetric(Base):
    """Value at Risk and expected shortfall estimated at `ts`, by one method.

    Each is the fraction of a position lost over the horizon. `realised_loss` is what
    followed, filled in once the horizon has ended.
    """

    __tablename__ = "risk_metrics"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[float] = mapped_column(Double, primary_key=True)
    # "historical", "filtered", or "simulator".
    method: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text)
    var: Mapped[float] = mapped_column(Double)
    expected_shortfall: Mapped[float] = mapped_column(Double)
    realised_loss: Mapped[float | None] = mapped_column(Double)


class NewsSentiment(Base):
    """The tone of one article according to one model version."""

    __tablename__ = "news_sentiment"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    model_version: Mapped[str] = mapped_column(Text, primary_key=True)
    p_pos: Mapped[float] = mapped_column(Double)
    p_neg: Mapped[float] = mapped_column(Double)
    p_neu: Mapped[float] = mapped_column(Double)
    # p_pos - p_neg, from -1 to +1.
    score: Mapped[float] = mapped_column(Double)


class SentimentAggregate(Base):
    """Tone summarised per asset and bucket. `ts` is when the bucket ended."""

    __tablename__ = "sentiment_agg"

    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    # "1Hour" or "1Day". A stock's day ends at the market close.
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text)
    article_count: Mapped[int] = mapped_column(Integer)
    # Average over the bucket's own articles; empty when it had none.
    score_mean: Mapped[float | None] = mapped_column(Double)
    # Average over all earlier articles, each one's weight halving every 24 hours.
    score_decayed: Mapped[float | None] = mapped_column(Double)


class NewsTopic(Base):
    """The topic one model version assigned to an article."""

    __tablename__ = "news_topics"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), primary_key=True
    )
    model_version: Mapped[str] = mapped_column(Text, primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    # The model's share of belief in the winning topic, from 0 to 1.
    confidence: Mapped[float] = mapped_column(Double)

    __table_args__ = (Index("ix_news_topics_topic", "model_version", "topic"),)


class ForecastLog(Base):
    """A forecast written down on the day it was made. Append-only.

    Nothing in a row changes after it is written except `outcome` and `resolved_at`,
    which are filled in once the days the forecast covered have ended.
    """

    __tablename__ = "forecast_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"))
    # "outlook_range", "volatility", or "loss_limit".
    kind: Mapped[str] = mapped_column(Text)
    horizon_days: Mapped[int] = mapped_column(Integer)
    # Which forecast of that kind: the range's level, the model, or the limit's level.
    key: Mapped[str] = mapped_column(Text)
    # When the inputs became known: the end of the last day the forecast used.
    as_of: Mapped[datetime] = mapped_column(TZDateTime)
    made_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    steps: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(Text)
    forecast: Mapped[dict[str, Any]] = mapped_column(JSONB)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    __table_args__ = (UniqueConstraint("symbol", "kind", "horizon_days", "key", "as_of"),)


class Portfolio(Base):
    """A set of holdings. Version 1 has one, with id 1."""

    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # Where the holdings last came from: "manual", "csv", or "binance".
    source: Mapped[str] = mapped_column(Text)
    # US dollars held as cash, dollar stablecoins included. Not a row in `holdings`,
    # because cash is not an asset with a price history.
    cash: Mapped[float] = mapped_column(Double, server_default="0")
    # The risk level and split the user chose as a target, or null when none is set.
    # It belongs to the user, not to the holdings: a new read of holdings keeps it.
    target: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Core or satellite, by symbol. Kept here and not only on the holdings, so a
    # new read of holdings keeps the tags the user gave.
    tags: Mapped[dict[str, str]] = mapped_column(JSONB, server_default="{}")
    # The exchange's own dollar total per wallet at the last read; empty for manual
    # and CSV. Shown beside what RADAR found, so a gap is never silent.
    wallets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    # Open leveraged exposure as the source reported it; empty for manual and CSV.
    leveraged: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class PortfolioHolding(Base):
    __tablename__ = "holdings"

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"), primary_key=True)
    quantity: Mapped[float] = mapped_column(Double)
    # "core", "satellite", or null.
    tag: Mapped[str | None] = mapped_column(Text)


class PortfolioAnalysis(Base):
    """The latest risk analysis of a portfolio. Replaced whenever holdings or prices change."""

    __tablename__ = "portfolio_analyses"

    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True
    )
    # The close of the last session the analysis used.
    as_of: Mapped[datetime] = mapped_column(TZDateTime)
    computed_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    model_version: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class SignalTrackRecord(Base):
    """What followed one kind of signal on one market in the past, against all days."""

    __tablename__ = "signal_track_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # "regime_change", "abnormal_move", or "sentiment_shock".
    type: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"))
    # The direction within the type: "to turbulent", "up", "negative", and so on.
    variant: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    n: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (UniqueConstraint("type", "symbol", "variant"),)


class Signal(Base):
    """One day a signal's rule fired. `ts` is when that day had ended."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("assets.symbol"))
    ts: Mapped[datetime] = mapped_column(TZDateTime, index=True)
    type: Mapped[str] = mapped_column(Text)
    variant: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    track_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("signal_track_records.id", ondelete="SET NULL")
    )

    __table_args__ = (UniqueConstraint("symbol", "ts", "type"),)


class Brief(Base):
    """One day's brief for one subject, kept with the payload it was written from."""

    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    # A market's symbol, or "PORTFOLIO".
    symbol: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    # The grounded input: every number in `text` is in here.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The text as sentences, each with the page that holds its evidence.
    sentences: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    text: Mapped[str] = mapped_column(Text)
    # "template", or the name of the writer whose text passed the grounding check.
    writer: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("day", "symbol"),)
