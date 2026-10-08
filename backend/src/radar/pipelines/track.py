"""The live track record: forecasts written down when they were made, scored later.

Every other accuracy figure in the app is a backtest: the model replayed over history.
A backtest can flatter a model in ways that are hard to see. This log is different.
Each day the forecasts the app is showing are copied here, and a row is never changed
afterwards except to fill in what happened. After a few months it shows how the models
did on days that were truly in the future when they spoke.

Rows are only written for the current day. A day the worker did not run has no row;
nothing is filled in after the fact.
"""

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import ForecastLog, RiskMetric, VolatilityForecast
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import evidence, regime
from radar.pipelines import risk as risk_job
from radar.pipelines import simulation as simulation_job
from radar.pipelines import volatility as volatility_job
from radar.pipelines.datasets import build_regime_observations
from radar.pipelines.regime import day_end
from radar.universe import Asset, Universe

log = get_logger(__name__)

KINDS = ("outlook_range", "volatility", "loss_limit")


def _rows_for(session: Session, asset: Asset) -> list[dict[str, Any]]:
    """What the app is showing for this asset right now, as log rows."""
    rows: list[dict[str, Any]] = []

    run = simulation_job.latest(session, asset.symbol)
    if run is not None:
        for horizon in run.horizons:
            for interval in horizon["intervals"]:
                adjusted = interval.get("adjusted_low") is not None
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "kind": "outlook_range",
                        "horizon_days": horizon["horizon_days"],
                        "key": f"{interval['level']:g}",
                        "as_of": run.as_of,
                        "steps": horizon["steps"],
                        "model_version": run.model_version,
                        "forecast": {
                            "low": interval["adjusted_low"] if adjusted else interval["low"],
                            "high": interval["adjusted_high"] if adjusted else interval["high"],
                            "adjusted": adjusted,
                            "start_price": run.start_price,
                        },
                    }
                )

    volatility = volatility_job.current_model(session, asset.symbol)
    if volatility is not None:
        steps = volatility_job.HORIZON_STEPS[asset.asset_class]
        for days, evaluation in volatility.metrics["horizons"].items():
            latest = session.scalars(
                select(VolatilityForecast)
                .where(
                    VolatilityForecast.symbol == asset.symbol,
                    VolatilityForecast.horizon_days == int(days),
                    VolatilityForecast.model == evaluation["shown"],
                )
                .order_by(VolatilityForecast.ts.desc())
                .limit(1)
            ).first()
            if latest is not None:
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "kind": "volatility",
                        "horizon_days": int(days),
                        "key": latest.model,
                        "as_of": latest.ts,
                        "steps": steps[int(days)],
                        "model_version": latest.model_version,
                        "forecast": {"value": latest.forecast},
                    }
                )

    risk = risk_job.current_model(session, asset.symbol)
    newest = session.scalar(
        select(func.max(RiskMetric.ts)).where(RiskMetric.symbol == asset.symbol)
    )
    if risk is not None and newest is not None:
        for days, stored in risk.metrics["horizons"].items():
            if stored["shown"] is None:
                continue
            for metric in session.scalars(
                select(RiskMetric).where(
                    RiskMetric.symbol == asset.symbol,
                    RiskMetric.ts == newest,
                    RiskMetric.horizon_days == int(days),
                    RiskMetric.method == stored["shown"],
                )
            ):
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "kind": "loss_limit",
                        "horizon_days": int(days),
                        "key": f"{metric.level:g}",
                        "as_of": metric.ts,
                        "steps": stored["steps"],
                        "model_version": metric.model_version,
                        "forecast": {"value": metric.var, "method": metric.method},
                    }
                )
    return rows


def record(engine: Engine, universe: Universe) -> int:
    """Write down today's forecasts. A forecast already written is never touched."""
    written = 0
    from radar.pipelines import followed

    with session_scope(engine) as session:
        for asset in followed.assets(session, universe):
            rows = _rows_for(session, asset)
            if not rows:
                continue
            statement = (
                insert(ForecastLog)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["symbol", "kind", "horizon_days", "key", "as_of"]
                )
                .returning(ForecastLog.id)
            )
            written += len(session.execute(statement).all())
    if written:
        log.info("forecasts_recorded", rows=written)
    return written


