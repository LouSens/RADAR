"""Binance's public market data, read without a key (decision 067).

Three reads only: hourly bars, which carry the volume bought by takers as well as the
total; the funding rate paid every 8 hours on a perpetual contract; and the list of
pairs the exchange trades, which is how every coin an account may have traded is found
(decision 076). Nothing here can
see an account; the signed reader for holdings is `binance.py` and stays separate.
"""

import pandas as pd

from radar.providers.public import PublicReader

SPOT_HOST = "api.binance.com"
FUTURES_HOST = "fapi.binance.com"
BARS = (SPOT_HOST, "/api/v3/klines")
FUNDING = (FUTURES_HOST, "/fapi/v1/fundingRate")
# Every pair the exchange lists. Market information only; nothing about any account.
PAIRS = (SPOT_HOST, "/api/v3/exchangeInfo")
ALLOWED = frozenset({BARS, FUNDING, PAIRS})
PAGE = 1000
HOUR_MS = 3_600_000
BAR_FIELDS = ["open", "high", "low", "close", "volume", "taker_buy"]


def reader() -> PublicReader:
    return PublicReader(ALLOWED)


def bars_frame(rows: list[list[str | int]]) -> pd.DataFrame:
    """Hourly bars indexed by their opening time (UTC). `taker_buy` is the part of
    `volume` that was bought by the side crossing the spread."""
    frame = pd.DataFrame(
        [
            [float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9])]
            for r in rows
        ],
        columns=BAR_FIELDS,
        index=pd.to_datetime([int(r[0]) for r in rows], unit="ms", utc=True),
    )
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def hourly_bars(source: PublicReader, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Every completed hourly bar that opened in [start, end)."""
    rows: list[list[str | int]] = []
    cursor = start_ms
    while cursor < end_ms:
        page = source.get(
            *BARS,
            {
                "symbol": symbol,
                "interval": "1h",
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": PAGE,
            },
        )
        if not page:
            break
        rows.extend(page)
        cursor = int(page[-1][0]) + HOUR_MS
        if len(page) < PAGE:
            break
    return bars_frame(rows) if rows else pd.DataFrame(columns=BAR_FIELDS)


def funding_rates(source: PublicReader, symbol: str, start_ms: int, end_ms: int) -> pd.Series:
    """The funding rate at each payment time (UTC) in [start, end)."""
    stamps: list[int] = []
    rates: list[float] = []
    cursor = start_ms
    while cursor < end_ms:
        page = source.get(
            *FUNDING, {"symbol": symbol, "startTime": cursor, "endTime": end_ms - 1, "limit": PAGE}
        )
        if not page:
            break
        stamps.extend(int(row["fundingTime"]) for row in page)
        rates.extend(float(row["fundingRate"]) for row in page)
        cursor = int(page[-1]["fundingTime"]) + 1
        if len(page) < PAGE:
            break
    series = pd.Series(rates, index=pd.to_datetime(stamps, unit="ms", utc=True), name="funding")
    return series[~series.index.duplicated(keep="last")].sort_index()


def dollar_pairs(source: PublicReader, cash: tuple[str, ...]) -> dict[str, list[str]]:
    """Every coin the exchange lists against one of the `cash` currencies, with the
    currencies it is listed against, in the order given."""
    listed: dict[str, list[str]] = {}
    for pair in source.get(*PAIRS, {}).get("symbols", []):
        base, quote = str(pair.get("baseAsset", "")), str(pair.get("quoteAsset", ""))
        if base and quote in cash and base not in cash:
            listed.setdefault(base, []).append(quote)
    return {base: [c for c in cash if c in quotes] for base, quotes in sorted(listed.items())}
