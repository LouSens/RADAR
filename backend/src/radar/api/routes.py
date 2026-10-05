"""REST and WebSocket routes under /api/v1.

Routes read stored results only. No model runs inside a request.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import AwareDatetime
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from radar.api.live import LiveHub
from radar.api.schemas import (
    AssetOut,
    BarOut,
    BarsOut,
    CalibrationOut,
    CalibrationRowOut,
    HealthOut,
    LevelIn,
    LevelOut,
    QualitySummary,
    RegimeEvaluationOut,
    RegimeModelOut,
    RegimeOut,
    RegimePoint,
    RegimeStateOut,
    SeriesStatus,
    SimulationOut,
    VolatilityHorizonOut,
    VolatilityOut,
    VolatilityPoint,
    VolatilityScoreOut,
)
from radar.db.models import (
    Bar,
    CalibrationReport,
    DataQualityReport,
    IngestionRun,
    RegimeState,
    VolatilityForecast,
)
from radar.models import simulator
from radar.pipelines import simulation as simulation_job
from radar.pipelines import volatility as volatility_job
from radar.pipelines.regime import current_model
from radar.universe import Asset, Universe

router = APIRouter(prefix="/api/v1")

MAX_BARS = 5_000
BAR_LENGTH = {"1Hour": timedelta(hours=1), "1Day": timedelta(days=1)}
# How long after a bar ends a series may sit before it is called stale.
CRYPTO_GRACE = timedelta(hours=3)
STOCK_GRACE = timedelta(days=5)  # covers weekends and market holidays


def slug_of(symbol: str) -> str:
    return symbol.lower().replace("/", "-")


def get_universe(request: Request) -> Universe:
    universe: Universe = request.app.state.universe
    return universe


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


UniverseDep = Annotated[Universe, Depends(get_universe)]
SessionDep = Annotated[Session, Depends(get_session)]


def find_asset(universe: Universe, symbol: str) -> Asset:
    """Resolve a canonical symbol ("BTC/USD") or its slug ("btc-usd")."""
    wanted = slug_of(symbol)
    for asset in universe.assets:
        if slug_of(asset.symbol) == wanted:
            return asset
    raise HTTPException(status_code=404, detail=f"Unknown asset: {symbol}")


def asset_out(asset: Asset) -> AssetOut:
    return AssetOut(
        symbol=asset.symbol,
        slug=slug_of(asset.symbol),
        name=asset.name,
        asset_class=asset.asset_class,
        is_primary=asset.is_primary,
        history_start=asset.history_start,
        news_start=asset.news_start,
        trades_continuously=asset.asset_class == "crypto",
    )


@router.get("/assets", response_model=list[AssetOut])
def list_assets(universe: UniverseDep) -> list[AssetOut]:
    """The configured universe, primary assets first."""
    ordered = sorted(universe.assets, key=lambda a: not a.is_primary)
    return [asset_out(asset) for asset in ordered]


@router.get("/assets/{symbol:path}/bars", response_model=BarsOut)
def get_bars(
    symbol: str,
    universe: UniverseDep,
    session: SessionDep,
    timeframe: Annotated[str, Query(pattern="^(1Hour|1Day)$")] = "1Hour",
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_BARS)] = 500,
) -> BarsOut:
    """Stored bars in time order. Without `start`, the latest `limit` bars."""
    asset = find_asset(universe, symbol)
    if timeframe not in universe.timeframes_for(asset):
        raise HTTPException(status_code=404, detail=f"{asset.symbol} has no {timeframe} bars")
    query = select(Bar).where(Bar.symbol == asset.symbol, Bar.timeframe == timeframe)
    if start is not None:
        query = query.where(Bar.ts >= start)
    if end is not None:
        query = query.where(Bar.ts <= end)
    if start is not None:
        rows = list(session.scalars(query.order_by(Bar.ts).limit(limit)))
    else:
        rows = list(session.scalars(query.order_by(Bar.ts.desc()).limit(limit)))[::-1]
    return BarsOut(
        symbol=asset.symbol,
        timeframe=timeframe,
        source=rows[0].loc if rows else None,
        count=len(rows),
        bars=[
            BarOut(
                ts=r.ts,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                is_quote_only=r.is_quote_only,
                is_outlier=r.is_outlier,
            )
            for r in rows
        ],
    )


@router.get("/assets/{symbol:path}/regime", response_model=RegimeOut)
def get_regime(
    symbol: str,
    universe: UniverseDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=5000)] = 365,
) -> RegimeOut:
    """The current market regime, its history, and how the model has measured."""
    asset = find_asset(universe, symbol)
    registered = current_model(session, asset.symbol)
    if registered is None:
        raise HTTPException(status_code=404, detail=f"No regime model for {asset.symbol} yet")
    rows = list(
        session.scalars(
            select(RegimeState)
            .where(RegimeState.symbol == asset.symbol, RegimeState.model_id == registered.id)
            .order_by(RegimeState.ts.desc())
            .limit(days)
        )
    )[::-1]
    if not rows:
        raise HTTPException(status_code=404, detail=f"No regime readings for {asset.symbol} yet")
    latest = rows[-1]
    streak = 0
    for row in reversed(rows):
        if row.label != latest.label:
            break
        streak += 1
    walk = registered.metrics.get("walk_forward")
    return RegimeOut(
        symbol=asset.symbol,
        as_of=latest.ts,
        label=latest.label,
        probability=latest.probability,
        probabilities=latest.probs,
        days_in_state=streak,
        states=[RegimeStateOut.model_validate(s) for s in registered.metrics["states"]],
        history=[RegimePoint(ts=r.ts, label=r.label, probability=r.probability) for r in rows],
        model=RegimeModelOut(
            version=registered.version,
            trained_at=registered.trained_at,
            train_start=registered.train_start,
            train_end=registered.train_end,
            n_train=registered.params["n_train"],
            bic_by_states=registered.metrics["bic_by_states"],
        ),
        evaluation=RegimeEvaluationOut.model_validate(walk) if walk else None,
    )


@router.get("/assets/{symbol:path}/simulation", response_model=SimulationOut)
def get_simulation(symbol: str, universe: UniverseDep, session: SessionDep) -> SimulationOut:
    """The latest stored simulator run: the outcome distribution at each horizon."""
    asset = find_asset(universe, symbol)
    run = simulation_job.latest(session, asset.symbol)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No simulation for {asset.symbol} yet")
    return SimulationOut.model_validate(
        {
            "symbol": asset.symbol,
            "as_of": run.as_of,
            "start_price": run.start_price,
            "n_paths": run.n_paths,
            "seed": run.seed,
            "model_version": run.model_version,
            "horizons": run.horizons,
            "fan": run.fan,
        }
    )


@router.post("/assets/{symbol:path}/simulation/level", response_model=LevelOut)
def post_simulation_level(
    symbol: str, body: LevelIn, universe: UniverseDep, session: SessionDep
) -> LevelOut:
    """Chances of ending beyond, and of touching, a price level. Counted from stored paths."""
    asset = find_asset(universe, symbol)
    run = simulation_job.latest(session, asset.symbol)
    if run is None or run.paths is None:
        raise HTTPException(status_code=404, detail=f"No simulation for {asset.symbol} yet")
    steps = next((h["steps"] for h in run.horizons if h["horizon_days"] == body.horizon_days), None)
    if steps is None:
        raise HTTPException(status_code=422, detail="That horizon is not simulated")
    result = simulator.level_probabilities(
        simulation_job.decode_paths(run), steps, run.start_price, body.level
    )
    return LevelOut(
        symbol=asset.symbol,
        as_of=run.as_of,
        start_price=run.start_price,
        level=body.level,
        horizon_days=body.horizon_days,
        steps=steps,
        n_paths=run.n_paths,
        ends_above=result.ends_above,
        ends_below=result.ends_below,
        touches=result.touches,
    )


@router.get("/assets/{symbol:path}/calibration", response_model=CalibrationOut)
def get_calibration(symbol: str, universe: UniverseDep, session: SessionDep) -> CalibrationOut:
    """How often the simulator's past ranges contained what happened."""
    asset = find_asset(universe, symbol)
    rows = list(
        session.scalars(
            select(CalibrationReport)
            .where(
                CalibrationReport.symbol == asset.symbol,
                CalibrationReport.model_version == simulator.MODEL_VERSION,
            )
            .order_by(CalibrationReport.horizon_days, CalibrationReport.nominal)
        )
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No calibration for {asset.symbol} yet")
    return CalibrationOut(
        symbol=asset.symbol,
        model_version=simulator.MODEL_VERSION,
        computed_at=max(r.computed_at for r in rows),
        rows=[CalibrationRowOut.model_validate(r, from_attributes=True) for r in rows],
    )


@router.get("/assets/{symbol:path}/volatility", response_model=VolatilityOut)
def get_volatility(
    symbol: str,
    universe: UniverseDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=5000)] = 365,
) -> VolatilityOut:
    """The volatility forecast, past forecasts against what happened, and model scores."""
    asset = find_asset(universe, symbol)
    registered = volatility_job.current_model(session, asset.symbol)
    if registered is None:
        raise HTTPException(status_code=404, detail=f"No volatility forecast for {asset.symbol}")
    steps = volatility_job.HORIZON_STEPS[asset.asset_class]
    horizons = []
    for horizon_days, evaluation in sorted(
        registered.metrics["horizons"].items(), key=lambda item: int(item[0])
    ):
        rows = list(
            session.scalars(
                select(VolatilityForecast)
                .where(
                    VolatilityForecast.symbol == asset.symbol,
                    VolatilityForecast.horizon_days == int(horizon_days),
                    VolatilityForecast.model == evaluation["shown"],
                )
                .order_by(VolatilityForecast.ts.desc())
                .limit(days)
            )
        )[::-1]
        if not rows:
            continue
        known = [r.realised for r in rows if r.realised is not None]
        horizons.append(
            VolatilityHorizonOut(
                horizon_days=int(horizon_days),
                steps=steps[int(horizon_days)],
                shown=evaluation["shown"],
                reason=evaluation["reason"],
                forecast=rows[-1].forecast,
                last_realised=known[-1] if known else None,
                history=[
                    VolatilityPoint(ts=r.ts, forecast=r.forecast, realised=r.realised) for r in rows
                ],
                n=evaluation["n"],
                first_day=evaluation["first_day"],
                last_day=evaluation["last_day"],
                scores=[VolatilityScoreOut.model_validate(s) for s in evaluation["scores"]],
            )
        )
    if not horizons:
        raise HTTPException(status_code=404, detail=f"No volatility forecast for {asset.symbol}")
    latest = session.scalar(
        select(func.max(VolatilityForecast.ts)).where(VolatilityForecast.symbol == asset.symbol)
    )
    return VolatilityOut.model_validate(
        {
            "symbol": asset.symbol,
            "as_of": latest,
            "model_version": registered.version,
            "horizons": horizons,
        }
    )


