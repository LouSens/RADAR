"""Hours from a second source: read once, stored once, and used for a day's movement."""

from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.ingest.upsert import upsert_bars
from radar.pipelines import outside_hours
from radar.pipelines.datasets import build_realised_volatility
from radar.providers import binance_public
from radar.providers.public import PublicReader
from radar.universe import Asset, load_universe

START = datetime(2026, 1, 1, tzinfo=UTC)
HOUR_MS = 3_600_000


def kline(opened: datetime, close: float) -> list[Any]:
    ms = int(opened.timestamp() * 1000)
    text = str(close)
    return [ms, text, text, text, text, "10", ms + HOUR_MS - 1, "0", 5, "4", "0", "0"]


def source(prices: pd.Series, calls: list[dict[str, str]]) -> PublicReader:
    """A reader that answers the bars request from `prices` and records what was asked."""

    def handle(request: httpx.Request) -> httpx.Response:
        asked = dict(request.url.params)
        calls.append({"host": request.url.host, "path": request.url.path, **asked})
        first, last = int(asked["startTime"]), int(asked["endTime"])
        rows = [
            kline(stamp.to_pydatetime(), price)
            for stamp, price in zip(pd.DatetimeIndex(prices.index), prices, strict=True)
            if first <= int(stamp.timestamp() * 1000) <= last
        ]
        return httpx.Response(200, json=rows[: int(asked["limit"])])

    return PublicReader(
        binance_public.ALLOWED, transport=httpx.MockTransport(handle), sleep=lambda _: None
    )


def gold() -> Asset:
    return load_universe().get("PAXG/USD")


def hours(days: int, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.date_range(START, periods=days * 24, freq="h")
    return pd.Series(2000 * np.exp(np.cumsum(rng.normal(0, 0.002, len(index)))), index=index)


def test_gold_names_binance_for_its_hours_and_only_a_coin_may() -> None:
    universe = load_universe()
    assert gold().hours_from == "PAXGUSDT"
    assert [a.symbol for a in universe.assets if a.hours_from] == ["PAXG/USD"]
    with pytest.raises(ValueError, match="crypto assets only"):
        Asset.model_validate({**universe.get("SPY").model_dump(), "hours_from": "SPYUSDT"})


def test_reading_twice_stores_the_same_rows_and_asks_only_for_what_is_new(
    session: Session,
) -> None:
    sync_assets(session, load_universe())
    prices = hours(3)
    calls: list[dict[str, str]] = []
    reader = source(prices, calls)
    noon = datetime(2026, 1, 2, 12, tzinfo=UTC)

    assert outside_hours.sync(session, gold(), reader, noon) == 36
    assert outside_hours.sync(session, gold(), reader, noon) == 0  # nothing new, nothing changed
    stored = outside_hours.hourly_close(session, gold())
    assert len(stored) == 36
    assert stored.index[-1] == pd.Timestamp("2026-01-02 11:00", tz="UTC")  # finished hours only
    pd.testing.assert_series_equal(stored, prices.iloc[:36], check_names=False, check_freq=False)

    # Later, only the hours since the newest stored one are asked for.
    calls.clear()
    assert outside_hours.sync(session, gold(), reader, datetime(2026, 1, 3, tzinfo=UTC)) == 12
    assert int(calls[0]["startTime"]) == int(stored.index[-1].timestamp() * 1000)
    # Every request went to the one agreed public endpoint, as a read.
    assert {(c["host"], c["path"]) for c in calls} == {binance_public.BARS}
    assert {c["symbol"] for c in calls} == {"PAXGUSDT"}


def test_a_days_movement_is_measured_on_the_outside_hours_when_there_are_any(
    session: Session,
) -> None:
    universe = load_universe()
    sync_assets(session, universe)
    asset, prices = gold(), hours(4)
    # The asset's own hours: every third one is missing, so no day has enough of them.
    own = prices[np.arange(len(prices)) % 3 != 0]
    upsert_bars(
        session,
        [
            {
                "symbol": asset.symbol,
                "timeframe": "1Hour",
                "loc": universe.crypto_location,
                "ts": stamp.to_pydatetime(),
                **{name: float(price) for name in ("open", "high", "low", "close", "vwap")},
                "volume": 1.0,
                "trade_count": 1,
                "is_quote_only": False,
            }
            for stamp, price in zip(pd.DatetimeIndex(own.index), own, strict=True)
        ],
    )
    before = build_realised_volatility(session, asset)
    assert before["flagged"].all()  # too few hours in every day

    outside_hours.upsert(session, asset, pd.DataFrame(dict.fromkeys(outside_hours.VALUES, prices)))
    after = build_realised_volatility(session, asset)
    assert not after["flagged"].iloc[1:].any()
    expected = float(np.sqrt((np.log(prices).diff().iloc[24:48] ** 2).sum()))
    assert after["rv"].iloc[1] == pytest.approx(expected)
