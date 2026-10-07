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
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.schemas import Bar

log = structlog.get_logger(__name__)

STORE = Path("data/research/daily")
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
