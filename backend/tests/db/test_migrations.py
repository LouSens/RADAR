from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import Asset, Bar, Base
from radar.db.session import downgrade, upgrade
from radar.universe import load_universe

TABLES = {
    "assets",
    "bars",
    "news_articles",
    "news_symbols",
    "ingestion_runs",
    "data_quality_reports",
    "model_registry",
    "regime_states",
    "simulations",
    "calibration_reports",
    "volatility_forecasts",
}


def test_migrations_create_every_phase_1_table(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= TABLES


def test_bars_is_a_hypertable_on_ts(engine: Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT d.column_name FROM timescaledb_information.dimensions d"
                " WHERE d.hypertable_name = 'bars'"
            )
        ).all()
    assert [r[0] for r in rows] == ["ts"]


def test_models_match_the_migrations(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_then_upgrade_round_trips(engine: Engine) -> None:
    downgrade(engine, "base")
    assert not set(inspect(engine).get_table_names()) & TABLES
    upgrade(engine)
    assert set(inspect(engine).get_table_names()) >= TABLES


def test_server_session_is_utc(session: Session) -> None:
    assert session.execute(text("SHOW timezone")).scalar_one().lower() == "utc"


def test_sync_assets_is_idempotent(session: Session) -> None:
    universe = load_universe()
    assert sync_assets(session, universe) == len(universe.assets)
    assert sync_assets(session, universe) == len(universe.assets)
    session.flush()

    assets = {a.symbol: a for a in session.scalars(select(Asset))}
    assert set(assets) == {a.symbol for a in universe.assets}
    assert assets["GLD"].is_primary
    assert assets["GLD"].provider_symbols == {"bars": "GLD", "news": ["GLD"]}
    assert assets["BTC/USD"].provider_symbols == {"bars": "BTC/USD", "news": ["BTCUSD"]}
    assert assets["SPY"].is_primary
    assert not assets["PAXG/USD"].is_primary


def _bar(ts: datetime, close: float = 100.0) -> Bar:
    return Bar(
        symbol="BTC/USD",
        timeframe="1Hour",
        loc="us-1",
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        trade_count=1,
        vwap=close,
        is_quote_only=False,
    )


def test_bars_store_timezone_aware_utc_timestamps(session: Session) -> None:
    sync_assets(session, load_universe())
    # 08:00 in GMT+8 is midnight UTC: the stored instant must be the same.
    local = datetime(2024, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    session.add(_bar(local))
    session.flush()
    session.expire_all()

    stored = session.scalars(select(Bar)).one()
    assert stored.ts == datetime(2024, 1, 1, tzinfo=UTC)
    assert stored.ts.utcoffset() == timedelta(0)
    assert stored.received_at.utcoffset() == timedelta(0)
    assert stored.is_outlier is False


def test_bars_natural_key_is_unique(session: Session) -> None:
    sync_assets(session, load_universe())
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    session.add(_bar(ts))
    session.flush()
    session.expunge_all()
    session.add(_bar(ts, close=200.0))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_bars_require_a_known_asset(session: Session) -> None:
    session.add(_bar(datetime(2024, 1, 1, tzinfo=UTC)))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
