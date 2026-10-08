"""The newest price of an asset: the latest trade when Alpaca can be asked, otherwise
the newest stored bar.

Daily closes are what the analysis is worked out on, but a price to act on has to be
the price now. A Bitcoin daily close can be most of a day old.
"""

from collections.abc import Callable, Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.config import load_settings
from radar.db.models import Bar
from radar.logging import get_logger
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.errors import AlpacaError
from radar.universe import Asset

log = get_logger(__name__)

# A price and when it was the price.
Latest = tuple[float, datetime]
# Asked for some assets and the crypto location, gives their latest trades.
Reader = Callable[[Iterable[Asset], str], dict[str, Latest]]


def none(assets: Iterable[Asset], crypto_location: str) -> dict[str, Latest]:
    """A reader that asks no one: stored prices only."""
    return {}


def stored(session: Session, symbols: Iterable[str]) -> dict[str, Latest]:
    """The close of the newest stored bar of each symbol, hourly or daily."""
    wanted = list(symbols)
    if not wanted:
        return {}
    newest = (
        select(Bar.symbol, func.max(Bar.ts).label("ts"))
        .where(Bar.symbol.in_(wanted))
        .group_by(Bar.symbol)
        .subquery()
    )
    rows = session.execute(
        select(Bar.symbol, Bar.close, Bar.ts).join(
            newest, (Bar.symbol == newest.c.symbol) & (Bar.ts == newest.c.ts)
        )
    ).all()
    return {symbol: (float(close), ts) for symbol, close, ts in rows}


def live(assets: Iterable[Asset], crypto_location: str) -> dict[str, Latest]:
    """The latest trade of each asset, asked of Alpaca's market data now. Empty when no
    key is set or Alpaca cannot be reached: the caller falls back to stored prices."""
    settings = load_settings()
    key, secret = settings.alpaca_api_key_id, settings.alpaca_api_secret_key
    chosen = list(assets)
    if key is None or secret is None or not chosen:
        return {}
    crypto = {a.bars_symbol or a.symbol: a.symbol for a in chosen if a.asset_class == "crypto"}
    stocks = {a.bars_symbol or a.symbol: a.symbol for a in chosen if a.asset_class != "crypto"}
    found: dict[str, Latest] = {}
    try:
        with AlpacaDataClient(key, secret) as client:
            if crypto:
                trades = client.get_crypto_latest_trades(list(crypto), loc=crypto_location)
                for name, trade in trades.trades.items():
                    if name in crypto:
                        found[crypto[name]] = (trade.price, trade.timestamp)
            if stocks:
                for name, snapshot in client.get_stock_snapshots(list(stocks)).items():
                    last = snapshot.latest_trade
                    if name in stocks and last is not None:
                        found[stocks[name]] = (last.price, last.timestamp)
    except AlpacaError as exc:
        log.warning("live_prices_unavailable", error=str(exc)[:200])
    return found


def newest(*sources: dict[str, Latest]) -> dict[str, Latest]:
    """For each symbol, whichever source has the later price."""
    merged: dict[str, Latest] = {}
    for source in sources:
        for symbol, (price, at) in source.items():
            if symbol not in merged or at > merged[symbol][1]:
                merged[symbol] = (price, at)
    return merged