def outcome_of(
    kind: str, forecast: dict[str, Any], returns: np.ndarray, volatility: np.ndarray
) -> dict[str, Any]:
    """What happened over the days a forecast covered, and whether the forecast held.

    `returns` and `volatility` are the daily log returns and realised volatility of
    exactly those days.
    """
    total = float(returns.sum())
    if kind == "outlook_range":
        price = forecast["start_price"] * float(np.exp(total))
        return {"value": price, "hit": bool(forecast["low"] <= price <= forecast["high"])}
    if kind == "loss_limit":
        loss = 1.0 - float(np.exp(total))
        return {"value": loss, "hit": bool(loss <= forecast["value"])}
    if kind == "volatility":
        return {"value": float(np.sqrt(np.mean(volatility**2)))}
    raise ValueError(f"Unknown forecast kind: {kind}")


def resolve(engine: Engine, universe: Universe, now: datetime | None = None) -> int:
    """Fill in what happened for every logged forecast whose days have all ended."""
    now = now or datetime.now(UTC)
    from radar.pipelines import followed

    resolved = 0
    for asset in followed.of(engine, universe):
        with session_scope(engine) as session:
            pending = list(
                session.scalars(
                    select(ForecastLog).where(
                        ForecastLog.symbol == asset.symbol, ForecastLog.outcome.is_(None)
                    )
                )
            )
            if not pending:
                continue
            observations = build_regime_observations(session, asset)
            clean = observations.dropna(subset=[*regime.FEATURES, "rv"])
            stamps = day_end(asset, pd.DatetimeIndex(clean.index))
            position = {
                pd.Timestamp(stamp): i for i, stamp in enumerate(stamps) if not pd.isna(stamp)
            }
            returns = clean["ret"].to_numpy(dtype=float)
            volatility = clean["rv"].to_numpy(dtype=float)
            for row in pending:
                start = position.get(pd.Timestamp(row.as_of))
                if start is None or start + row.steps >= len(clean):
                    continue
                days = slice(start + 1, start + row.steps + 1)
                row.outcome = outcome_of(row.kind, row.forecast, returns[days], volatility[days])
                row.resolved_at = now
                resolved += 1
    if resolved:
        log.info("forecasts_resolved", rows=resolved)
    return resolved


class TrackRecord(BaseModel):
    kind: str
    horizon_days: int
    key: str
    recorded: int
    resolved: int
    # For ranges and loss limits: how many held, with a 95% range for the share.
    held: int | None
    held_share: float | None
    held_low: float | None
    held_high: float | None
    # What the share should be if the forecast is right: the range's stated level.
    expected_share: float | None
    # For volatility: average of forecast divided by outcome (1.0 is unbiased).
    forecast_to_outcome: float | None
    first_as_of: datetime
    last_as_of: datetime


def summary(session: Session, symbol: str) -> list[TrackRecord]:
    rows = list(
        session.scalars(
            select(ForecastLog).where(ForecastLog.symbol == symbol).order_by(ForecastLog.as_of)
        )
    )
    groups: dict[tuple[str, int, str], list[ForecastLog]] = {}
    for row in rows:
        groups.setdefault((row.kind, row.horizon_days, row.key), []).append(row)
    result = []
    for (kind, horizon_days, key), group in sorted(groups.items()):
        done = [r for r in group if r.outcome is not None]
        scored = [r for r in done if "hit" in (r.outcome or {})]
        held = sum(bool((r.outcome or {})["hit"]) for r in scored) if scored else None
        low, high = evidence.wilson(held, len(scored)) if held is not None else (None, None)
        ratios = [
            r.forecast["value"] / r.outcome["value"]
            for r in done
            if kind == "volatility" and r.outcome and r.outcome["value"] > 0
        ]
        result.append(
            TrackRecord(
                kind=kind,
                horizon_days=horizon_days,
                key=key,
                recorded=len(group),
                resolved=len(done),
                held=held,
                held_share=held / len(scored) if held is not None else None,
                held_low=low,
                held_high=high,
                expected_share=float(key) if kind in ("outlook_range", "loss_limit") else None,
                forecast_to_outcome=float(np.mean(ratios)) if ratios else None,
                first_as_of=group[0].as_of,
                last_as_of=group[-1].as_of,
            )
        )
    return result


def run(engine: Engine, universe: Universe) -> int:
    return record(engine, universe) + resolve(engine, universe)
