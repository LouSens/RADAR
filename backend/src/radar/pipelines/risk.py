"""Estimate tail risk for every day, store it, and record how each method's limits held.

Runs after the volatility job, whose stored forecasts feed the filtered method. Each
stored estimate was made from what was known on its own day.
"""

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, RiskMetric, VolatilityForecast
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import calibration, regime, tail_risk
from radar.pipelines.datasets import build_regime_observations, load_field, stock_daily
from radar.pipelines.regime import day_end
from radar.pipelines.volatility import HORIZON_STEPS
from radar.universe import Asset, Universe

log = get_logger(__name__)

MODEL_NAME = "tail_risk"
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


def _stored_forecasts(session: Session, symbol: str, horizon_days: int) -> dict[Any, float]:
    """The HAR volatility forecast made at each day end. The trees are not used here."""
    rows = session.execute(
        select(VolatilityForecast.ts, VolatilityForecast.forecast).where(
            VolatilityForecast.symbol == symbol,
            VolatilityForecast.horizon_days == horizon_days,
            VolatilityForecast.model == "har",
        )
    ).all()
    return {pd.Timestamp(ts): forecast for ts, forecast in rows}


def _upsert(session: Session, rows: list[dict[str, Any]]) -> int:
    changed = 0
    for start in range(0, len(rows), BATCH):
        statement = insert(RiskMetric).values(rows[start : start + BATCH])
        excluded = statement.excluded
        measured = ("var", "expected_shortfall", "realised_loss")
        upsert = statement.on_conflict_do_update(
            index_elements=[
                RiskMetric.symbol,
                RiskMetric.horizon_days,
                RiskMetric.level,
                RiskMetric.method,
                RiskMetric.ts,
            ],
            set_={
                **{name: getattr(excluded, name) for name in measured},
                "model_version": excluded.model_version,
            },
            where=tuple_(*(getattr(RiskMetric, name) for name in measured)).is_distinct_from(
                tuple_(*(getattr(excluded, name) for name in measured))
            ),
        ).returning(RiskMetric.ts)
        changed += len(session.execute(upsert).all())
    return changed


def assess(
    engine: Engine,
    asset: Asset,
    *,
    min_train: int = 500,
    refit_every: int = 63,
    n_paths: int = 2000,
    min_window: int = tail_risk.MIN_WINDOW,
    force: bool = False,
) -> int:
    """Store estimates for every day not yet covered. Returns the number of rows changed."""
    steps = HORIZON_STEPS[asset.asset_class]
    with session_scope(engine) as session:
        observations = build_regime_observations(session, asset)
        newest = session.scalar(
            select(func.max(RiskMetric.ts)).where(RiskMetric.symbol == asset.symbol)
        )
        stored = {days: _stored_forecasts(session, asset.symbol, days) for days in steps}
        if asset.asset_class == "crypto":
            close = load_field(session, [asset.symbol], "1Day")[asset.symbol]
        else:
            close = stock_daily(session, [asset.symbol])[asset.symbol]
    clean = observations.dropna(subset=list(regime.FEATURES))
    if len(clean) <= min_train:
        log.warning("risk_skipped", symbol=asset.symbol, days=len(clean))
        return 0
    index = pd.DatetimeIndex(clean.index)
    stamps = day_end(asset, index)
    up_to_date = (
        newest is not None and not pd.isna(stamps[-1]) and stamps[-1] <= pd.Timestamp(newest)
    )
    if up_to_date and not force:
        return 0  # nothing new since the last run

    returns = clean["ret"].to_numpy(dtype=float)
    simulations = calibration.walk_forward_forecasts(
        clean, tuple(steps.values()), min_train=min_train, refit_every=refit_every, n_paths=n_paths
    )
    rows: list[dict[str, Any]] = []
    horizons: dict[str, Any] = {}
    tested: dict[int, tuple[int, list[tail_risk.Backtest]]] = {}
    for days, count in steps.items():
        forecasts = np.array([stored[days].get(stamp, np.nan) for stamp in stamps], dtype=float)
        estimates = tail_risk.estimate(
            tail_risk.RiskInputs(
                returns=returns,
                volatility_forecast=forecasts,
                simulated_days=simulations[count].origins,
                simulated=simulations[count].samples,
            ),
            count,
            min_window=min_window,
        )
        tested[days] = (count, tail_risk.backtest(estimates, index))
        for (method, level), values in estimates.var.items():
            shortfall = estimates.es[(method, level)]
            for t in np.flatnonzero(~np.isnan(values)).tolist():
                if pd.isna(stamps[t]):
                    continue
                loss = estimates.realised_loss[t]
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "horizon_days": days,
                        "level": level,
                        "method": method,
                        "ts": stamps[t].to_pydatetime(),
                        "model_version": tail_risk.MODEL_VERSION,
                        "var": float(values[t]),
                        "expected_shortfall": float(shortfall[t]),
                        "realised_loss": None if np.isnan(loss) else float(loss),
                    }
                )
    # Every limit for this market is one family of tests: judge them together.
    flat = tail_risk.correct_family([b for _, rows in tested.values() for b in rows])
    position = 0
    for days, (count, backtests) in tested.items():
        corrected = flat[position : position + len(backtests)]
        position += len(backtests)
        horizons[str(days)] = {
            "steps": count,
            "shown": tail_risk.choose(corrected),
            "backtests": [b.model_dump(mode="json") for b in corrected],
        }
    metrics = {
        "horizons": horizons,
        "drawdowns": [
            d.model_dump(mode="json") for d in tail_risk.worst_drawdowns(close.loc[: index[-1]])
        ],
    }
    with session_scope(engine) as session:
        changed = _upsert(session, rows)
        existing = current_model(session, asset.symbol)
        if existing is not None and existing.version == tail_risk.MODEL_VERSION:
            existing.metrics = metrics
            existing.train_end = index[-1].date()
        else:
            session.execute(
                update(ModelRegistry)
                .where(ModelRegistry.name == MODEL_NAME, ModelRegistry.symbol == asset.symbol)
                .values(is_current=False)
            )
            session.add(
                ModelRegistry(
                    name=MODEL_NAME,
                    symbol=asset.symbol,
                    version=tail_risk.MODEL_VERSION,
                    train_start=index[0].date(),
                    train_end=index[-1].date(),
                    is_current=True,
                    params={"window": tail_risk.WINDOW, "min_window": min_window},
                    metrics=metrics,
                )
            )
    log.info("risk_stored", symbol=asset.symbol, rows=len(rows), changed=changed)
    return changed


def run(engine: Engine, universe: Universe, *, force: bool = False) -> int:
    from radar.pipelines import followed

    return sum(assess(engine, asset, force=force) for asset in followed.of(engine, universe))
