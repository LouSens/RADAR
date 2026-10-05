"""Volatility forecasts against the real test database."""

from datetime import datetime

import numpy as np
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, VolatilityForecast
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import volatility as job
from tests.pipelines.test_regime_job import ASSET, DAY, DAYS, HOUR, START, seed, wire

SETTINGS = {"min_train": 260, "refit_every": 30}


def test_forecasts_are_stored_once_with_their_scores(engine: Engine, session: Session) -> None:
    seed(session)
    changed = job.forecast(engine, ASSET, **SETTINGS)
    total = session.scalar(select(func.count()).select_from(VolatilityForecast))
    assert changed == total
    assert job.forecast(engine, ASSET, **SETTINGS) == 0  # nothing new: no work, no rows

    rows = session.execute(
        select(
            VolatilityForecast.horizon_days,
            VolatilityForecast.model,
            func.count(),
            func.max(VolatilityForecast.ts),
            func.count(VolatilityForecast.realised),
        ).group_by(VolatilityForecast.horizon_days, VolatilityForecast.model)
    ).all()
    assert {(r[0], r[1]) for r in rows} == {
        (h, m) for h in (1, 7) for m in ("har", "gbt", "carry", "regime")
    }
    for horizon, _, count, newest, known in rows:
        # A forecast is stamped when its day had ended.
        assert newest == START + DAYS * DAY
        assert count - known == horizon  # the latest outcomes are not known yet

    registered = session.scalars(select(ModelRegistry)).one()
    assert registered.name == "volatility"
    assert registered.is_current
    assert set(registered.params) == {"1", "7"}
    week = registered.metrics["horizons"]["7"]
    assert week["shown"] in {"har", "gbt"}
    assert {s["model"] for s in week["scores"]} == {"har", "gbt", "carry", "regime"}
    assert week["n"] > 0


def test_a_new_day_adds_rows_and_fills_in_outcomes(engine: Engine, session: Session) -> None:
    seed(session)
    job.forecast(engine, ASSET, **SETTINGS)
    before: dict[tuple[int, str, datetime], float] = {
        (h, m, ts): f
        for h, m, ts, f in session.execute(
            select(
                VolatilityForecast.horizon_days,
                VolatilityForecast.model,
                VolatilityForecast.ts,
                VolatilityForecast.forecast,
            )
        )
    }

    rng = np.random.default_rng(3)
    price = 100.0
    rows = []
    for i in range(24):
        price *= float(np.exp(rng.normal(0, 0.01)))
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(START + DAYS * DAY + i * HOUR, price)))
    rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(START + DAYS * DAY, price)))
    upsert_bars(session, rows)
    session.commit()

    # Eight new forecasts (two horizons by four models) and eight outcomes filled in.
    assert job.forecast(engine, ASSET, **SETTINGS) == 16
    session.expire_all()
    after = {
        (h, m, ts): f
        for h, m, ts, f in session.execute(
            select(
                VolatilityForecast.horizon_days,
                VolatilityForecast.model,
                VolatilityForecast.ts,
                VolatilityForecast.forecast,
            )
        )
    }
    # No earlier forecast moved when the new day arrived.
    assert {key: after[key] for key in before} == before
    assert len(after) == len(before) + 8
    assert session.scalar(select(func.count()).select_from(ModelRegistry)) == 1
