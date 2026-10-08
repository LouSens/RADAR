"""Run the outcome simulator, store each run, and measure how its past ranges held.

`simulate` stores one run per asset and day, with the seed and the simulated paths, so
every displayed number can be rebuilt. `calibrate` replays the simulator over history
walk-forward and stores the coverage table. The API only ever reads the stored rows.
"""

import zlib
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import CalibrationReport, Simulation
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import calibration, regime, simulator
from radar.pipelines.datasets import build_regime_observations, load_field, stock_daily
from radar.pipelines.regime import current_model, day_end
from radar.universe import Asset, Universe

log = get_logger(__name__)

# At or below this miss rate the adjusted range is as wide as the method can make it.
WIDEST_MISS_RATE = 0.002


def seed_for(symbol: str, as_of: datetime, model_id: int) -> int:
    """A fixed seed for one run, so a rerun of the same day gives the same paths."""
    return zlib.crc32(f"{symbol}|{as_of.isoformat()}|{model_id}".encode())


def encode_paths(cumulative: np.ndarray) -> bytes:
    return zlib.compress(cumulative.astype("<f4").tobytes(), 1)


def decode_paths(row: Simulation) -> np.ndarray:
    """Cumulative log returns of a stored run, shape (n_paths, max_steps)."""
    if row.paths is None:
        raise ValueError("This run no longer has its paths stored")
    flat = np.frombuffer(zlib.decompress(row.paths), dtype="<f4")
    return flat.reshape(row.n_paths, row.max_steps).astype(float)


def _last_close(session: Session, asset: Asset, day: pd.Timestamp) -> float:
    if asset.asset_class == "crypto":
        closes = load_field(session, [asset.symbol], "1Day")[asset.symbol]
    else:
        closes = stock_daily(session, [asset.symbol])[asset.symbol]
    return float(closes.loc[day])


def _miss_rates(session: Session, symbol: str) -> dict[tuple[int, float], float]:
    rows = session.execute(
        select(
            CalibrationReport.horizon_days,
            CalibrationReport.nominal,
            CalibrationReport.conformal_miss_rate,
        ).where(
            CalibrationReport.symbol == symbol,
            CalibrationReport.model_version == simulator.MODEL_VERSION,
        )
    ).all()
    return {(days, nominal): miss for days, nominal, miss in rows}


def horizon_payload(
    cumulative: np.ndarray,
    horizon_days: int,
    steps: int,
    start_price: float,
    miss_rates: dict[tuple[int, float], float],
) -> dict[str, Any]:
    """One horizon's summary, with each range also given after the conformal adjustment."""
    summary = simulator.summarise(cumulative, steps, start_price)
    payload = summary.model_dump()
    payload["horizon_days"] = horizon_days
    terminal = cumulative[:, steps - 1]
    for interval in payload["intervals"]:
        miss = miss_rates.get((horizon_days, interval["level"]))
        if miss is None:
            interval.update(adjusted_low=None, adjusted_high=None, adjusted_is_widest=False)
            continue
        low, high = np.quantile(terminal, [miss / 2.0, 1.0 - miss / 2.0])
        interval.update(
            adjusted_low=start_price * float(np.exp(low)),
            adjusted_high=start_price * float(np.exp(high)),
            adjusted_is_widest=miss <= WIDEST_MISS_RATE,
        )
    return payload


