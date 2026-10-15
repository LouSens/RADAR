"""Which assets the models run for: the followed markets and holdings with enough days."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.ingest.upsert import upsert_bars
from radar.models.holdings import Holding, Holdings
from radar.pipelines import followed
from radar.pipelines import portfolio as job
from radar.universe import load_universe

START = datetime(2024, 1, 1, tzinfo=UTC)


def daily(session: Session, symbol: str, days: int) -> None:
    upsert_bars(
        session,
        [
            {
                "symbol": symbol,
                "timeframe": "1Day",
                "loc": "us-1",
                "ts": START + timedelta(days=day),
                **dict.fromkeys(("open", "high", "low", "close", "vwap"), 100.0 + day),
                "volume": 1.0,
                "trade_count": 1,
                "is_quote_only": False,
            }
            for day in range(days)
        ],
    )


def test_a_holding_is_analysed_once_it_has_enough_days_and_says_how_many_until_then(
    session: Session,
) -> None:
    universe = load_universe()
    sync_assets(session, universe)
    daily(session, "BTC/USD", 40)  # a followed market: analysed whatever it has
    daily(session, "ETH/USD", followed.MIN_DAYS)  # held, with just enough
    daily(session, "SOL/USD", followed.MIN_DAYS - 1)  # held, one day short
    held = [Holding(symbol=s, quantity=1.0) for s in ("BTC/USD", "ETH/USD", "SOL/USD", "USD")]
    job.store(session, Holdings(source="manual", holdings=held, unsupported=[]))

    by_symbol = {s.symbol: s for s in followed.standing(session, universe)}
    assert set(by_symbol) == {"BTC/USD", "ETH/USD", "SOL/USD"}  # cash has no analysis
    assert by_symbol["BTC/USD"].analysed
    assert by_symbol["ETH/USD"].analysed
    assert (by_symbol["SOL/USD"].analysed, by_symbol["SOL/USD"].days) == (
        False,
        followed.MIN_DAYS - 1,
    )
    assert by_symbol["SOL/USD"].needed == followed.MIN_DAYS

    symbols = [a.symbol for a in followed.assets(session, universe)]
    primary = [a.symbol for a in universe.primary]
    assert symbols == [*primary, "ETH/USD"]  # the markets first, then the holding


def test_an_asset_nobody_holds_is_not_analysed_however_long_its_record(
    session: Session,
) -> None:
    universe = load_universe()
    sync_assets(session, universe)
    daily(session, "ETH/USD", followed.MIN_DAYS + 50)
    assert followed.standing(session, universe) == []
    assert followed.assets(session, universe) == list(universe.primary)
