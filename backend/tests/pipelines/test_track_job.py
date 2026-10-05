"""The live forecast log against the real test database."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.models import ForecastLog
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import regime as regime_job
from radar.pipelines import risk as risk_job
from radar.pipelines import simulation as simulation_job
from radar.pipelines import track as job
from radar.pipelines import volatility as volatility_job
from tests.pipelines.test_regime_job import ASSET, DAY, DAYS, HOUR, START, UNIVERSE, seed, wire


def add_days(session: Session, first: int, count: int, seed_: int = 4) -> None:
    rng = np.random.default_rng(seed_)
    price = 100.0
    rows = []
    for day in range(first, first + count):
        for hour in range(24):
            price *= float(np.exp(rng.normal(0, 0.004)))
            rows.append(
                bar_row("BTC/USD", "1Hour", "us-1", wire(START + day * DAY + hour * HOUR, price))
            )
        rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(START + day * DAY, price)))
    upsert_bars(session, rows)
    session.commit()


@pytest.fixture
def forecasts(engine: Engine, session: Session, tmp_path: Path) -> None:
    """A market with every Phase 3 forecast stored for its latest day."""
    seed(session)
    regime_job.train(
        engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2
    )
    simulation_job.simulate(engine, ASSET, n_paths=300)
    volatility_job.forecast(engine, ASSET, min_train=260, refit_every=30)
    risk_job.assess(engine, ASSET, min_train=260, refit_every=30, n_paths=200, min_window=20)


def test_todays_forecasts_are_written_once(
    engine: Engine, session: Session, forecasts: None
) -> None:
    written = job.record(engine, UNIVERSE)
    # Three ranges at three horizons, a volatility forecast and two loss limits at two.
    assert written == 9 + 2 + 4
    assert job.record(engine, UNIVERSE) == 0  # already written: never rewritten
    rows = session.scalars(select(ForecastLog)).all()
    assert {r.kind for r in rows} == set(job.KINDS)
    assert all(r.as_of == START + DAYS * DAY for r in rows)
    assert all(r.outcome is None for r in rows)
    week = next(
        r for r in rows if r.kind == "outlook_range" and r.horizon_days == 7 and r.key == "0.8"
    )
    assert week.steps == 7
    assert week.forecast["low"] < week.forecast["start_price"] < week.forecast["high"]


def test_outcomes_are_filled_in_only_when_the_days_have_ended(
    engine: Engine, session: Session, forecasts: None
) -> None:
    job.record(engine, UNIVERSE)
    before = {r.id: dict(r.forecast) for r in session.scalars(select(ForecastLog))}
    assert job.resolve(engine, UNIVERSE) == 0  # nothing has happened yet

    add_days(session, DAYS, 1)
    # One day later only the one-day forecasts can be scored: 3 ranges, 1 volatility, 2 limits.
    assert job.resolve(engine, UNIVERSE, now=datetime(2030, 1, 1, tzinfo=UTC)) == 6
    session.expire_all()
    rows = session.scalars(select(ForecastLog)).all()
    done = [r for r in rows if r.outcome is not None]
    assert {r.horizon_days for r in done} == {1}
    assert all(r.resolved_at == datetime(2030, 1, 1, tzinfo=UTC) for r in done)
    # A forecast is never edited after it is written.
    assert {r.id: dict(r.forecast) for r in rows} == before
    wide = next(r for r in done if r.kind == "outlook_range" and r.key == "0.95")
    assert wide.outcome is not None
    assert wide.outcome["hit"] == (
        wide.forecast["low"] <= wide.outcome["value"] <= wide.forecast["high"]
    )

    add_days(session, DAYS + 1, 7, seed_=5)
    assert job.resolve(engine, UNIVERSE) == 6  # now the seven-day ones too; 30-day still open
    assert job.resolve(engine, UNIVERSE) == 0


def test_outcomes_match_a_hand_calculation() -> None:
    returns = np.array([0.01, -0.03])
    volatility = np.array([0.02, 0.04])
    held = job.outcome_of(
        "outlook_range", {"low": 95.0, "high": 105.0, "start_price": 100.0}, returns, volatility
    )
    assert held["value"] == pytest.approx(100 * np.exp(-0.02))
    assert held["hit"] is True
    missed = job.outcome_of(
        "outlook_range", {"low": 99.0, "high": 105.0, "start_price": 100.0}, returns, volatility
    )
    assert missed["hit"] is False
    # A loss limit holds when the loss stays at or under it.
    assert job.outcome_of("loss_limit", {"value": 0.03}, returns, volatility)["hit"] is True
    assert job.outcome_of("loss_limit", {"value": 0.01}, returns, volatility)["hit"] is False
    swing = job.outcome_of("volatility", {"value": 0.03}, returns, volatility)
    assert swing == {"value": pytest.approx(np.sqrt((0.02**2 + 0.04**2) / 2))}
    with pytest.raises(ValueError, match="Unknown"):
        job.outcome_of("other", {}, returns, volatility)


def test_summary_counts_what_held_with_a_range(
    engine: Engine, session: Session, forecasts: None
) -> None:
    job.record(engine, UNIVERSE)
    rows = job.summary(session, "BTC/USD")
    assert len(rows) == 15
    assert all(r.resolved == 0 and r.held is None and r.held_low is None for r in rows)

    add_days(session, DAYS, 1)
    job.resolve(engine, UNIVERSE)
    session.expire_all()
    by_key = {(r.kind, r.horizon_days, r.key): r for r in job.summary(session, "BTC/USD")}
    day = by_key[("outlook_range", 1, "0.8")]
    assert (day.recorded, day.resolved) == (1, 1)
    assert day.held in (0, 1)
    assert day.expected_share == 0.8
    # One result says almost nothing, and the range shows it.
    assert day.held_low is not None
    assert day.held_high is not None
    assert day.held_high - day.held_low > 0.7
    swings = by_key[("volatility", 1, "har")]
    assert swings.held is None
    assert swings.forecast_to_outcome is not None
    assert swings.forecast_to_outcome > 0
    assert by_key[("outlook_range", 30, "0.8")].resolved == 0
