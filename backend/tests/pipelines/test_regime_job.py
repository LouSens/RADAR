"""Regime training and scoring against the real test database."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import ModelRegistry, RegimeState
from radar.ingest.upsert import bar_row, upsert_bars
from radar.pipelines import regime as job
from radar.providers import schemas
from radar.universe import Asset, Universe

DAY = timedelta(days=1)
HOUR = timedelta(hours=1)
START = datetime(2024, 1, 1, tzinfo=UTC)
DAYS = 320

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
                "history_start": "2024-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2024-01-01",
            }
        ],
    }
)
ASSET = UNIVERSE.get("BTC/USD")


def wire(ts: datetime, price: float) -> schemas.Bar:
    return schemas.Bar.model_validate(
        {"t": ts, "o": price, "h": price, "l": price, "c": price, "v": 1, "n": 1, "vw": price}
    )


def seed(session: Session, days: int = DAYS) -> None:
    """Hourly and daily bars for a market that alternates quiet and wild months."""
    sync_assets(session, UNIVERSE)
    rng = np.random.default_rng(0)
    hours = days * 24
    volatility = np.where((np.arange(hours) // (24 * 40)) % 2 == 0, 0.002, 0.012)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, volatility)))
    rows = [
        bar_row("BTC/USD", "1Hour", "us-1", wire(START + i * HOUR, float(p)))
        for i, p in enumerate(prices)
    ]
    rows += [
        bar_row("BTC/USD", "1Day", "us-1", wire(START + d * DAY, float(prices[d * 24 + 23])))
        for d in range(days)
    ]
    upsert_bars(session, rows)
    session.commit()


def test_train_registers_a_model_and_score_stores_filtered_states(
    engine: Engine, session: Session, tmp_path: Path
) -> None:
    seed(session)
    model_id = job.train(
        engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2
    )

    registered = session.scalars(select(ModelRegistry)).one()
    assert registered.id == model_id
    assert registered.is_current
    assert registered.name == "regime"
    assert registered.params["n_states"] == 3
    assert set(registered.metrics["bic_by_states"]) == {"2", "3", "4"}
    assert registered.artefact_path is not None
    assert Path(registered.artefact_path).is_file()

    changed = job.score(engine, ASSET)
    assert changed == session.scalar(select(func.count()).select_from(RegimeState))
    assert changed > 300
    states = pd.DataFrame(
        session.execute(
            select(
                RegimeState.ts, RegimeState.label, RegimeState.probability, RegimeState.probs
            ).order_by(RegimeState.ts)
        ).all(),
        columns=["ts", "label", "probability", "probs"],
    )
    # A reading is stamped when its day had ended: at midnight UTC of the next day.
    assert all(ts.hour == 0 for ts in states["ts"])
    assert states["ts"].iloc[-1] == START + DAYS * DAY
    assert {"calm", "turbulent"} <= set(states["label"])
    first = states.iloc[0]
    assert abs(sum(first["probs"].values()) - 1.0) < 1e-4
    assert first["probability"] == max(first["probs"].values())

    assert job.score(engine, ASSET) == 0  # scoring again changes nothing


def test_stored_states_do_not_change_when_later_days_arrive(
    engine: Engine, session: Session, tmp_path: Path
) -> None:
    seed(session, days=300)
    job.train(engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2)
    job.score(engine, ASSET)
    before: dict[datetime, dict[str, float]] = dict(
        session.execute(select(RegimeState.ts, RegimeState.probs)).all()
    )

    # Twenty more days of data arrive; the same model scores them.
    rng = np.random.default_rng(5)
    last = 100.0
    rows = []
    for i in range(20 * 24):
        last *= float(np.exp(rng.normal(0, 0.03)))
        stamp = START + 300 * DAY + i * HOUR
        rows.append(bar_row("BTC/USD", "1Hour", "us-1", wire(stamp, last)))
        if i % 24 == 23:
            day = START + (300 + i // 24) * DAY
            rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(day, last)))
    upsert_bars(session, rows)
    session.commit()

    assert job.score(engine, ASSET) == 20  # only the new days are written
    session.expire_all()
    after: dict[datetime, dict[str, float]] = dict(
        session.execute(select(RegimeState.ts, RegimeState.probs)).all()
    )
    assert {ts: after[ts] for ts in before} == before


def test_retraining_replaces_the_current_model(
    engine: Engine, session: Session, tmp_path: Path
) -> None:
    seed(session)
    first = job.train(
        engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2
    )
    second = job.train(
        engine, ASSET, evaluate=False, artefact_root=tmp_path, mlflow_uri=None, n_init=2
    )
    current = session.scalars(select(ModelRegistry.id).where(ModelRegistry.is_current)).all()
    assert current == [second]
    assert first != second
    found = job.current_model(session, "BTC/USD")
    assert found is not None
    assert found.id == second


def test_run_trains_once_then_only_scores(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed(session)
    trained: list[str] = []
    real_train = job.train

    def fake_train(engine: Engine, asset: Asset, **kwargs: object) -> int:
        trained.append(asset.symbol)
        return real_train(engine, asset, evaluate=False, mlflow_uri=None, n_init=2)

    monkeypatch.setattr(job, "train", fake_train)
    monkeypatch.chdir(tmp_path)  # artefacts land outside the repo
    assert job.run(engine, UNIVERSE) > 0
    assert job.run(engine, UNIVERSE) == 0
    assert trained == ["BTC/USD"]
