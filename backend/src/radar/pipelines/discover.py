"""Find and register assets the user holds that RADAR does not know yet.

The configured universe says which markets RADAR analyses. Holdings can be anything, and
change. When a holdings source reports a name with no price history, this module looks
for it in Alpaca's market data, records it in the `assets` table as discovered, and
fetches its history, so that the next read can price it. Nothing is added by hand.

Two rules keep a name from being matched to the wrong instrument:

- A name Binance marks as a tokenised US stock (`EQ_` plus the ticker) is looked up as a
  stock only.
- Every other name is looked up as a crypto pair against the dollar only. Many crypto
  names are also stock tickers, and a wrong match would silently misprice a holding.

A discovered asset is priced and counted in the money at once. It joins the risk figures
when it has enough history, like any other holding.
"""

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import Asset as AssetRow
from radar.db.session import session_scope
from radar.ingest.backfill import Backfill
from radar.logging import get_logger
from radar.providers.alpaca_rest import AlpacaDataClient, collect_bars
from radar.providers.errors import AlpacaError
from radar.universe import Asset, Universe

log = get_logger(__name__)

STOCK_PREFIX = "EQ_"
STOCK_START = datetime(2016, 1, 4, tzinfo=UTC)
CRYPTO_START = datetime(2021, 1, 1, tzinfo=UTC)
_TICKER = re.compile(r"^[A-Z0-9.]{1,10}$")
# Names tried per call, so one read cannot start an unbounded number of lookups.
MAX_NAMES = 10


def find(client: AlpacaDataClient, name: str, crypto_location: str) -> Asset | None:
    """The asset a holdings name refers to, if Alpaca has prices for it."""
    raw = name.strip().upper()
    is_stock = raw.startswith(STOCK_PREFIX)
    ticker = raw[len(STOCK_PREFIX) :] if is_stock else raw
    if not _TICKER.match(ticker):
        return None
    try:
        if is_stock:
            bars = collect_bars(
                client.iter_stock_bar_pages(
                    [ticker], "1Day", start=STOCK_START, feed="iex", max_pages=1
                )
            ).get(ticker, [])
            if not bars:
                return None
            return Asset(
                symbol=ticker,
                name=ticker,
                asset_class="stock",
                bars_symbol=ticker,
                history_start=bars[0].timestamp.date(),
            )
        pair = f"{ticker}/USD"
        bars = collect_bars(
            client.iter_crypto_bar_pages(
                [pair], "1Day", start=CRYPTO_START, loc=crypto_location, max_pages=1
            )
        ).get(pair, [])
        if not bars:
            return None
        return Asset(
            symbol=pair,
            name=ticker,
            asset_class="crypto",
            bars_symbol=pair,
            history_start=max(bars[0].timestamp.date(), CRYPTO_START.date()),
        )
    except AlpacaError as error:
        log.warning("discover_lookup_failed", name=ticker, reason=str(error))
        return None


def register(session: Session, assets: Iterable[Asset]) -> None:
    """Record discovered assets. One already stored is only marked as discovered."""
    rows = [
        {
            "symbol": a.symbol,
            "name": a.name,
            "asset_class": a.asset_class,
            "is_primary": False,
            "provider_symbols": {"bars": a.bars_symbol, "news": []},
            "history_start": a.history_start,
            "news_start": None,
            "discovered": True,
        }
        for a in assets
    ]
    if rows:
        session.execute(
            insert(AssetRow)
            .values(rows)
            .on_conflict_do_update(index_elements=[AssetRow.symbol], set_={"discovered": True})
        )


def extend(universe: Universe, session: Session) -> Universe:
    """The configured universe plus every discovered asset."""
    known = {a.symbol for a in universe.assets}
    rows = session.scalars(
        select(AssetRow).where(AssetRow.discovered).order_by(AssetRow.symbol)
    ).all()
    extra = tuple(
        Asset(
            symbol=row.symbol,
            name=row.name,
            asset_class="crypto" if row.asset_class == "crypto" else "stock",
            bars_symbol=str(row.provider_symbols.get("bars", row.symbol)),
            history_start=row.history_start if isinstance(row.history_start, date) else date.min,
        )
        for row in rows
        if row.symbol not in known
    )
    return (
        universe if not extra else universe.model_copy(update={"assets": universe.assets + extra})
    )


def discover(
    client: AlpacaDataClient, engine: Engine, universe: Universe, names: Iterable[str]
) -> list[Asset]:
    """Look up unknown holdings names, register those found, and fetch their history."""
    known = {a.symbol for a in universe.assets}
    found: dict[str, Asset] = {}
    for name in list(dict.fromkeys(names))[:MAX_NAMES]:
        asset = find(client, name, universe.crypto_location)
        if asset is not None and asset.symbol not in known:
            found[asset.symbol] = asset
    if not found:
        return []
    new = list(found.values())
    with session_scope(engine) as session:
        register(session, new)
    # Only the new assets: the rest of the universe is kept up to date by the worker.
    only_new = universe.model_copy(
        update={"assets": tuple(a for a in universe.assets if a.is_primary)[:1] + tuple(new)}
    )
    job = Backfill(client, engine, only_new)
    for asset in new:
        for timeframe in only_new.timeframes_for(asset):
            job.backfill_bars(asset, timeframe)
    log.info(
        "assets_discovered",
        symbols=[a.symbol for a in new],
        rows=job.result.rows_changed,
        failures=len(job.result.failures),
    )
    return new
