"""Forecast volatility walk-forward, store every forecast, and record how each model did.

Each stored forecast was made from data up to its own day by a model fitted on earlier
days, so the latest row is the live forecast and the older rows are its track record.
"""

from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, VolatilityForecast
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import regime, volatility
from radar.pipelines.datasets import build_regime_observations
from radar.pipelines.regime import day_end
from radar.universe import Asset, Universe

log = get_logger(__name__)

MODEL_NAME = "volatility"
# Trading steps for each horizon in days. Stocks have 5 sessions a week.
HORIZON_STEPS: dict[str, dict[int, int]] = {
    "crypto": {1: 1, 7: 7},
    "stock": {1: 1, 7: 5},
}
BATCH = 2_000


def current_model(session: Session, symbol: str) -> ModelRegistry | None:
    return session.scalars(
        select(ModelRegistry)
        .where(
            ModelRegistry.name == MODEL_NAME,
            ModelRegistry.symbol == symbol,
            ModelRegistry.is_current,
        )
        .order_by(ModelRegistry.trained_at.desc())
        .limit(1)
    ).first()


def _upsert(session: Session, rows: list[dict[str, Any]]) -> int:
    changed = 0
    for start in range(0, len(rows), BATCH):
        statement = insert(VolatilityForecast).values(rows[start : start + BATCH])
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[
                VolatilityForecast.symbol,
                VolatilityForecast.horizon_days,
                VolatilityForecast.model,
                VolatilityForecast.ts,
            ],
            set_={
                "forecast": excluded.forecast,
                "realised": excluded.realised,
                "model_version": excluded.model_version,
            },
            where=tuple_(VolatilityForecast.forecast, VolatilityForecast.realised).is_distinct_from(
                tuple_(excluded.forecast, excluded.realised)
            ),
        ).returning(VolatilityForecast.ts)
        changed += len(session.execute(upsert).all())
    return changed


def _register(
    session: Session,
    asset: Asset,
    walks: dict[int, volatility.WalkForward],
    evaluations: dict[int, volatility.HorizonEvaluation],
    horizon_of: dict[int, int],
) -> None:
    """Record the latest fits and their scores. One row per refit; scores are kept current."""
    first = walks[min(walks)].latest
    params = {str(horizon_of[s]): w.latest.model_dump(mode="json") for s, w in walks.items()}
    metrics = {
        "horizons": {str(horizon_of[s]): e.model_dump(mode="json") for s, e in evaluations.items()}
    }
    existing = current_model(session, asset.symbol)
    if existing is not None and existing.train_end == first.train_end:
        existing.metrics = metrics
        return
    session.execute(
        update(ModelRegistry)
        .where(ModelRegistry.name == MODEL_NAME, ModelRegistry.symbol == asset.symbol)
        .values(is_current=False)
    )
    session.add(
        ModelRegistry(
            name=MODEL_NAME,
            symbol=asset.symbol,
            version=volatility.MODEL_VERSION,
            train_start=first.train_start,
            train_end=first.train_end,
            is_current=True,
            params=params,
            metrics=metrics,
        )
    )


def forecast(
    engine: Engine,
    asset: Asset,
    *,
    min_train: int = 500,
    refit_every: int = 63,
    refit: bool = False,
) -> int:
    """Store forecasts for every day not yet covered. Returns the number of rows changed.

    `refit` works every day out again even when none is new: for when the measure of a
    day's movement itself has changed (decision 091).
    """
    with session_scope(engine) as session:
        observations = build_regime_observations(session, asset)
        newest = session.scalar(
            select(func.max(VolatilityForecast.ts)).where(VolatilityForecast.symbol == asset.symbol)
        )
    clean = observations.dropna(subset=[*regime.FEATURES, "rv"])
    if len(clean) <= min_train:
        log.warning("volatility_skipped", symbol=asset.symbol, days=len(clean))
        return 0
    stamps = day_end(asset, pd.DatetimeIndex(clean.index))
    covered = newest is not None and not pd.isna(stamps[-1]) and stamps[-1] <= pd.Timestamp(newest)
    if covered and not refit:
        return 0  # nothing new since the last run

    steps = HORIZON_STEPS[asset.asset_class]
    horizon_of = {count: days for days, count in steps.items()}
    walks = volatility.walk_forward(
        clean, tuple(steps.values()), min_train=min_train, refit_every=refit_every
    )
    stamp_of = dict(zip(clean.index, stamps, strict=True))
    rows: list[dict[str, Any]] = []
    evaluations: dict[int, volatility.HorizonEvaluation] = {}
    for count, walk in walks.items():
        if walk.forecasts["realised"].notna().any():
            evaluations[count] = volatility.evaluate(walk)
        for day, record in walk.forecasts.iterrows():
            ts = stamp_of[day]
            if pd.isna(ts):
                continue
            realised = None if pd.isna(record["realised"]) else float(record["realised"])
            rows.extend(
                {
                    "symbol": asset.symbol,
                    "ts": ts.to_pydatetime(),
                    "horizon_days": horizon_of[count],
                    "model": name,
                    "model_version": volatility.MODEL_VERSION,
                    "forecast": float(record[name]),
                    "realised": realised,
                }
                for name in volatility.MODELS
            )
    with session_scope(engine) as session:
        changed = _upsert(session, rows)
        if evaluations:
            _register(session, asset, walks, evaluations, horizon_of)
    log.info("volatility_stored", symbol=asset.symbol, rows=len(rows), changed=changed)
    return changed


def run(engine: Engine, universe: Universe, *, refit: bool = False) -> int:
    return sum(forecast(engine, asset, refit=refit) for asset in universe.primary)
