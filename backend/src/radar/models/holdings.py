"""Where holdings come from (spec F6). Pure: no database and no network here.

Every way of supplying holdings is a `HoldingsSource`: something that can be read and
gives back what it could use and what it could not. Manual entry and a CSV file are
here. A read-only exchange connection is a third source with the same interface; it
lives with the other provider clients because it makes network calls.

A source only ever reads. Nothing in this interface can place, change, or cancel an
order, or move funds.
"""

import csv
import io
import math
from collections.abc import Iterable, Mapping
from typing import Literal, Protocol

from pydantic import BaseModel

Tag = Literal["core", "satellite"]
SourceName = Literal["manual", "csv", "binance"]

# Names other venues use for assets RADAR stores under its own symbol.
ALIASES: Mapping[str, str] = {"SPYB": "SPY", "XBT": "BTC/USD"}
QUOTES = ("USDT", "USDC", "USD")
# Cash is a holding like any other: it is part of the money and carries no price risk.
# Dollar stablecoins are counted as dollars, one for one.
CASH = "USD"
NO_HISTORY = "RADAR has no price history for this."
CASH_NAME = "Cash (US dollars)"
CASH_NAMES = frozenset({"USD", "CASH", "USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI"})
SYMBOL_COLUMNS = ("symbol", "asset", "ticker", "coin")
QUANTITY_COLUMNS = ("quantity", "amount", "qty", "units", "balance")
MAX_ROWS = 500


class Holding(BaseModel):
    symbol: str
    quantity: float
    tag: Tag | None = None


class Unsupported(BaseModel):
    """Something the source held that RADAR cannot use, and why."""

    symbol: str
    reason: str


class Holdings(BaseModel):
    source: SourceName
    holdings: list[Holding]
    unsupported: list[Unsupported]


class HoldingsSource(Protocol):
    """Anything holdings can be read from."""

    name: SourceName

    def read(self) -> Holdings: ...


def resolve(raw: str, known: Iterable[str]) -> str | None:
    """RADAR's symbol for a name as typed or exported, or None when there is none.

    "btc", "BTC/USD", "BTCUSDT", and "BTC-USD" all mean `BTC/USD`. A dollar or a dollar
    stablecoin on its own is cash.
    """
    symbols = set(known)
    name = raw.strip().upper().replace("-", "/").replace("_", "/")
    # Binance names a tokenised US stock `EQ_` plus its ticker. Such a name can only be
    # that stock: it is never matched to a crypto pair that happens to share the letters.
    if name.startswith("EQ/"):
        return name[3:] if name[3:] in symbols else None
    if name in CASH_NAMES:
        return CASH
    if name in ALIASES:
        name = ALIASES[name]
    if name in symbols:
        return name
    base = name.split("/")[0]
    if "/" not in name:
        for quote in QUOTES:
            if name.endswith(quote) and len(name) > len(quote):
                base = name[: -len(quote)]
                break
    base = ALIASES.get(base, base)
    for candidate in (base, f"{base}/USD"):
        if candidate in symbols:
            return candidate
    return None


def _collect(
    source: SourceName,
    rows: Iterable[tuple[str, object, object]],
    known: Iterable[str],
) -> Holdings:
    """Resolve symbols, check quantities, and add up repeated symbols."""
    symbols = list(known)
    totals: dict[str, Holding] = {}
    unsupported: list[Unsupported] = []
    for raw_symbol, raw_quantity, raw_tag in rows:
        label = str(raw_symbol).strip()
        if not label:
            continue
        try:
            quantity = float(str(raw_quantity).replace(",", "").strip())
        except ValueError:
            unsupported.append(Unsupported(symbol=label, reason="The quantity is not a number."))
            continue
        if not math.isfinite(quantity) or quantity <= 0:
            unsupported.append(
                Unsupported(symbol=label, reason="The quantity must be greater than zero.")
            )
            continue
        symbol = resolve(label, symbols)
        if symbol is None:
            unsupported.append(Unsupported(symbol=label, reason=NO_HISTORY))
            continue
        tag = str(raw_tag).strip().lower() if raw_tag is not None else ""
        chosen: Tag | None = (
            "core" if tag == "core" else "satellite" if tag == "satellite" else None
        )
        if symbol in totals:
            before = totals[symbol]
            totals[symbol] = Holding(
                symbol=symbol, quantity=before.quantity + quantity, tag=before.tag or chosen
            )
        else:
            totals[symbol] = Holding(symbol=symbol, quantity=quantity, tag=chosen)
    return Holdings(source=source, holdings=list(totals.values()), unsupported=unsupported)


class ManualSource:
    """Holdings typed in by the user."""

    name: SourceName = "manual"

    def __init__(self, entries: Iterable[Holding], known: Iterable[str]) -> None:
        self._entries = list(entries)
        self._known = list(known)

    def read(self) -> Holdings:
        return _collect(
            self.name, ((e.symbol, e.quantity, e.tag) for e in self._entries), self._known
        )


class CsvSource:
    """Holdings from the text of a CSV file.

    The first row names the columns. One must be the asset (`symbol`, `asset`, `ticker`,
    or `coin`) and one the amount held (`quantity`, `amount`, `qty`, `units`, or
    `balance`). A `tag` column of `core` or `satellite` is optional. Other columns are
    ignored.
    """

    name: SourceName = "csv"

    def __init__(self, text: str, known: Iterable[str]) -> None:
        self._text = text
        self._known = list(known)

    def read(self) -> Holdings:
        reader = csv.DictReader(io.StringIO(self._text.lstrip("﻿")))
        columns = {(name or "").strip().lower(): name for name in reader.fieldnames or []}
        symbol_column = next((columns[c] for c in SYMBOL_COLUMNS if c in columns), None)
        quantity_column = next((columns[c] for c in QUANTITY_COLUMNS if c in columns), None)
        if symbol_column is None or quantity_column is None:
            raise ValueError(
                "The file needs a header row with a symbol column and a quantity column."
            )
        tag_column = columns.get("tag")
        rows: list[tuple[str, object, object]] = []
        for number, row in enumerate(reader):
            if number >= MAX_ROWS:
                raise ValueError(f"The file has more than {MAX_ROWS} rows.")
            rows.append(
                (
                    row.get(symbol_column) or "",
                    row.get(quantity_column) or "",
                    row.get(tag_column) if tag_column else None,
                )
            )
        return _collect(self.name, rows, self._known)
