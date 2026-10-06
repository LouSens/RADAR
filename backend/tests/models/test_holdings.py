"""Holdings sources: manual entry and CSV text."""

import inspect

import pytest

from radar.models import holdings
from radar.models.holdings import CsvSource, Holding, HoldingsSource, ManualSource, resolve

KNOWN = ["BTC/USD", "PAXG/USD", "GLD", "SPY"]


@pytest.mark.parametrize(
    ("typed", "symbol"),
    [
        ("BTC/USD", "BTC/USD"),
        ("btc", "BTC/USD"),
        (" btc-usd ", "BTC/USD"),
        ("BTCUSDT", "BTC/USD"),
        ("PAXG", "PAXG/USD"),
        ("spy", "SPY"),
        ("SPYB", "SPY"),
        ("gld", "GLD"),
        ("DOGE", None),
        ("USDT", "USD"),
        ("usdc", "USD"),
        ("cash", "USD"),
        ("EUR", None),
        ("", None),
    ],
)
def test_names_from_other_venues_resolve_to_stored_symbols(typed: str, symbol: str | None) -> None:
    assert resolve(typed, KNOWN) == symbol


def test_manual_entries_are_checked_and_repeats_added_up() -> None:
    source: HoldingsSource = ManualSource(
        [
            Holding(symbol="btc", quantity=0.5, tag="core"),
            Holding(symbol="BTC/USD", quantity=0.25),
            Holding(symbol="SPY", quantity=3),
            Holding(symbol="DOGE", quantity=100),
            Holding(symbol="GLD", quantity=0),
        ],
        KNOWN,
    )
    read = source.read()
    assert read.source == "manual"
    assert [(h.symbol, h.quantity, h.tag) for h in read.holdings] == [
        ("BTC/USD", 0.75, "core"),
        ("SPY", 3, None),
    ]
    assert [(u.symbol, u.reason) for u in read.unsupported] == [
        ("DOGE", "RADAR has no price history for this."),
        ("GLD", "The quantity must be greater than zero."),
    ]


def test_csv_accepts_common_column_names_and_ignores_the_rest() -> None:
    text = (
        "﻿Asset,Amount,Tag,Note\n"
        'BTC,"1,250.5",Core,cold wallet\n'
        "spy,4,satellite,\n"
        "PAXGUSDT,2,other,\n"
        "SHIB,1000,,\n"
        "GLD,lots,,\n"
        ",,,\n"
    )
    read = CsvSource(text, KNOWN).read()
    assert read.source == "csv"
    assert [(h.symbol, h.quantity, h.tag) for h in read.holdings] == [
        ("BTC/USD", 1250.5, "core"),
        ("SPY", 4, "satellite"),
        ("PAXG/USD", 2, None),
    ]
    assert [(u.symbol, u.reason) for u in read.unsupported] == [
        ("SHIB", "RADAR has no price history for this."),
        ("GLD", "The quantity is not a number."),
    ]


def test_csv_without_the_needed_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="symbol column and a quantity column"):
        CsvSource("name,price\nBTC,100\n", KNOWN).read()
    with pytest.raises(ValueError, match="more than"):
        CsvSource("symbol,quantity\n" + "BTC,1\n" * 501, KNOWN).read()


def test_a_source_can_only_be_read() -> None:
    """The interface has one method, and nothing here can reach an exchange."""
    methods = [
        name
        for name, _ in inspect.getmembers(HoldingsSource, inspect.isfunction)
        if not name.startswith("_")
    ]
    assert methods == ["read"]
    source = inspect.getsource(holdings)
    for word in ("httpx", "requests", "socket", "urllib"):
        assert f"import {word}" not in source


def test_dollars_and_dollar_stablecoins_add_up_to_one_cash_holding() -> None:
    read = CsvSource("symbol,quantity\nBTC,1\nUSDT,400\nUSDC,100.5\ncash,50\n", KNOWN).read()
    assert [(h.symbol, h.quantity) for h in read.holdings] == [("BTC/USD", 1), ("USD", 550.5)]
    assert read.unsupported == []
