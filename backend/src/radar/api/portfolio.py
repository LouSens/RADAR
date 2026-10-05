"""Portfolio routes under /api/v1/portfolio.

Reading routes return stored results. Saving holdings is the one place a calculation
runs inside a request: the analysis is recomputed and stored there, so that every later
read is only a read.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from radar.api.routes import SessionDep, UniverseDep
from radar.models.holdings import CsvSource, Holding, HoldingsSource, ManualSource, Unsupported
from radar.pipelines import portfolio as job
from radar.universe import Universe

router = APIRouter(prefix="/api/v1/portfolio")

MAX_CSV_CHARACTERS = 200_000


class SupportedAsset(BaseModel):
    symbol: str
    name: str
    asset_class: Literal["crypto", "stock"]


class PortfolioOut(BaseModel):
    # Where the holdings last came from: "manual" or "csv". Null when none are saved.
    source: str | None
    holdings: list[Holding]
    # Entries from the last save or import that could not be used, and why. Not stored.
    unsupported: list[Unsupported] = []
    # Every asset that can be held: the ones RADAR stores prices for.
    supported: list[SupportedAsset]
    # Why there is no analysis, when holdings exist but none could be made.
    problem: str | None = None


class HoldingsIn(BaseModel):
    holdings: list[Holding] = Field(max_length=200)


class CsvIn(BaseModel):
    # The text of the file. The browser reads the file; nothing is uploaded as a file.
    csv: str = Field(max_length=MAX_CSV_CHARACTERS)


def _supported(universe: Universe) -> list[SupportedAsset]:
    return [
        SupportedAsset(symbol=a.symbol, name=a.name, asset_class=a.asset_class)
        for a in universe.assets
    ]


def _store(session: Session, universe: Universe, source: HoldingsSource) -> PortfolioOut:
    read = job.save(session, source)
    problem = job.refresh(session, universe) if read.holdings else None
    session.commit()
    return PortfolioOut(
        source=read.source,
        holdings=sorted(read.holdings, key=lambda h: h.symbol),
        unsupported=read.unsupported,
        supported=_supported(universe),
        problem=problem,
    )


@router.get("", response_model=PortfolioOut)
def get_portfolio(universe: UniverseDep, session: SessionDep) -> PortfolioOut:
    """The saved holdings and the assets that can be held."""
    source, holdings = job.stored_holdings(session)
    problem = (
        "These holdings do not share enough price history to analyse yet."
        if holdings and job.stored_analysis(session) is None
        else None
    )
    return PortfolioOut(
        source=source, holdings=holdings, supported=_supported(universe), problem=problem
    )


@router.put("", response_model=PortfolioOut)
def put_portfolio(body: HoldingsIn, universe: UniverseDep, session: SessionDep) -> PortfolioOut:
    """Replace the holdings with these, and analyse them."""
    known = [a.symbol for a in universe.assets]
    return _store(session, universe, ManualSource(body.holdings, known))


@router.post("/import", response_model=PortfolioOut)
def import_portfolio(body: CsvIn, universe: UniverseDep, session: SessionDep) -> PortfolioOut:
    """Replace the holdings with those in a CSV file's text, and analyse them."""
    known = [a.symbol for a in universe.assets]
    try:
        return _store(session, universe, CsvSource(body.csv, known))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/analysis", response_model=job.Analysis)
def get_analysis(session: SessionDep) -> job.Analysis:
    """Where the portfolio's risk comes from, its loss limits, and past episodes replayed."""
    analysis = job.stored_analysis(session)
    if analysis is None:
        raise HTTPException(status_code=404, detail="No portfolio analysis yet")
    return analysis
