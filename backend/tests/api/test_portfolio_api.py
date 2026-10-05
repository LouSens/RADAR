"""Portfolio routes and the analysis job against the real test database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.api.portfolio import get_binance_reader
from radar.db.assets import sync_assets
from radar.db.models import PortfolioAnalysis, PortfolioHolding
from radar.features.calendars import nyse_schedule
from radar.ingest.upsert import bar_row, upsert_bars
from radar.models.holdings import Holding, Holdings, Unsupported
from radar.pipelines import portfolio as job
from radar.providers import schemas
from radar.providers.binance import BinanceError, BinanceReading, Leveraged
from radar.universe import Universe

UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2022-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            },
            {
                "symbol": "GLD",
                "name": "Gold",
                "asset_class": "stock",
                "bars_symbol": "GLD",
                "history_start": "2022-01-01",
            },
            {
                "symbol": "SOL/USD",
                "name": "Solana",
                "asset_class": "crypto",
                "bars_symbol": "SOL/USD",
                "history_start": "2024-01-01",
            },
        ],
        "stress_episodes": [
            {"name": "Spring 2022", "start": "2022-05-04", "end": "2022-06-17"},
            {"name": "Long ago", "start": "2019-01-02", "end": "2019-02-01"},
        ],
    }
)
FIRST = pd.Timestamp("2022-01-03", tz="UTC")
LAST = pd.Timestamp("2024-06-28", tz="UTC")


def wire(ts: datetime, price: float) -> schemas.Bar:
    return schemas.Bar.model_validate(
        {"t": ts, "o": price, "h": price, "l": price, "c": price, "v": 1, "n": 1, "vw": price}
    )


def seed(session: Session) -> None:
    """Two and a half years of sessions. Bitcoin swings eight times as much as gold;
    Solana has only the last sixty sessions."""
    sync_assets(session, UNIVERSE)
    schedule = nyse_schedule(FIRST, LAST)
    rng = np.random.default_rng(1)
    n = len(schedule)
    btc = 40_000 * np.exp(np.cumsum(rng.normal(0, 0.04, n)))
    gld = 180 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    sol = 100 * np.exp(np.cumsum(rng.normal(0, 0.05, n)))
    rows = []
    for i, (day, close) in enumerate(zip(schedule.index, schedule["close"], strict=True)):
        midnight = day.tz_localize("America/New_York").tz_convert(UTC).to_pydatetime()
        rows.append(bar_row("GLD", "1Day", "iex", wire(midnight, float(gld[i]))))
        bar_start = (close - timedelta(hours=1)).to_pydatetime()
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(bar_start, float(btc[i]))))
        if i >= n - 60:
            rows.append(bar_row("SOL/USD", "1Hour", "us-1", wire(bar_start, float(sol[i]))))
    upsert_bars(session, rows)
    session.commit()


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    seed(session)
    app = create_app(engine, UNIVERSE)
    # Tests never read a real key from this machine's .env.
    app.dependency_overrides[get_binance_reader] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


def test_an_empty_portfolio_lists_what_can_be_held(client: TestClient) -> None:
    body = client.get("/api/v1/portfolio").json()
    assert body["source"] is None
    assert body["holdings"] == []
    assert [a["symbol"] for a in body["supported"]] == ["BTC/USD", "GLD", "SOL/USD"]
    assert client.get("/api/v1/portfolio/analysis").status_code == 404


def test_saving_holdings_stores_them_and_their_analysis(
    client: TestClient, session: Session
) -> None:
    saved = client.put(
        "/api/v1/portfolio",
        json={
            "holdings": [
                {"symbol": "btc", "quantity": 0.05, "tag": "satellite"},
                {"symbol": "GLD", "quantity": 40, "tag": "core"},
                {"symbol": "DOGE", "quantity": 5},
            ]
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["source"] == "manual"
    assert [(h["symbol"], h["quantity"], h["tag"]) for h in body["holdings"]] == [
        ("BTC/USD", 0.05, "satellite"),
        ("GLD", 40, "core"),
    ]
    assert [u["symbol"] for u in body["unsupported"]] == ["DOGE"]
    assert body["problem"] is None
    assert session.scalar(select(func.count()).select_from(PortfolioHolding)) == 2
    assert client.get("/api/v1/portfolio").json()["holdings"] == body["holdings"]

    analysis = client.get("/api/v1/portfolio/analysis").json()
    positions = {p["symbol"]: p for p in analysis["positions"]}
    assert analysis["value"] == pytest.approx(sum(p["value"] for p in positions.values()))
    assert sum(p["weight"] for p in positions.values()) == pytest.approx(1.0)
    assert positions["GLD"]["name"] == "Gold"
    assert positions["GLD"]["value"] == pytest.approx(40 * positions["GLD"]["price"])

    xray = analysis["xray"]
    shares = {h["symbol"]: h["risk_share"] for h in xray["holdings"]}
    assert sum(shares.values()) == pytest.approx(1.0)
    # Bitcoin is the smaller holding by value here only if its share of risk is larger.
    assert shares["BTC/USD"] > positions["BTC/USD"]["weight"]
    assert xray["n_days"] > 600
    assert xray["deepest_fall"]["depth"] < 0

    day, week = analysis["limits"]
    assert (day["horizon_days"], day["steps"]) == (1, 1)
    assert (week["horizon_days"], week["steps"]) == (7, 5)
    assert day["shown"] in {"historical", "filtered"}
    shown = next(m for m in day["levels"][0]["methods"] if m["method"] == day["shown"])
    assert 0 < shown["var"] <= shown["expected_shortfall"]
    assert shown["backtest"]["n"] > 100

    spring, long_ago = analysis["stress"]
    assert spring["available"]
    assert spring["missing"] == []
    assert sum(p["contribution"] for p in spring["parts"]) == pytest.approx(spring["change"])
    assert not long_ago["available"]
    assert long_ago["missing"] == ["BTC/USD", "GLD"]

    trust = analysis["trust"]
    assert trust["xray"]["grade"] == "fair"  # under three years of shared sessions
    assert trust["risk"]["grade"] in {"solid", "fair", "rough"}
    assert trust["stress"]["grade"] == "fair"  # one episode of two has prices
    assert "1 of 2 episodes" in trust["stress"]["reason"]


def test_csv_text_replaces_the_holdings(client: TestClient) -> None:
    client.put("/api/v1/portfolio", json={"holdings": [{"symbol": "GLD", "quantity": 1}]})
    body = client.post(
        "/api/v1/portfolio/import", json={"csv": "symbol,quantity\nBTC,0.5\nXRP,10\n"}
    ).json()
    assert body["source"] == "csv"
    assert [h["symbol"] for h in body["holdings"]] == ["BTC/USD"]
    assert [u["symbol"] for u in body["unsupported"]] == ["XRP"]
    assert client.get("/api/v1/portfolio/analysis").json()["positions"][0]["weight"] == 1.0

    refused = client.post("/api/v1/portfolio/import", json={"csv": "a,b\n1,2\n"})
    assert refused.status_code == 422
    assert "header row" in refused.json()["detail"]
    # A refused file leaves the holdings as they were.
    assert [h["symbol"] for h in client.get("/api/v1/portfolio").json()["holdings"]] == ["BTC/USD"]


def test_too_little_shared_history_is_said_not_guessed(
    client: TestClient, session: Session
) -> None:
    body = client.put(
        "/api/v1/portfolio",
        json={"holdings": [{"symbol": "SOL", "quantity": 3}, {"symbol": "GLD", "quantity": 1}]},
    ).json()
    assert "250 are needed" in body["problem"]
    assert client.get("/api/v1/portfolio/analysis").status_code == 404
    assert client.get("/api/v1/portfolio").json()["problem"] is not None


def test_clearing_the_holdings_clears_the_analysis(client: TestClient, session: Session) -> None:
    client.put("/api/v1/portfolio", json={"holdings": [{"symbol": "GLD", "quantity": 1}]})
    assert session.scalar(select(func.count()).select_from(PortfolioAnalysis)) == 1
    cleared = client.put("/api/v1/portfolio", json={"holdings": []}).json()
    assert cleared["holdings"] == []
    assert cleared["problem"] is None
    assert client.get("/api/v1/portfolio/analysis").status_code == 404


def test_the_job_refreshes_the_stored_analysis_and_is_repeatable(
    client: TestClient, engine: Engine, session: Session
) -> None:
    assert job.run(engine, UNIVERSE) == 0  # nothing held yet
    client.put("/api/v1/portfolio", json={"holdings": [{"symbol": "BTC", "quantity": 1}]})
    first = client.get("/api/v1/portfolio/analysis").json()
    assert job.run(engine, UNIVERSE) == 1
    assert client.get("/api/v1/portfolio/analysis").json() == first
    assert session.scalar(select(func.count()).select_from(PortfolioAnalysis)) == 1


def reading(*holdings: tuple[str, float]) -> BinanceReading:
    return BinanceReading(
        holdings=Holdings(
            source="binance",
            holdings=[Holding(symbol=s, quantity=q) for s, q in holdings],
            unsupported=[Unsupported(symbol="USDT", reason="A cash balance.")],
        ),
        leveraged=[
            Leveraged(
                symbol="BTC/USD",
                quantity=0.1,
                leverage=3,
                entry_price=50_000,
                mark_price=60_000,
                liquidation_price=45_000,
                distance_to_liquidation=0.25,
            )
        ],
    )


def test_binance_holdings_replace_the_portfolio_when_a_key_is_configured(
    client: TestClient, engine: Engine, session: Session
) -> None:
    assert client.get("/api/v1/portfolio").json()["binance_available"] is False
    assert client.post("/api/v1/portfolio/binance").status_code == 409

    app = client.app
    app.dependency_overrides[get_binance_reader] = lambda: lambda: reading(("BTC/USD", 0.4))  # type: ignore[attr-defined]
    body = client.post("/api/v1/portfolio/binance").json()
    assert body["source"] == "binance"
    assert body["binance_available"] is True
    assert [(h["symbol"], h["quantity"]) for h in body["holdings"]] == [("BTC/USD", 0.4)]
    assert [u["symbol"] for u in body["unsupported"]] == ["USDT"]
    assert body["leveraged"][0]["distance_to_liquidation"] == 0.25
    assert client.get("/api/v1/portfolio").json()["leveraged"] == body["leveraged"]
    assert client.get("/api/v1/portfolio/analysis").json()["positions"][0]["quantity"] == 0.4

    # The hourly job reads the exchange again, so a changed balance is picked up.
    assert job.run(engine, UNIVERSE, lambda: reading(("BTC/USD", 0.9), ("GLD", 2))) == 1
    positions = client.get("/api/v1/portfolio/analysis").json()["positions"]
    assert {p["symbol"]: p["quantity"] for p in positions} == {"BTC/USD": 0.9, "GLD": 2}

    # If the exchange cannot be reached, the last holdings are kept.
    def unreachable() -> BinanceReading:
        raise BinanceError("Could not reach Binance.")

    assert job.run(engine, UNIVERSE, unreachable) == 1
    assert len(client.get("/api/v1/portfolio").json()["holdings"]) == 2
    app.dependency_overrides[get_binance_reader] = lambda: unreachable  # type: ignore[attr-defined]
    refused = client.post("/api/v1/portfolio/binance")
    assert refused.status_code == 502
    assert refused.json()["detail"] == "Could not reach Binance."

    # Typing holdings in afterwards clears the leveraged exposure that came from Binance.
    saved = client.put("/api/v1/portfolio", json={"holdings": [{"symbol": "GLD", "quantity": 1}]})
    assert saved.json()["leveraged"] == []


def test_the_analysis_ties_holdings_to_their_market_state_and_drivers(
    client: TestClient, session: Session
) -> None:
    body = client.put(
        "/api/v1/portfolio",
        json={"holdings": [{"symbol": "BTC", "quantity": 0.05}, {"symbol": "GLD", "quantity": 40}]},
    )
    assert body.status_code == 200
    analysis = client.get("/api/v1/portfolio/analysis").json()
    # This universe has too few driver funds and no regime model: nothing is made up.
    assert analysis["drivers"] is None
    assert analysis["states"] == []
    assert analysis["trust"]["drivers"] is None
