"""Simulator runs and calibration reports against the real test database."""

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.models import CalibrationReport, Simulation
from radar.ingest.upsert import bar_row, upsert_bars
from radar.models import regime, simulator
from radar.pipelines import regime as regime_job
from radar.pipelines import simulation as job
from radar.pipelines.datasets import build_regime_observations
from tests.pipelines.test_regime_job import ASSET, DAY, DAYS, HOUR, START, UNIVERSE, seed, wire


@pytest.fixture
def trained(engine: Engine, session: Session, tmp_path: Path) -> int:
    seed(session)
    return regime_job.train(
        engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2
    )


def test_a_run_is_stored_once_and_can_be_rebuilt_from_its_seed(
    engine: Engine, session: Session, trained: int
) -> None:
    assert job.simulate(engine, ASSET, n_paths=500) == 1
    assert job.simulate(engine, ASSET, n_paths=500) == 0  # same day, same model: nothing new

    row = session.scalars(select(Simulation)).one()
    assert row.model_id == trained
    assert row.model_version == simulator.MODEL_VERSION
    assert row.as_of == START + DAYS * DAY  # the end of the last stored day
    assert row.n_paths == 500
    assert row.max_steps == 30
    assert [h["horizon_days"] for h in row.horizons] == [1, 7, 30]
    assert row.fan["0.5"][0] == row.start_price

    # Rebuild the run from the stored seed and the data up to that day.
    observations = build_regime_observations(session, ASSET)
    model = regime.RegimeModel.model_validate(
        regime_job.current_model(session, "BTC/USD").params  # type: ignore[union-attr]
    )
    probabilities = regime.filtered_probabilities(model, observations).to_numpy()
    returns = observations["ret"].to_numpy()
    pools, _ = simulator.build_pools(returns, probabilities.argmax(axis=1), 3)
    inputs = simulator.SimulationInputs(
        probabilities[-1], np.array(model.transition), pools, returns
    )
    again = simulator.cumulative_returns(simulator.simulate(inputs, 30, n_paths=500, seed=row.seed))
    stored = job.decode_paths(row)
    assert stored.shape == (500, 30)
    assert np.allclose(stored, again, atol=1e-6)
    # The stored summary is the summary of the stored paths.
    week = next(h for h in row.horizons if h["horizon_days"] == 7)
    assert week["quantiles"]["0.5"] == pytest.approx(
        simulator.summarise(stored, 7, row.start_price).quantiles["0.5"]
    )
    # No calibration yet, so there is no adjusted range to show.
    assert week["intervals"][1]["adjusted_low"] is None


def test_calibration_is_stored_and_feeds_the_adjusted_range(
    engine: Engine, session: Session, trained: int
) -> None:
    changed = job.calibrate(engine, ASSET, min_train=260, refit_every=30, n_paths=200)
    assert changed == 9  # three horizons by three ranges
    assert job.calibrate(engine, ASSET, min_train=260, refit_every=30, n_paths=200) == 0
    reports = session.scalars(select(CalibrationReport)).all()
    assert {(r.horizon_days, r.nominal) for r in reports} == {
        (h, level) for h in (1, 7, 30) for level in (0.5, 0.8, 0.95)
    }
    assert all(0 <= r.empirical <= 1 and r.n > 0 for r in reports)
    assert job.has_calibration(session, "BTC/USD")

    assert job.simulate(engine, ASSET, n_paths=500) == 1
    row = session.scalars(select(Simulation)).one()
    for horizon in row.horizons:
        for interval in horizon["intervals"]:
            assert interval["adjusted_low"] < interval["adjusted_high"]
            assert interval["low"] < interval["high"]


def test_only_the_latest_run_keeps_its_paths(
    engine: Engine, session: Session, trained: int
) -> None:
    assert job.simulate(engine, ASSET, n_paths=200) == 1
    # One more day of data arrives.
    rng = np.random.default_rng(9)
    price = 100.0
    rows = []
    for i in range(24):
        price *= float(np.exp(rng.normal(0, 0.005)))
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(START + DAYS * DAY + i * HOUR, price)))
    rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(START + DAYS * DAY, price)))
    upsert_bars(session, rows)
    session.commit()

    assert job.simulate(engine, ASSET, n_paths=200) == 1
    session.expire_all()
    runs = session.scalars(select(Simulation).order_by(Simulation.as_of)).all()
    assert [r.paths is not None for r in runs] == [False, True]
    assert runs[1].as_of - runs[0].as_of == timedelta(days=1)
    assert runs[0].seed != runs[1].seed
    newest = job.latest(session, "BTC/USD")
    assert newest is not None
    assert newest.id == runs[1].id
    with pytest.raises(ValueError, match="no longer"):
        job.decode_paths(runs[0])


def test_run_calibrates_once_then_only_simulates(
    engine: Engine, session: Session, trained: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = job.calibrate

    def quick(engine: Engine, asset: object, **kwargs: object) -> int:
        calls.append("calibrate")
        return real(engine, ASSET, min_train=260, refit_every=30, n_paths=200)

    monkeypatch.setattr(job, "calibrate", quick)
    assert job.run(engine, UNIVERSE) == 10  # nine report rows and one run
    assert job.run(engine, UNIVERSE) == 0
    assert calls == ["calibrate"]
