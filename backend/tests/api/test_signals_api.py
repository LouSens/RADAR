"""Stored signals and their track records, through the store and the routes."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.db.assets import sync_assets
from radar.db.models import Signal, SignalTrackRecord
from radar.pipelines import signals as job
from radar.signals import track
from radar.universe import Universe


def asset(symbol: str, name: str, kind: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "name": name,
        "asset_class": kind,
        "bars_symbol": symbol,
        "history_start": "2022-01-01",
        "is_primary": True,
        "news_symbols": [symbol.replace("/", "")],
        "news_start": "2022-01-01",
    }


UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [asset("BTC/USD", "Bitcoin", "crypto"), asset("SPY", "US stocks", "stock")],
    }
)


def built() -> tuple[list[track.TrackRecord], list[dict[str, Any]]]:
    rng = np.random.default_rng(4)
    days = pd.date_range("2022-01-01", periods=401, tz="UTC")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 401))), index=days)
    horizons = [(1, "1 day"), (7, "1 week")]
    records = track.correct_family(
        [
            track.record("abnormal_move", "BTC/USD", "up", list(days[0:390:10]), close, horizons),
            track.record("regime_change", "SPY", "to calm", list(days[0:50:10]), close, horizons),
        ]
    )
    rows = [
        {
            "symbol": "BTC/USD",
            "ts": datetime(2024, 3, 1 + i, tzinfo=UTC),
            "type": "abnormal_move",
            "variant": "up",
            "payload": {"multiple": 3.5 + i},
        }
        for i in range(3)
    ] + [
        {
            "symbol": "SPY",
            "ts": datetime(2024, 3, 2, 20, tzinfo=UTC),
            "type": "regime_change",
            "variant": "to calm",
            "payload": {"from": "normal", "to": "calm", "probability": 0.9},
        }
    ]
    return records, rows


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    sync_assets(session, UNIVERSE)
    records, rows = built()
    job.store(session, records, rows)
    session.commit()
    with TestClient(create_app(engine, UNIVERSE)) as test_client:
        yield test_client


def test_storing_twice_stores_the_same_rows(client: TestClient, session: Session) -> None:
    before = [(s.id, s.symbol, s.ts, s.track_record_id) for s in session.scalars(select(Signal))]
    records, rows = built()
    assert job.store(session, records, rows) == 4
    session.commit()
    session.expire_all()
    after = [(s.id, s.symbol, s.ts, s.track_record_id) for s in session.scalars(select(Signal))]
    assert sorted(before) == sorted(after)
    assert session.scalar(select(func.count()).select_from(SignalTrackRecord)) == 2
    assert all(row[3] is not None for row in after)


def test_signals_come_newest_first_each_with_its_track_record(client: TestClient) -> None:
    body = client.get("/api/v1/signals").json()
    assert [(s["symbol"], s["ts"][:10]) for s in body["signals"]] == [
        ("BTC/USD", "2024-03-03"),
        ("SPY", "2024-03-02"),
        ("BTC/USD", "2024-03-02"),
        ("BTC/USD", "2024-03-01"),
    ]
    newest = body["signals"][0]
    assert (newest["name"], newest["type"], newest["variant"]) == ("Bitcoin", "abnormal_move", "up")
    assert newest["detail"] == {"multiple": 5.5}
    assert newest["record"]["n"] == 39
    assert newest["record"]["verdict"] == "no measurable edge"
    assert 0 <= newest["record"]["share_positive"] <= 1
    assert newest["record"]["baseline_mean_size"] > 0
    # Five occurrences are too few to judge, and the signal says so.
    assert body["signals"][1]["record"]["verdict"] == "not enough occurrences"
    # No portfolio is saved, so there are no portfolio signals.
    assert body["portfolio"] == []


def test_the_feed_can_be_narrowed(client: TestClient) -> None:
    stocks = client.get("/api/v1/signals", params={"symbol": "spy"}).json()["signals"]
    assert [s["symbol"] for s in stocks] == ["SPY"]
    moves = client.get("/api/v1/signals", params={"type": "abnormal_move", "limit": 2}).json()
    assert [s["ts"][:10] for s in moves["signals"]] == ["2024-03-03", "2024-03-02"]
    assert client.get("/api/v1/signals", params={"type": "tip"}).status_code == 422
    assert client.get("/api/v1/signals", params={"symbol": "NOPE"}).status_code == 404


def test_a_track_record_shows_what_followed_against_all_days(client: TestClient) -> None:
    body = client.get("/api/v1/signals/track-records/abnormal_move").json()
    assert body["type"] == "abnormal_move"
    # Two horizons of the one record with enough occurrences were tested together.
    assert body["tested"] == 2
    (record,) = body["records"]
    assert (record["symbol"], record["name"], record["variant"], record["n"]) == (
        "BTC/USD",
        "Bitcoin",
        "up",
        39,
    )
    day, week = record["horizons"]
    assert (day["label"], week["label"]) == ("1 day", "1 week")
    assert day["signal"]["n"] == 39
    assert day["baseline"]["n"] == 400
    assert (
        day["signal"]["share_low"] <= day["signal"]["share_positive"] <= day["signal"]["share_high"]
    )
    assert set(day["signal"]["quantiles"]) == {"0.05", "0.25", "0.5", "0.75", "0.95"}
    assert record["first_day"] == "2022-01-01"

    assert client.get("/api/v1/signals/track-records/sentiment_shock").json()["records"] == []
    assert client.get("/api/v1/signals/track-records/hot_tip").status_code == 404
