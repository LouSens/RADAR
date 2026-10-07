"""Daily bars for markets used only in research notebooks (decision 064).

These markets are not part of the app, so their bars are kept as Parquet files in the
gitignored `data/research/` and never written to the app's tables. Fetched once from
Alpaca's data API and read from the file after that.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import structlog

from radar.features.calendars import session_of
from radar.providers import binance_public, cftc
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.public import PublicReader
from radar.providers.schemas import Bar

log = structlog.get_logger(__name__)

STORE = Path("data/research/daily")
BINANCE_STORE = Path("data/research/binance")
POSITIONS_STORE = Path("data/research/positions")
START = datetime(2016, 1, 1, tzinfo=UTC)
FIELDS = ["open", "high", "low", "close", "volume"]
# The full-market feed is free only for bars older than 15 minutes, as in the backfill.
STOCK_DELAY = timedelta(minutes=20)


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def path_of(symbol: str, store: Path = STORE) -> Path:
    return store / f"{symbol.replace('/', '-')}.parquet"


def to_frame(bars: list[Bar], crypto: bool) -> pd.DataFrame:
    """Bars as a table indexed by day: the UTC day for crypto, the session for stocks."""
    frame = pd.DataFrame(
        [[bar.open, bar.high, bar.low, bar.close, bar.volume] for bar in bars],
        columns=FIELDS,
        index=pd.DatetimeIndex([bar.timestamp for bar in bars]).tz_convert("UTC"),
    )
    index = pd.DatetimeIndex(frame.index)
    frame.index = index.tz_localize(None).normalize() if crypto else session_of(index)
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def fetch(client: AlpacaDataClient, symbol: str, now: datetime, loc: str) -> pd.DataFrame:
    """Every completed daily bar of one market since 2016."""
    if is_crypto(symbol):
        pages = client.iter_crypto_bar_pages([symbol], "1Day", START, now, loc=loc)
    else:
        pages = client.iter_stock_bar_pages([symbol], "1Day", START, now - STOCK_DELAY, feed="sip")
    bars = [bar for page in pages for bar in page.bars.get(symbol, [])]
    if not bars:
        return pd.DataFrame(columns=FIELDS)
    frame = to_frame(bars, is_crypto(symbol))
    # The newest crypto bar is the day still in progress.
    return frame.iloc[:-1] if is_crypto(symbol) else frame


def load(
    symbols: list[str],
    client: AlpacaDataClient | None,
    loc: str,
    store: Path = STORE,
    now: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Each market's daily bars, from its file when there is one, fetched otherwise.
    Without a client, markets that have no file are left out."""
    store.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        target = path_of(symbol, store)
        if target.exists():
            result[symbol] = pd.read_parquet(target)
        elif client is not None:
            frame = fetch(client, symbol, now or datetime.now(UTC), loc)
            if len(frame):
                frame.to_parquet(target)
                result[symbol] = frame
            log.info("research_bars_fetched", symbol=symbol, days=len(frame))
    return result


def load_binance(
    symbols: list[str],
    source: PublicReader | None,
    start: datetime,
    end: datetime,
    store: Path = BINANCE_STORE,
) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    """Hourly bars and funding rates for each symbol, from file when there is one."""
    store.mkdir(parents=True, exist_ok=True)
    first, last = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    result: dict[str, tuple[pd.DataFrame, pd.Series]] = {}
    for symbol in symbols:
        bars_file, funding_file = (
            store / f"{symbol}-bars.parquet",
            store / f"{symbol}-funding.parquet",
        )
        if bars_file.exists() and funding_file.exists():
            result[symbol] = (pd.read_parquet(bars_file), pd.read_parquet(funding_file)["funding"])
        elif source is not None:
            bars = binance_public.hourly_bars(source, symbol, first, last)
            funding = binance_public.funding_rates(source, symbol, first, last)
            if len(bars) and len(funding):
                bars.to_parquet(bars_file)
                funding.to_frame().to_parquet(funding_file)
                result[symbol] = (bars, funding)
            log.info(
                "research_binance_fetched", symbol=symbol, bars=len(bars), payments=len(funding)
            )
    return result


def load_positions(
    contracts: list[cftc.Contract], source: PublicReader | None, store: Path = POSITIONS_STORE
) -> dict[str, pd.DataFrame]:
    """The weekly positioning reports of each contract, from file when there is one."""
    store.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    for contract in contracts:
        target = store / f"{contract.code}.parquet"
        if target.exists():
            result[contract.name] = pd.read_parquet(target)
        elif source is not None:
            frame = cftc.positions(source, contract)
            if len(frame):
                frame.to_parquet(target)
                result[contract.name] = frame
            log.info("research_positions_fetched", contract=contract.name, weeks=len(frame))
    return result
