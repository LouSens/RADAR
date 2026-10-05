"""API routes against the real test database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.db.assets import sync_assets
from radar.db.models import DataQualityReport
from radar.ingest.live import notify
from radar.ingest.upsert import bar_row, record_run, upsert_bars
from radar.providers import schemas
from radar.universe import Universe

HOUR = timedelta(hours=1)
UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "ETH/USD",
                "name": "Ethereum",
                "asset_class": "crypto",
                "bars_symbol": "ETH/USD",
                "history_start": "2021-01-01",
            },
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2021-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            },
            {
                "symbol": "GLD",
                "name": "Gold",
                "asset_class": "stock",
                "is_primary": True,
                "bars_symbol": "GLD",
                "history_start": "2016-01-04",
                "news_symbols": ["GLD"],
                "news_start": "2023-01-01",
            },
        ],
    }
)


def last_full_hour() -> datetime:
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - HOUR


def wire(ts: datetime, close: float, volume: float = 1.0) -> schemas.Bar:
    return schemas.Bar.model_validate(
        {
            "t": ts,
            "o": close,
            "h": close + 1,
            "l": close - 1,
            "c": close,
            "v": volume,
            "n": 1,
            "vw": close,
        }
    )


def seed(session: Session, *, btc_hours_ago: int = 0) -> datetime:
    """Ten hourly Bitcoin bars ending `btc_hours_ago` hours before the last full hour."""
    sync_assets(session, UNIVERSE)
    end = last_full_hour() - btc_hours_ago * HOUR
    rows = [
        bar_row("BTC/USD", "1Hour", "us-1", wire(end - (9 - i) * HOUR, 100.0 + i, volume=i % 2))
        for i in range(10)
    ]
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(today - timedelta(days=1), 105.0)))
    rows.append(bar_row("GLD", "1Day", "sip", wire(today - timedelta(days=1, hours=-5), 50.0)))
    upsert_bars(session, rows)
    session.commit()
    return end


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    with TestClient(create_app(engine, UNIVERSE)) as test_client:
        yield test_client


def test_assets_lists_the_universe_primary_first(client: TestClient) -> None:
    body = client.get("/api/v1/assets").json()
    assert [a["symbol"] for a in body] == ["BTC/USD", "GLD", "ETH/USD"]
    btc, gld = body[0], body[1]
    assert btc["slug"] == "btc-usd"
    assert btc["trades_continuously"] is True
    assert gld["trades_continuously"] is False
    assert gld["news_start"] == "2023-01-01"


@pytest.mark.parametrize("path", ["BTC/USD", "btc-usd", "BTC%2FUSD"])
def test_bars_accept_symbol_or_slug_and_return_utc_in_order(
    client: TestClient, session: Session, path: str
) -> None:
    end = seed(session)
    body = client.get(f"/api/v1/assets/{path}/bars", params={"limit": 3}).json()
    assert body["symbol"] == "BTC/USD"
    assert body["timeframe"] == "1Hour"
    assert body["source"] == "us-1"
    assert body["count"] == 3
    stamps = [datetime.fromisoformat(b["ts"]) for b in body["bars"]]
    assert stamps == [end - 2 * HOUR, end - HOUR, end]  # the latest three, oldest first
    assert all(s.utcoffset() == timedelta(0) for s in stamps)
    assert body["bars"][-1]["close"] == 109.0
    assert body["bars"][-1]["is_quote_only"] is False
    assert body["bars"][-2]["is_quote_only"] is True


def test_bars_window_and_timeframe(client: TestClient, session: Session) -> None:
    end = seed(session)
    start = (end - 5 * HOUR).isoformat()
    body = client.get("/api/v1/assets/btc-usd/bars", params={"start": start, "limit": 2}).json()
    assert [datetime.fromisoformat(b["ts"]) for b in body["bars"]] == [
        end - 5 * HOUR,
        end - 4 * HOUR,
    ]
    daily = client.get("/api/v1/assets/btc-usd/bars", params={"timeframe": "1Day"}).json()
    assert daily["count"] == 1
    assert (
        client.get("/api/v1/assets/gld/bars", params={"timeframe": "1Day"}).json()["source"]
        == "sip"
    )


def test_bars_reject_bad_requests(client: TestClient, session: Session) -> None:
    seed(session)
    assert client.get("/api/v1/assets/doge-usd/bars").status_code == 404
    assert client.get("/api/v1/assets/gld/bars", params={"timeframe": "1Hour"}).status_code == 404
    assert (
        client.get("/api/v1/assets/btc-usd/bars", params={"timeframe": "1Min"}).status_code == 422
    )
    assert client.get("/api/v1/assets/btc-usd/bars", params={"limit": 999_999}).status_code == 422
    naive = client.get("/api/v1/assets/btc-usd/bars", params={"start": "2024-01-01T00:00:00"})
    assert naive.status_code == 422  # timestamps must carry a zone


def test_health_is_ok_when_primary_series_are_fresh(
    client: TestClient, session: Session, engine: Engine
) -> None:
    seed(session)
    now = datetime.now(UTC)
    record_run(
        session,
        job="backfill",
        key="bars:BTC/USD:1Hour:us-1",
        window_start=now - HOUR,
        window_end=now,
        status="partial",
        rows=1,
        started_at=now,
    )
    session.add(
        DataQualityReport(
            symbol="BTC/USD", check="gaps:1Hour", status="ok", detail={"missing_share": 0.0005}
        )
    )
    session.commit()

    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["last_sync"] is not None
    assert body["quality"] == {**body["quality"], "findings": 1, "warnings": 0, "failures": 0}
    series = {(s["symbol"], s["timeframe"]): s for s in body["series"]}
    btc = series[("BTC/USD", "1Hour")]
    assert btc["bars"] == 10
    assert btc["stale"] is False
    assert 0 <= btc["lag_seconds"] < 3600
    assert btc["missing_share"] == 0.0005
    assert series[("GLD", "1Day")]["stale"] is False


def test_health_is_degraded_when_a_primary_series_is_stale(
    client: TestClient, session: Session
) -> None:
    seed(session, btc_hours_ago=10)
    body = client.get("/api/v1/health").json()
    assert body["status"] == "degraded"
    series = {(s["symbol"], s["timeframe"]): s for s in body["series"]}
    assert series[("BTC/USD", "1Hour")]["stale"] is True


def test_health_is_degraded_when_a_primary_series_is_missing(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()  # empty database
    assert body["status"] == "degraded"
    assert body["series"] == []


def test_stream_forwards_events_published_by_the_worker(client: TestClient, engine: Engine) -> None:
    hub = client.app.state.hub  # type: ignore[attr-defined]
    assert hub.listening.wait(timeout=5)
    with client.websocket_connect("/api/v1/stream") as websocket:
        assert websocket.receive_json() == {"type": "hello"}
        assert client.get("/api/v1/health").json()["stream_clients"] == 1
        event = {"type": "bar", "symbol": "BTC/USD", "ts": "2024-01-01T00:01:00Z", "close": 2.5}
        notify(engine, event)
        assert websocket.receive_json() == event


def test_openapi_documents_every_route_and_live_message(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/api/v1/assets",
        "/api/v1/assets/{symbol}/bars",
        "/api/v1/assets/{symbol}/regime",
        "/api/v1/health",
    }
    assert {"AssetOut", "BarsOut", "HealthOut", "LiveBar", "LiveNews"} <= set(
        schema["components"]["schemas"]
    )


def test_api_has_no_trading_routes(client: TestClient) -> None:
    paths = " ".join(client.get("/openapi.json").json()["paths"])
    for word in ("order", "position", "account", "transfer", "trade"):
        assert word not in paths
    assert client.post("/api/v1/assets").status_code == 405


def test_regime_route_serves_stored_readings(client: TestClient, session: Session) -> None:
    from radar.db.models import ModelRegistry, RegimeState

    seed(session)
    assert client.get("/api/v1/assets/btc-usd/regime").status_code == 404  # no model yet

    states = [
        {
            "label": label,
            "typical_daily_volatility": vol,
            "typical_duration_days": 30.0,
            "next_states": {"normal": 1.0}
            if label != "normal"
            else {"calm": 0.6, "turbulent": 0.4},
            "mean_daily_return": 0.0,
        }
        for label, vol in (("calm", 0.01), ("normal", 0.02), ("turbulent", 0.04))
    ]
    model = ModelRegistry(
        name="regime",
        symbol="BTC/USD",
        version="regime-hmm-1",
        train_start=datetime(2021, 1, 2, tzinfo=UTC).date(),
        train_end=datetime(2026, 10, 4, tzinfo=UTC).date(),
        is_current=True,
        params={"n_train": 2102},
        metrics={
            "states": states,
            "bic_by_states": {"2": 9743.0, "3": 8575.0, "4": 7687.0},
            "walk_forward": {
                "n_days": 1602,
                "n_refits": 26,
                "first_test_day": "2022-05-17",
                "last_test_day": "2026-10-04",
                "model_log_density": 2.017,
                "baseline_log_density": 1.972,
                "next_day_volatility": {"calm": 0.0196, "normal": 0.0271, "turbulent": 0.0363},
                "days_per_state": {"calm": 600, "normal": 600, "turbulent": 402},
                "volatility_is_ordered": True,
                "average_run_length": 34.1,
            },
        },
    )
    session.add(model)
    session.flush()
    day = datetime(2026, 10, 1, tzinfo=UTC)
    for i, label in enumerate(["normal", "calm", "calm", "calm"]):
        probs = {"calm": 0.05, "normal": 0.05, "turbulent": 0.0, label: 0.9}
        session.add(
            RegimeState(
                symbol="BTC/USD",
                model_id=model.id,
                ts=day + timedelta(days=i),
                label=label,
                probability=0.9,
                probs=probs,
            )
        )
    session.commit()

    body = client.get("/api/v1/assets/btc-usd/regime").json()
    assert body["label"] == "calm"
    assert body["days_in_state"] == 3
    assert body["probability"] == 0.9
    assert datetime.fromisoformat(body["as_of"]) == day + timedelta(days=3)
    assert [p["label"] for p in body["history"]] == ["normal", "calm", "calm", "calm"]
    assert [s["label"] for s in body["states"]] == ["calm", "normal", "turbulent"]
    assert body["evaluation"]["volatility_is_ordered"] is True
    assert body["evaluation"]["n_days"] == 1602
    assert body["model"]["n_train"] == 2102

    assert (
        len(client.get("/api/v1/assets/btc-usd/regime", params={"days": 2}).json()["history"]) == 2
    )
