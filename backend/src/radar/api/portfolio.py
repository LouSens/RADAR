"""Portfolio routes under /api/v1/portfolio.

Reading routes return stored results. Saving holdings is the one place a calculation
runs inside a request: the analysis is recomputed and stored there, so that every later
read is only a read.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from radar.api.routes import SessionDep, UniverseDep
from radar.models import allocation
from radar.models.holdings import (
    CASH,
    CASH_NAME,
    CsvSource,
    Holding,
    Holdings,
    HoldingsSource,
    ManualSource,
    Unsupported,
)
from radar.pipelines import portfolio as job
from radar.pipelines import rebalance
from radar.pipelines.datasets import build_mixed_panel
from radar.providers.binance import BinanceError, Leveraged, Wallet
from radar.universe import Universe

router = APIRouter(prefix="/api/v1/portfolio")

MAX_CSV_CHARACTERS = 200_000


class SupportedAsset(BaseModel):
    symbol: str
    name: str
    asset_class: Literal["crypto", "stock", "cash"]


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
    # True when a Binance key is configured, so holdings can be read from the exchange.
    binance_available: bool = False
    # Open leveraged exposure from the last exchange read.
    leveraged: list[Leveraged] = []
    # The exchange's own dollar total per wallet at the last read, to check against.
    wallets: list[Wallet] = []


class HoldingsIn(BaseModel):
    holdings: list[Holding] = Field(max_length=200)


class TargetIn(BaseModel):
    # A risk level to hold the portfolio against, or null.
    level: allocation.Level | None = None
    # How the holdings are split among themselves under a level.
    split: allocation.Method = "current"
    # Or a mix of the user's own: each holding's share of the whole, cash being the
    # rest. With neither a level nor a mix, the target is cleared.
    weights: dict[str, float] | None = Field(default=None, max_length=50)


class WhatIfIn(BaseModel):
    # Each holding's share of the whole, from 0 to 1. Cash is whatever is left over.
    weights: dict[str, float] = Field(max_length=50)


class TagsIn(BaseModel):
    # Core or satellite by symbol; null clears a tag. Holdings not named keep theirs.
    tags: dict[str, Literal["core", "satellite"] | None] = Field(max_length=200)


class CsvIn(BaseModel):
    # The text of the file. The browser reads the file; nothing is uploaded as a file.
    csv: str = Field(max_length=MAX_CSV_CHARACTERS)


def _supported(universe: Universe) -> list[SupportedAsset]:
    return [
        SupportedAsset(symbol=a.symbol, name=a.name, asset_class=a.asset_class)
        for a in universe.assets
    ] + [SupportedAsset(symbol=CASH, name=CASH_NAME, asset_class="cash")]


def get_binance_reader() -> job.Reader | None:
    return job.binance_reader()


def get_asset_finder(request: Request) -> job.Finder | None:
    return job.asset_finder(request.app.state.engine)


BinanceDep = Annotated[job.Reader | None, Depends(get_binance_reader)]
FinderDep = Annotated[job.Finder | None, Depends(get_asset_finder)]


def _store(
    session: Session, universe: Universe, source: HoldingsSource, *, binance: bool
) -> PortfolioOut:
    read = job.save(session, source)
    return _finish(session, universe, read, binance=binance)


def _finish(session: Session, universe: Universe, read: Holdings, *, binance: bool) -> PortfolioOut:
    problem = job.refresh(session, universe) if read.holdings else None
    session.commit()
    return PortfolioOut(
        source=read.source,
        # As stored, so that tags kept from before are on them.
        holdings=sorted(job.stored_holdings(session)[1], key=lambda h: h.symbol),
        unsupported=read.unsupported,
        supported=_supported(universe),
        problem=problem,
        binance_available=binance,
        leveraged=[Leveraged.model_validate(p) for p in job.stored_leveraged(session)],
        wallets=[Wallet.model_validate(w) for w in job.stored_wallets(session)],
    )


@router.get("", response_model=PortfolioOut)
def get_portfolio(universe: UniverseDep, session: SessionDep, binance: BinanceDep) -> PortfolioOut:
    """The saved holdings and the assets that can be held."""
    source, holdings = job.stored_holdings(session)
    problem = (
        "These holdings do not share enough price history to analyse yet."
        if holdings and job.stored_analysis(session) is None
        else None
    )
    return PortfolioOut(
        source=source,
        holdings=holdings,
        supported=_supported(universe),
        problem=problem,
        binance_available=binance is not None,
        leveraged=[Leveraged.model_validate(p) for p in job.stored_leveraged(session)],
        wallets=[Wallet.model_validate(w) for w in job.stored_wallets(session)],
    )


@router.put("", response_model=PortfolioOut)
def put_portfolio(
    body: HoldingsIn, universe: UniverseDep, session: SessionDep, binance: BinanceDep
) -> PortfolioOut:
    """Replace the holdings with these, and analyse them."""
    known = [a.symbol for a in universe.assets]
    return _store(
        session, universe, ManualSource(body.holdings, known), binance=binance is not None
    )


@router.post("/import", response_model=PortfolioOut)
def import_portfolio(
    body: CsvIn, universe: UniverseDep, session: SessionDep, binance: BinanceDep
) -> PortfolioOut:
    """Replace the holdings with those in a CSV file's text, and analyse them."""
    known = [a.symbol for a in universe.assets]
    try:
        return _store(session, universe, CsvSource(body.csv, known), binance=binance is not None)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/binance", response_model=PortfolioOut)
