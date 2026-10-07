"""The account record built from an invented history."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from radar.models.ledger import Entry, Kind
from radar.pipelines import account
from radar.providers.binance import BinanceError

START = datetime(2025, 1, 1, tzinfo=UTC)
NOW = START + timedelta(hours=1000)


def hour(n: int) -> datetime:
    return START + timedelta(hours=n, minutes=10)


def prices(asset: str, start: datetime, end: datetime) -> pd.DataFrame:
    close = 100 + 10 * np.sin(np.arange(1000) / 30)
    index = pd.date_range(START, periods=1000, freq="h", tz="UTC")
    return pd.DataFrame({"high": close + 0.1, "low": close - 0.1, "close": close}, index=index)


def entry(n: int, kind: Kind, units: float, dollars: float | None, asset: str = "SOL") -> Entry:
    return Entry(at=hour(n), asset=asset, kind=kind, units=units, dollars=dollars)


ENTRIES = [
    entry(200, "buy", 2.0, 200.0),
    entry(300, "sell", -2.0, 230.0),
    entry(400, "buy", 1.0, 105.0),
    entry(450, "reward", 0.01, None),
    entry(500, "buy", 50.0, 50.0, asset="USDT"),
]


def test_the_record_adds_up_what_was_paid_made_and_left() -> None:
    record = account.build(ENTRIES, prices, {"SOL": 1.0}, NOW)

    assert [a.asset for a in record.assets] == ["SOL"]  # cash is not a holding
    sol = record.assets[0]
    assert sol.standing.realised == pytest.approx(30)
    assert sol.standing.units == pytest.approx(1.01)
    assert sol.standing.average_cost == pytest.approx(105 / 1.01)
    last = float(prices("SOL", START, NOW)["close"].iloc[-1])
    assert sol.price == pytest.approx(last)
    assert sol.unrealised == pytest.approx((last - 105 / 1.01) * 1.01)
    assert sol.trips is not None
    assert (sol.trips.count, sol.trips.ended_up, sol.trips.total) == (1, 1, 30)
    # The first 200 was new money; the 105 came out of the 230 from the sale.
    assert sol.compared is not None
    assert sol.compared.put_in == 200
    assert sol.compared.as_traded == pytest.approx(1.0 * last + 125)
    assert sol.missing_share == pytest.approx(0.01)
    assert record.trades == 3
    assert record.realised == pytest.approx(30)
    assert record.first_trade == hour(200)
    assert [(m.month, m.trades, m.bought, m.sold) for m in record.months] == [
        ("2025-01", 3, 305.0, 230.0)
    ]


def test_each_trade_is_set_beside_the_prices_around_it() -> None:
    record = account.build(ENTRIES, prices, {}, NOW)
    sol = record.assets[0]
    assert sol.buys is not None
    assert sol.sells is not None
    assert sol.usual is not None
    assert (sol.buys.trades, sol.sells.trades) == (2, 1)
    assert 0 <= sol.buys.place <= 1
    assert sol.held_units is None
    assert sol.missing_share is None
    assert not sol.buys_unusual  # two trades are too few to say anything


def test_a_market_without_prices_still_gets_its_cost_and_gain() -> None:
    def none(asset: str, start: datetime, end: datetime) -> pd.DataFrame:
        raise RuntimeError("no such market")

    record = account.build(ENTRIES, none, {}, NOW)
    sol = record.assets[0]
    assert sol.standing.realised == pytest.approx(30)
    assert (sol.price, sol.value, sol.unrealised, sol.compared, sol.buys) == (None,) * 5


class FakeHistory:
    """Answers like the reader, from a few invented rows."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def conversions(self, start: datetime, end: datetime) -> list[Any]:
        if start <= hour(100) < end:
            return [
                SimpleNamespace(
                    at=hour(100),
                    from_asset="USDT",
                    from_quantity=50.0,
                    to_asset="PURR",
                    to_quantity=5.0,
                )
            ]
        return []

    def movements(self, start: datetime, end: datetime) -> list[Any]:
        return []

    def rewards(self, start: datetime, end: datetime) -> list[Any]:
        return []

    def fills(self, pair: str) -> list[Any]:
        self.asked.append(pair)
        if pair == "SOLUSDT":
            return [
                SimpleNamespace(
                    pair=pair,
                    at=hour(50),
                    bought=True,
                    quantity=1.0,
                    amount=100.0,
                    fee=0.1,
                    fee_asset="USDT",
                )
            ]
        if pair.startswith("PURR"):
            raise BinanceError("Binance answered 400: Invalid symbol.")
        return []


def test_collecting_follows_the_accounts_own_swaps_to_find_what_to_ask_for() -> None:
    history = FakeHistory()
    entries = account.collect(history, ["SOL"], NOW)  # type: ignore[arg-type]

    assert [(e.asset, e.kind, e.units, e.dollars) for e in entries] == [
        ("SOL", "buy", 1.0, 100.1),
        ("PURR", "buy", 5.0, 50.0),
    ]
    # The swap named an asset nobody listed; a pair that does not exist is passed over.
    assert "PURRUSDT" in history.asked
    assert "SOLUSDT" in history.asked
    assert not any(pair.startswith(("USDT", "USDC")) for pair in history.asked)
