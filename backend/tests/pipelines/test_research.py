"""Research bars: shaped by day, cached in a file, and never fetched twice."""

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd

from radar.pipelines import research
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.schemas import Bar


def bar(stamp: str, close: float) -> Bar:
    return Bar.model_validate(
        {
            "t": stamp,
            "o": close,
            "h": close + 1,
            "l": close - 1,
            "c": close,
            "v": 10,
            "n": 1,
            "vw": close,
        }
    )


def test_stock_bars_are_indexed_by_session_and_crypto_bars_by_utc_day() -> None:
    stock = research.to_frame(
        [bar("2024-03-11T04:00:00Z", 5), bar("2024-03-12T04:00:00Z", 6)], False
    )
    assert list(stock.index) == [pd.Timestamp("2024-03-11"), pd.Timestamp("2024-03-12")]
    assert stock["close"].tolist() == [5.0, 6.0]
    crypto = research.to_frame([bar("2024-03-11T00:00:00Z", 5)], True)
    assert list(crypto.index) == [pd.Timestamp("2024-03-11")]
    assert research.is_crypto("ETH/USD")
    assert not research.is_crypto("QQQ")


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _page(self, symbol: str, hour: str) -> Iterator[Any]:
        self.calls.append(symbol)
        stamps = [f"2024-03-11T{hour}:00:00Z", f"2024-03-12T{hour}:00:00Z"]
        return iter([SimpleNamespace(bars={symbol: [bar(s, 5) for s in stamps]})])

    def iter_stock_bar_pages(self, symbols: Sequence[str], *_: Any, **__: Any) -> Iterator[Any]:
        return self._page(symbols[0], "04")

    def iter_crypto_bar_pages(self, symbols: Sequence[str], *_: Any, **__: Any) -> Iterator[Any]:
        return self._page(symbols[0], "00")


def test_a_market_is_fetched_once_then_read_from_its_file(tmp_path: Path) -> None:
    fake = FakeClient()
    client = cast(AlpacaDataClient, fake)
    now = datetime(2024, 3, 12, 12, tzinfo=UTC)
    first = research.load(["QQQ", "ETH/USD"], client, "us-1", tmp_path, now)
    assert fake.calls == ["QQQ", "ETH/USD"]
    assert len(first["QQQ"]) == 2
    # The newest crypto bar is the day still in progress and is left out.
    assert len(first["ETH/USD"]) == 1
    again = research.load(["QQQ", "ETH/USD"], None, "us-1", tmp_path, now)
    assert again["QQQ"].equals(first["QQQ"])
    assert fake.calls == ["QQQ", "ETH/USD"]
    # With no client and no file, a market is simply left out.
    assert research.load(["IWM"], None, "us-1", tmp_path, now) == {}