def read_binance(
    universe: UniverseDep, session: SessionDep, binance: BinanceDep, finder: FinderDep
) -> PortfolioOut:
    """Replace the holdings with what the Binance account holds. This only reads.

    A holding RADAR does not know yet is looked up in the market data and its history
    fetched, which can take up to a minute the first time it is seen.
    """
    if binance is None:
        raise HTTPException(status_code=409, detail="No Binance key is configured.")
    try:
        reading, universe = job.read_exchange(session, universe, binance, finder)
    except BinanceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    job.store(
        session,
        reading.holdings,
        [p.model_dump() for p in reading.leveraged],
        [w.model_dump() for w in reading.wallets],
    )
    return _finish(session, universe, reading.holdings, binance=True)


def _checked(weights: dict[str, float], universe: Universe) -> dict[str, float]:
    """Shares that are sensible: known holdings, nothing negative, at most 100% in all."""
    known = {a.symbol for a in universe.assets} | {CASH}
    unknown = sorted(set(weights) - known)
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"RADAR has no price history for {', '.join(unknown)}."
        )
    if any(not (0.0 <= w <= 1.0) for w in weights.values()):
        raise HTTPException(status_code=422, detail="Each share must be between 0% and 100%.")
    shares = {s: w for s, w in weights.items() if s != CASH and w > 0}
    if sum(shares.values()) > 1.0 + 1e-6:
        raise HTTPException(status_code=422, detail="The shares add up to more than 100%.")
    if not shares:
        raise HTTPException(status_code=422, detail="Give at least one holding a share.")
    return shares


@router.post("/what-if", response_model=job.WhatIf)
def post_what_if(body: WhatIfIn, universe: UniverseDep, session: SessionDep) -> job.WhatIf:
    """The risk figures for a mix the user is trying out. Nothing is saved or traded."""
    shares = _checked(body.weights, universe)
    analysis = job.stored_analysis(session)
    if analysis is None:
        raise HTTPException(status_code=409, detail="Save your holdings first.")
    try:
        return job.what_if(shares, analysis.value, build_mixed_panel(session, universe), universe)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/target", response_model=job.Analysis)
def put_target(body: TargetIn, universe: UniverseDep, session: SessionDep) -> job.Analysis:
    """Choose, change, or clear the risk level and split the portfolio is held against.

    Nothing is traded and nothing changes at the exchange: this only sets what the
    portfolio is compared with.
    """
    weights = _checked(body.weights, universe) if body.weights is not None else None
    target = (
        None
        if body.level is None and weights is None
        else rebalance.stamped(
            None if weights is not None else body.level, body.split, weights, datetime.now(UTC)
        )
    )
    if not job.set_target(session, target):
        raise HTTPException(status_code=409, detail="There are no holdings yet.")
    problem = job.refresh(session, universe)
    session.commit()
    analysis = job.stored_analysis(session)
    if problem or analysis is None:
        raise HTTPException(status_code=409, detail=problem or "No portfolio analysis yet")
    return analysis


@router.put("/tags", response_model=job.Analysis)
def put_tags(body: TagsIn, universe: UniverseDep, session: SessionDep) -> job.Analysis:
    """Tag holdings as core or satellite. The tags are kept by symbol, so reading the
    holdings again does not lose them. Nothing is traded."""
    if not job.set_tags(session, dict(body.tags)):
        raise HTTPException(status_code=409, detail="There are no holdings yet.")
    problem = job.refresh(session, universe)
    session.commit()
    analysis = job.stored_analysis(session)
    if problem or analysis is None:
        raise HTTPException(status_code=409, detail=problem or "No portfolio analysis yet")
    return analysis


@router.get("/analysis", response_model=job.Analysis)
def get_analysis(session: SessionDep) -> job.Analysis:
    """Where the portfolio's risk comes from, its loss limits, and past episodes replayed."""
    analysis = job.stored_analysis(session)
    if analysis is None:
        raise HTTPException(status_code=404, detail="No portfolio analysis yet")
    return analysis
