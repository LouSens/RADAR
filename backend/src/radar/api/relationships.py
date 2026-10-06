"""Routes for how the markets move together. They read stored results only."""

from fastapi import APIRouter, HTTPException

from radar.api.routes import SessionDep, UniverseDep, find_asset
from radar.pipelines import news_volatility as news_job
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


@router.get("/assets/{symbol:path}/news-and-swings", response_model=news_job.NewsTest)
def get_news_test(symbol: str, universe: UniverseDep, session: SessionDep) -> news_job.NewsTest:
    """Whether adding news improved the forecast of this market's daily swings."""
    asset = find_asset(universe, symbol)
    stored = news_job.current(session, asset.symbol)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No news test for {asset.symbol} yet")
    return news_job.NewsTest.model_validate({**stored.metrics, "computed_at": stored.trained_at})
