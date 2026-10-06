"""The relationships job and its routes against the real test database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.db.assets import sync_assets
from radar.db.models import ModelRegistry, RegimeState
from radar.features.calendars import nyse_schedule
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import relationships as job
from radar.providers import schemas
from radar.universe import Universe


def asset(symbol: str, name: str, kind: str, primary: bool = False) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": symbol,
        "name": name,
        "asset_class": kind,
        "bars_symbol": symbol,
        "history_start": "2022-01-01",
    }
    if primary:
        base |= {
            "is_primary": True,
            "news_symbols": [symbol.replace("/", "")],
            "news_start": "2022-01-01",
        }
    return base


UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [
            asset("BTC/USD", "Bitcoin", "crypto", primary=True),
            asset("SPY", "US stocks", "stock", primary=True),
            asset("UUP", "US dollar", "stock"),
            asset("VIXY", "Expected stock market volatility", "stock"),
        ],
    }
)
FIRST = pd.Timestamp("2022-01-03", tz="UTC")
LAST = pd.Timestamp("2024-06-28", tz="UTC")


def wire(ts: datetime, open_: float, close: float) -> schemas.Bar:
    return schemas.Bar.model_validate(
        {"t": ts, "o": open_, "h": close, "l": close, "c": close, "v": 1, "n": 1, "vw": close}
    )


def seed(session: Session) -> None:
    """Stocks follow Bitcoin loosely and open each session where Bitcoin's move since the
    last close points; the dollar moves on its own."""
    sync_assets(session, UNIVERSE)
    schedule = nyse_schedule(FIRST, LAST)
    rng = np.random.default_rng(4)
    n = len(schedule)
    btc_close_move = rng.normal(0, 0.03, n)
    btc_overnight = rng.normal(0, 0.02, n)
    btc_at_open = 40_000 * np.exp(np.cumsum(btc_close_move + btc_overnight) - btc_close_move)
    btc_at_close = 40_000 * np.exp(np.cumsum(btc_close_move + btc_overnight))
    spy_gap = 0.1 * btc_overnight + rng.normal(0, 0.001, n)
    spy_day = 0.2 * btc_close_move + rng.normal(0, 0.006, n)
    spy_close = 400 * np.exp(np.cumsum(spy_gap + spy_day))
    spy_open = spy_close / np.exp(spy_day)
    uup = 28 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    vixy = 20 * np.exp(np.cumsum(-2.5 * (spy_gap + spy_day) + rng.normal(0, 0.01, n)))
    rows = []
    for i, day in enumerate(schedule.index):
        midnight = day.tz_localize("America/New_York").tz_convert(UTC).to_pydatetime()
        rows.append(bar_row("SPY", "1Day", "iex", wire(midnight, spy_open[i], spy_close[i])))
        rows.append(bar_row("UUP", "1Day", "iex", wire(midnight, uup[i], uup[i])))
        rows.append(bar_row("VIXY", "1Day", "iex", wire(midnight, vixy[i], vixy[i])))
        before_open = (schedule["open"].iloc[i] - timedelta(hours=1, minutes=30)).to_pydatetime()
        before_close = (schedule["close"].iloc[i] - timedelta(hours=1)).to_pydatetime()
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(before_open, 1, btc_at_open[i])))
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(before_close, 1, btc_at_close[i])))
    upsert_bars(session, rows)

    # A regime model for Bitcoin that turned turbulent every 25 sessions.
    model = ModelRegistry(
        name="regime",
        symbol="BTC/USD",
        version="test",
        train_start=FIRST.date(),
        train_end=LAST.date(),
        is_current=True,
        params={},
        metrics={},
    )
    session.add(model)
    session.flush()
    session.add_all(
        RegimeState(
            symbol="BTC/USD",
            model_id=model.id,
            ts=schedule["close"].iloc[i].to_pydatetime() - timedelta(hours=2),
            label="turbulent" if i % 25 < 3 else "calm",
            probability=0.9,
            probs={},
        )
        for i in range(n)
    )
    session.commit()


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    seed(session)
    with TestClient(create_app(engine, UNIVERSE)) as test_client:
        yield test_client


def test_nothing_is_served_before_the_job_has_run(client: TestClient) -> None:
    assert client.get("/api/v1/relationships").status_code == 404
    assert client.get("/api/v1/assets/spy/drivers").status_code == 404
    assert client.get("/api/v1/assets/nope/drivers").status_code == 404


def test_the_job_stores_results_the_routes_serve(
    client: TestClient, engine: Engine, session: Session
) -> None:
    assert job.run(engine, UNIVERSE) == 3  # relationships, and drivers for two markets
    body = client.get("/api/v1/relationships").json()

    (pair,) = body["pairs"]
    assert (pair["a"], pair["b"], pair["regime_of"]) == ("BTC/USD", "SPY", "BTC/USD")
    assert pair["n_days"] > 600
    assert 0.3 < pair["full"] < 0.9
    assert pair["low_90"] < pair["current_90"] < pair["high_90"]
    assert len(pair["series"]) == 500
    assert pair["series"][-1]["rolling_90"] == pytest.approx(pair["current_90"])
    regimes = {r["label"]: r for r in pair["by_regime"]}
    assert set(regimes) == {"calm", "turbulent"}
    assert regimes["calm"]["n"] + regimes["turbulent"]["n"] == pair["n_days"]
    assert pair["trust"]["grade"] == "fair"  # under three years

    assert len(body["grid_full"]["symbols"]) == 4
    assert len(body["grid_full"]["matrix"]) == 4
    assert body["grid_recent"]["n_days"] == 90

    spills = {(s["source"], s["target"], s["steps"]): s for s in body["spillovers"]}
    assert set(spills) == {
        (a, b, k) for a, b in [("BTC/USD", "SPY"), ("SPY", "BTC/USD")] for k in (1, 5, 10)
    }
    assert spills[("BTC/USD", "SPY", 5)]["episodes"] >= 20
    assert spills[("BTC/USD", "SPY", 5)]["verdict"] in {"spills over", "no measurable spillover"}
    # Stocks have no regime model here, so nothing is claimed for them as a source.
    assert spills[("SPY", "BTC/USD", 5)]["episodes"] == 0
    assert spills[("SPY", "BTC/USD", 5)]["verdict"] == "not enough episodes"
    assert body["spillover_trust"]["grade"] == "rough"

    (weekend,) = body["weekends"]
    assert weekend["symbol"] == "SPY"
    assert weekend["weekends"] > 100
    assert weekend["slope"] == pytest.approx(0.1, abs=0.02)
    assert weekend["verdict"] == "moves with"
    assert body["weekend_trust"]["grade"] == "solid"

    drivers = client.get("/api/v1/assets/btc-usd/drivers").json()
    assert drivers["symbol"] == "BTC/USD"
    assert set(drivers["names"]) == {"SPY", "UUP", "VIXY"}
    assert [w["window"] for w in drivers["windows"]] == [90, 250]
    assert all(w["baseline"] == "SPY" for w in drivers["windows"])
    for reading in drivers["windows"][1]["drivers"]:
        assert reading["low"] <= reading["coefficient"] <= reading["high"]
    assert drivers["trust"]["grade"] in {"solid", "fair", "rough"}

    stocks = client.get("/api/v1/assets/spy/drivers").json()
    assert set(stocks["names"]) == {"UUP", "VIXY"}  # a market is never its own driver
    assert stocks["windows"][0]["baseline"] == "VIXY"
    vixy = next(d for d in stocks["windows"][1]["drivers"] if d["symbol"] == "VIXY")
    assert vixy["verdict"] == "moves against"

    # Running again replaces the current rows instead of adding more current ones.
    assert job.run(engine, UNIVERSE) == 3
    current = session.scalar(
        select(func.count())
        .select_from(ModelRegistry)
        .where(ModelRegistry.name.in_([job.NAME, job.DRIVERS_NAME]), ModelRegistry.is_current)
    )
    assert current == 3
    assert client.get("/api/v1/relationships").json()["pairs"][0]["full"] == pair["full"]