def series_status(session: Session, universe: Universe, now: datetime) -> list[SeriesStatus]:
    rows = session.execute(
        select(
            Bar.symbol, Bar.timeframe, func.count(), func.min(Bar.ts), func.max(Bar.ts)
        ).group_by(Bar.symbol, Bar.timeframe)
    ).all()
    stored = {(symbol, timeframe): (n, first, last) for symbol, timeframe, n, first, last in rows}

    latest = (
        select(
            DataQualityReport.symbol,
            DataQualityReport.check,
            DataQualityReport.detail,
            func.row_number()
            .over(
                partition_by=(DataQualityReport.symbol, DataQualityReport.check),
                order_by=DataQualityReport.ts.desc(),
            )
            .label("rank"),
        )
        .where(DataQualityReport.check.like("gaps:%"))
        .subquery()
    )
    missing = {
        (symbol, check.split(":", 1)[1]): detail.get("missing_share")
        for symbol, check, detail in session.execute(
            select(latest.c.symbol, latest.c.check, latest.c.detail).where(latest.c.rank == 1)
        )
    }

    statuses = []
    for asset in universe.assets:
        for timeframe in universe.timeframes_for(asset):
            if (asset.symbol, timeframe) not in stored:
                continue
            count, first, last = stored[(asset.symbol, timeframe)]
            lag = now - (last + BAR_LENGTH[timeframe])
            # A crypto series may trail by the bar still forming plus a grace period.
            allowed = (
                BAR_LENGTH[timeframe] + CRYPTO_GRACE
                if asset.asset_class == "crypto"
                else STOCK_GRACE
            )
            statuses.append(
                SeriesStatus(
                    symbol=asset.symbol,
                    timeframe=timeframe,
                    is_primary=asset.is_primary,
                    bars=count,
                    first_ts=first,
                    last_ts=last,
                    lag_seconds=lag.total_seconds(),
                    stale=lag > allowed,
                    missing_share=missing.get((asset.symbol, timeframe)),
                )
            )
    return statuses


