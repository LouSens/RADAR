"""Routes for how the markets move together. They read stored results only."""

from fastapi import APIRouter, HTTPException

from radar.api.routes import SessionDep, UniverseDep, find_asset
from radar.pipelines import relationships as job

router = APIRouter(prefix="/api/v1")


@router.get("/relationships", response_model=job.Relationships)
def get_relationships(session: SessionDep) -> job.Relationships:
    """Correlations between the markets, risk transmission, and weekend gaps."""
    stored = job.current(session, job.NAME, None)
    if stored is None:
        raise HTTPException(status_code=404, detail="No relationship results yet")
    return job.Relationships.model_validate(stored.metrics)


@router.get("/assets/{symbol:path}/drivers", response_model=job.Drivers)
def get_drivers(symbol: str, universe: UniverseDep, session: SessionDep) -> job.Drivers:
    """Which outside forces this market has been moving with, and how well that held."""
    asset = find_asset(universe, symbol)
    stored = job.current(session, job.DRIVERS_NAME, asset.symbol)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No driver results for {asset.symbol} yet")
    return job.Drivers.model_validate(stored.metrics)