def simulate(engine: Engine, asset: Asset, *, n_paths: int = simulator.DEFAULT_PATHS) -> int:
    """Store a run for the latest completed day. Returns 1 if a run was written, else 0."""
    with session_scope(engine) as session:
        registered = current_model(session, asset.symbol)
        if registered is None:
            return 0
        model = regime.RegimeModel.model_validate(registered.params)
        model_id = registered.id
        observations = build_regime_observations(session, asset)
        clean = observations.dropna(subset=list(regime.FEATURES))
        if clean.empty:
            return 0
        last_day = pd.DatetimeIndex(clean.index)[-1]
        stamp = day_end(asset, pd.DatetimeIndex([last_day]))[0]
        if pd.isna(stamp):
            return 0
        as_of = stamp.to_pydatetime()
        exists = session.scalar(
            select(Simulation.id).where(
                Simulation.symbol == asset.symbol,
                Simulation.as_of == as_of,
                Simulation.model_id == model_id,
            )
        )
        if exists is not None:
            return 0
        start_price = _last_close(session, asset, last_day)
        miss_rates = _miss_rates(session, asset.symbol)

    # Filtered, so the regime of each past day uses that day and earlier days only.
    probabilities = regime.filtered_probabilities(model, clean).to_numpy()
    returns = clean["ret"].to_numpy(dtype=float)
    pools, _ = simulator.build_pools(returns, probabilities.argmax(axis=1), model.n_states)
    inputs = simulator.SimulationInputs(
        start_probabilities=probabilities[-1],
        transition=np.array(model.transition),
        pools=pools,
        all_returns=returns,
    )
    steps = calibration.HORIZON_STEPS[asset.asset_class]
    max_steps = max(steps.values())
    seed = seed_for(asset.symbol, as_of, model_id)
    daily = simulator.simulate(inputs, max_steps, n_paths=n_paths, seed=seed)
    # Summaries are taken from the paths exactly as they are stored.
    cumulative = simulator.cumulative_returns(daily).astype("<f4").astype(float)

    with session_scope(engine) as session:
        session.execute(
            update(Simulation).where(Simulation.symbol == asset.symbol).values(paths=None)
        )
        session.add(
            Simulation(
                symbol=asset.symbol,
                as_of=as_of,
                model_id=model_id,
                model_version=simulator.MODEL_VERSION,
                seed=seed,
                n_paths=n_paths,
                max_steps=max_steps,
                start_price=start_price,
                horizons=[
                    horizon_payload(cumulative, days, count, start_price, miss_rates)
                    for days, count in steps.items()
                ],
                fan=simulator.fan(cumulative, start_price),
                paths=encode_paths(cumulative),
            )
        )
    log.info("simulation_stored", symbol=asset.symbol, as_of=as_of.isoformat(), seed=seed)
    return 1


def calibrate(
    engine: Engine,
    asset: Asset,
    *,
    min_train: int = 500,
    refit_every: int = 63,
    n_paths: int = 2000,
) -> int:
    """Replay the simulator over history and store the coverage table. Returns rows changed."""
    with session_scope(engine) as session:
        observations = build_regime_observations(session, asset)
    clean = observations.dropna(subset=list(regime.FEATURES))
    steps = calibration.HORIZON_STEPS[asset.asset_class]
    if len(clean) <= min_train + max(steps.values()):
        log.warning("calibration_skipped", symbol=asset.symbol, days=len(clean))
        return 0
    forecasts = calibration.walk_forward_forecasts(
        clean,
        tuple(steps.values()),
        min_train=min_train,
        refit_every=refit_every,
        n_paths=n_paths,
    )
    horizon_of = {count: days for days, count in steps.items()}
    rows = [
        {
            "symbol": asset.symbol,
            "model_version": simulator.MODEL_VERSION,
            **row.model_dump(exclude={"first_origin", "last_origin"}),
            "first_origin": pd.Timestamp(row.first_origin).date(),
            "last_origin": pd.Timestamp(row.last_origin).date(),
        }
        for row in calibration.evaluate(forecasts, horizon_of, pd.DatetimeIndex(clean.index))
    ]
    if not rows:
        return 0
    measured = ("empirical", "empirical_conformal", "n", "conformal_miss_rate", "last_origin")
    with session_scope(engine) as session:
        statement = insert(CalibrationReport).values(rows)
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[
                CalibrationReport.symbol,
                CalibrationReport.model_version,
                CalibrationReport.horizon_days,
                CalibrationReport.nominal,
            ],
            set_={
                **{
                    c.name: getattr(excluded, c.name)
                    for c in CalibrationReport.__table__.columns
                    if not c.primary_key and c.name != "computed_at"
                },
                "computed_at": func.now(),
            },
            where=tuple_(*(getattr(CalibrationReport, name) for name in measured)).is_distinct_from(
                tuple_(*(getattr(excluded, name) for name in measured))
            ),
        ).returning(CalibrationReport.horizon_days)
        changed = len(session.execute(upsert).all())
    log.info("calibration_stored", symbol=asset.symbol, rows=len(rows), changed=changed)
    return changed


def has_calibration(session: Session, symbol: str) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(CalibrationReport)
            .where(
                CalibrationReport.symbol == symbol,
                CalibrationReport.model_version == simulator.MODEL_VERSION,
            )
        )
        or 0
    ) > 0


def latest(session: Session, symbol: str) -> Simulation | None:
    return session.scalars(
        select(Simulation)
        .where(Simulation.symbol == symbol)
        .order_by(Simulation.as_of.desc(), Simulation.created_at.desc())
        .limit(1)
    ).first()


def run(engine: Engine, universe: Universe, *, recalibrate: bool = False) -> int:
    """Calibrate where there is no report (or always, with `recalibrate`), then simulate."""
    from radar.pipelines import followed

    changed = 0
    for asset in followed.of(engine, universe):
        with session_scope(engine) as session:
            missing = not has_calibration(session, asset.symbol)
        if recalibrate or missing:
            changed += calibrate(engine, asset)
        changed += simulate(engine, asset)
    return changed