def quality_summary(session: Session) -> QualitySummary:
    last_run = session.scalar(select(func.max(DataQualityReport.ts)))
    if last_run is None:
        return QualitySummary(last_run=None, findings=0, warnings=0, failures=0)
    # One job run writes all its rows within moments of each other.
    recent = session.execute(
        select(DataQualityReport.status, func.count())
        .where(DataQualityReport.ts >= last_run - timedelta(minutes=5))
        .group_by(DataQualityReport.status)
    ).all()
    counts: dict[str, int] = {row[0]: row[1] for row in recent}
    return QualitySummary(
        last_run=last_run,
        findings=sum(counts.values()),
        warnings=counts.get("warn", 0),
        failures=counts.get("fail", 0),
    )


@router.get("/health", response_model=HealthOut)
def health(request: Request, universe: UniverseDep, session: SessionDep) -> HealthOut:
    """Pipeline and data status. Always answers, even when the database is down."""
    now = datetime.now(UTC)
    hub: LiveHub = request.app.state.hub
    try:
        session.execute(text("SELECT 1"))
        series = series_status(session, universe, now)
        quality = quality_summary(session)
        last_sync = session.scalar(
            select(func.max(IngestionRun.finished_at)).where(IngestionRun.status != "failed")
        )
    except SQLAlchemyError:
        return HealthOut(
            status="down",
            generated_at=now,
            database=False,
            last_sync=None,
            stream_clients=hub.client_count,
            quality=QualitySummary(last_run=None, findings=0, warnings=0, failures=0),
            series=[],
        )
    primary = [s for s in series if s.is_primary]
    expected = sum(len(universe.timeframes_for(a)) for a in universe.primary)
    degraded = any(s.stale for s in primary) or len(primary) < expected or quality.failures > 0
    return HealthOut(
        status="degraded" if degraded else "ok",
        generated_at=now,
        database=True,
        last_sync=last_sync,
        stream_clients=hub.client_count,
        quality=quality,
        series=series,
    )


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    """Live bars and new articles, as JSON messages with a `type` field."""
    hub: LiveHub = websocket.app.state.hub
    await hub.connect(websocket)
    try:
        await websocket.send_json({"type": "hello"})
        while True:
            await websocket.receive_text()  # clients only listen; this waits for disconnect
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)
