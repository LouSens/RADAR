"""The brief job and its route against the real test database."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.api.app import create_app
from radar.brief import grounding
from radar.db.assets import sync_assets
from radar.db.models import Brief
from radar.pipelines import brief as job
from radar.pipelines import signals as signals_job
from tests.api.test_signals_api import UNIVERSE, built

NOW = datetime(2024, 3, 4, 9, tzinfo=UTC)


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    sync_assets(session, UNIVERSE)
    records, rows = built()
    signals_job.store(session, records, rows)
    session.commit()
    with TestClient(create_app(engine, UNIVERSE)) as test_client:
        yield test_client


def test_there_is_no_brief_until_one_is_written(client: TestClient) -> None:
    assert client.get("/api/v1/briefs/latest").status_code == 404


def test_the_brief_is_built_from_stored_results_and_every_number_is_grounded(
    client: TestClient, engine: Engine, session: Session
) -> None:
    assert job.run(engine, UNIVERSE, now=NOW) == 2
    rows = job.latest(session)
    assert [r.symbol for r in rows] == ["BTC/USD", "SPY"]
    for row in rows:
        assert grounding.ungrounded(row.text, row.payload) == []
        assert row.writer == "template"
    # No models are stored for these markets, so only the signals are reported: the
    # three abnormal moves of the first three days of March, newest first.
    bitcoin = rows[0]
    assert [s["days_ago"] for s in bitcoin.payload["signals"]] == [1, 2, 3]
    assert bitcoin.text.startswith("Yesterday there was an abnormally large hourly move up.")
    assert "Over 39 past cases" in bitcoin.text
    # The stock's one signal has five past cases: too few to judge, and it says so.
    assert "It has happened 5 times before, too few to say" in rows[1].text


def test_running_again_on_the_same_day_replaces_the_brief(
    client: TestClient, engine: Engine, session: Session
) -> None:
    job.run(engine, UNIVERSE, now=NOW)
    job.run(engine, UNIVERSE, now=NOW.replace(hour=15))
    assert session.scalar(select(func.count()).select_from(Brief)) == 2
    # A new day adds a new brief, and the route serves the newest.
    job.run(engine, UNIVERSE, now=NOW.replace(day=5))
    assert session.scalar(select(func.count()).select_from(Brief)) == 4
    body = client.get("/api/v1/briefs/latest").json()
    assert body["day"] == "2024-03-05"
    assert [i["symbol"] for i in body["items"]] == ["BTC/USD", "SPY"]
    first = body["items"][0]
    assert first["name"] == "Bitcoin"
    assert {s["section"] for s in first["sentences"]} == {"signals"}
    assert first["sentences"][0]["text"].startswith("2 days ago there was")
