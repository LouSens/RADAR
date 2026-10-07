"""The events job and its route against the real test database."""

from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.db.assets import sync_assets
from radar.db.models import ModelRegistry
from radar.features.calendars import nyse_schedule
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import events as job
from radar.providers import schemas
from radar.universe import Universe

UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "SPY",
                "name": "US stocks (S&P 500)",
                "asset_class": "stock",
                "is_primary": True,
                "bars_symbol": "SPY",
                "history_start": "2022-01-01",
                "news_symbols": ["SPY"],
                "news_start": "2022-01-01",
            }
        ],
    }
)
FIRST = pd.Timestamp("2022-01-03", tz="UTC")
LAST = pd.Timestamp("2024-12-31", tz="UTC")


def seed(session: Session) -> None:
    """Three years of daily closes for one stock market."""
    sync_assets(session, UNIVERSE)
    schedule = nyse_schedule(FIRST, LAST)
    rng = np.random.default_rng(2)
    close = 450 * np.exp(np.cumsum(rng.normal(0, 0.01, len(schedule))))
    rows = []
    for i, day in enumerate(schedule.index):
        midnight = day.tz_localize("America/New_York").tz_convert(UTC).to_pydatetime()
        price = float(close[i])
        bar = schemas.Bar.model_validate(
            {
                "t": midnight,
                "o": price,
                "h": price,
                "l": price,
                "c": price,
                "v": 1,
                "n": 1,
                "vw": price,
            }
        )
        rows.append(bar_row("SPY", "1Day", "iex", bar))
    upsert_bars(session, rows)
    session.commit()


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    seed(session)
    with TestClient(create_app(engine, UNIVERSE)) as test_client:
        yield test_client


def test_nothing_is_served_before_the_first_run(client: TestClient) -> None:
    assert client.get("/api/v1/events").status_code == 404


def test_events_are_measured_from_stored_prices_and_served_with_what_is_coming(
    client: TestClient, engine: Engine, session: Session
) -> None:
    assert job.run(engine, UNIVERSE) == 3
    body = client.get("/api/v1/events").json()
    assert [r["key"] for r in body["results"]] == ["fed", "jobs", "inflation"]
    assert body["names"] == {"SPY": "US stocks (S&P 500)"}

    by_key = {r["key"]: r["markets"][0] for r in body["results"]}
    # Eight scheduled Fed meetings a year: twenty-four in these three years, too few
    # to judge. A report a month gives thirty-six, less one that came out on a market
    # holiday (Good Friday 2023), which has no trading day of its own.
    assert by_key["fed"]["n_events"] == 24
    assert by_key["fed"]["size"]["verdict"] == "not enough events"
    assert body["trust"]["fed"]["grade"] == "rough"
    jobs = by_key["jobs"]
    assert jobs["n_events"] == 35
    assert by_key["inflation"]["n_events"] == 36
    assert (jobs["first_day"], jobs["last_day"]) == ("2022-01-07", "2024-12-06")
    assert body["trust"]["jobs"]["grade"] == "fair"
    # The prices are random, so nothing is found, and it is said plainly.
    assert jobs["size"]["verdict"] == "no measurable difference"
    for name in ("day_before", "event_day", "next_day", "next_week"):
        assert jobs[name]["verdict"] == "no measurable pattern"
        assert jobs[name]["low"] <= jobs[name]["share"] <= jobs[name]["high"]
    assert (body["direction_tests"], body["size_tests"]) == (8, 2)

    # What is coming is read from the dates file as of now, soonest first.
    now = datetime.now(UTC)
    times = [datetime.fromisoformat(e["at"]) for e in body["upcoming"]]
    assert times == sorted(times)
    assert all(t > now for t in times)
    assert all(e["days_until"] >= 0 for e in body["upcoming"])
    assert {e["key"] for e in body["upcoming"]} <= {"fed", "jobs", "inflation"}


def test_running_again_keeps_one_current_result(
    client: TestClient, engine: Engine, session: Session
) -> None:
    job.run(engine, UNIVERSE)
    first = client.get("/api/v1/events").json()["results"]
    job.run(engine, UNIVERSE)
    current = session.scalar(
        select(func.count())
        .select_from(ModelRegistry)
        .where(ModelRegistry.name == job.NAME, ModelRegistry.is_current)
    )
    assert current == 1
    assert client.get("/api/v1/events").json()["results"] == first
