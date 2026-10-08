"""Portfolio routes under /api/v1/portfolio.

Reading routes return stored results. Saving holdings is the one place a calculation
runs inside a request: the analysis is recomputed and stored there, so that every later
read is only a read.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field
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
from radar.pipelines import account as account_job
from radar.pipelines import check as check_job
from radar.pipelines import discover, rebalance
from radar.pipelines import followed as followed_job
from radar.pipelines import portfolio as job
from radar.pipelines import prices as prices_job
from radar.pipelines import steps as steps_job
from radar.pipelines.datasets import build_mixed_panel
from radar.providers import binance_public
from radar.providers.binance import BinanceError, Leveraged, Wallet
from radar.providers.public import PublicDataError
from radar.universe import Universe

router = APIRouter(prefix="/api/v1/portfolio")

MAX_CSV_CHARACTERS = 200_000


class SupportedAsset(BaseModel):
    symbol: str
    name: str
    asset_class: Literal["crypto", "stock", "cash"]


class PortfolioOut(BaseModel):
    # When the holdings were last read from where they are kept.
    read_at: AwareDatetime | None = None
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


# Holdings on an exchange are read again when the last read is older than this.
STEPS_FRESH = timedelta(minutes=5)


class LostIn(BaseModel):
    # Coins whose units left the account without a sale and are gone for good.
    assets: list[str] = Field(max_length=100)


class RegularBuyingIn(BaseModel):
    # How each purchase is split among assets; the shares are scaled to add up to 100%.
    weights: dict[str, float] = Field(max_length=20)
    # Dollars per purchase.
    amount: float = Field(gt=0, le=1_000_000_000)
    # Trading sessions between purchases: 5 is weekly, 21 monthly.
    every: int = Field(ge=1, le=63)
    purchases: int = Field(ge=2, le=504)


class LookupIn(BaseModel):
    # A ticker as typed: "NVDA", "ETH". Whether it is a stock or a crypto coin is said,
    # because the same letters can be both.
    ticker: str = Field(min_length=1, max_length=12)
    kind: Literal["stock", "crypto"]


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


def get_live_prices() -> prices_job.Reader:
    """The reader of latest trades. Tests replace it so that none calls Alpaca."""
    return prices_job.live


BinanceDep = Annotated[job.Reader | None, Depends(get_binance_reader)]
LivePricesDep = Annotated[prices_job.Reader, Depends(get_live_prices)]
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
        read_at=job.read_at(session),
        # As stored, so that tags kept from before are on them.
        holdings=sorted(job.stored_holdings(session)[1], key=lambda h: h.symbol),
        unsupported=read.unsupported,
        supported=_supported(universe),
        problem=problem,
        binance_available=binance,
        leveraged=[Leveraged.model_validate(p) for p in job.stored_leveraged(session)],
        wallets=[Wallet.model_validate(w) for w in job.stored_wallets(session)],
    )


@router.get("/record", response_model=account_job.Record)
def get_record(session: SessionDep) -> account_job.Record:
    """What the holdings cost, what was made, and how the trades were timed, from the
    exchange's own history. Read from the stored result; nothing is fetched here."""
    record = account_job.stored(session)
    if record is None:
        raise HTTPException(status_code=404, detail="No account record yet")
    return record


def _follow_exchange(
    session: Session, universe: Universe, binance: job.Reader | None, finder: job.Finder | None
) -> Universe:
    """Read the exchange again when the holdings come from it and the last read is old,
    so a purchase or a deposit shows up without anyone asking. If the exchange cannot be
    reached, what is stored is kept. Returns the universe the reading was resolved in."""
    source, _ = job.stored_holdings(session)
    last = job.read_at(session)
    stale = last is None or datetime.now(UTC) - last > STEPS_FRESH
    if binance is None or source != "binance" or not stale:
        return universe
    try:
        reading, universe = job.read_exchange(session, universe, binance, finder)
        job.store(
            session,
            reading.holdings,
            [p.model_dump() for p in reading.leveraged],
            [w.model_dump() for w in reading.wallets],
        )
        job.refresh(session, universe)
        session.commit()
    except BinanceError:
        session.rollback()
    return universe


@router.get("/followed", response_model=list[followed_job.HoldingStanding])
def get_followed(universe: UniverseDep, session: SessionDep) -> list[followed_job.HoldingStanding]:
    """Each holding with how many days of prices it has and whether the models run for
    it yet. They start once a holding has enough days to be checked on unseen ones."""
    return followed_job.standing(session, universe)


@router.get("/steps", response_model=steps_job.Steps)
def get_steps(
    universe: UniverseDep,
    session: SessionDep,
    binance: BinanceDep,
    finder: FinderDep,
    live: LivePricesDep,
) -> steps_job.Steps:
    """Where cash over the plan goes, at what prices, and why. Worked out from the
    portfolio and plan each time it is asked for; nothing is traded.

    When the holdings come from Binance and were last read more than a few minutes ago,
    they are read again first, so a purchase or a deposit shows up without anyone asking
    for it. If Binance cannot be reached, what is stored is used.
    """
    universe = _follow_exchange(session, universe, binance, finder)
    steps = steps_job.current(session, universe, live, datetime.now(UTC))
    if steps is None:
        raise HTTPException(status_code=404, detail="No portfolio analysis yet")
    return steps.model_copy(update={"checked_at": job.read_at(session)})


@router.get("/check/{coin}", response_model=check_job.Check)
def get_check(coin: str, session: SessionDep) -> check_job.Check:
    """Whether a coin's price is high or low against its own last week, month and three
    months, beside the user's own record. Reads public prices; nothing is traded."""
    name = coin.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}", name):
        raise HTTPException(status_code=422, detail="That is not a coin name.")
    try:
        with binance_public.reader() as source:
            bars = check_job.fetch(source, name)
            daily = check_job.fetch_year(source, name) if len(bars) else None
    except PublicDataError:
        raise HTTPException(status_code=404, detail=f"No prices for {name}.") from None
    if len(bars) < check_job.WEEK + 1:
        raise HTTPException(status_code=404, detail=f"No prices for {name}.")
    return check_job.build(name, bars, account_job.stored(session), datetime.now(UTC), daily)


@router.put("/record/lost", response_model=account_job.Record)
def put_lost_coins(body: LostIn, session: SessionDep) -> account_job.Record:
    """Say which coins that left the account without a sale were lost for good. This
    only changes how the record adds up; nothing is sent to any exchange."""
    account_job.set_lost_coins(session, body.assets, datetime.now(UTC))
    session.commit()
    record = account_job.stored(session)
    if record is None:
        raise HTTPException(status_code=404, detail="No account record yet")
    return record


@router.get("", response_model=PortfolioOut)
def get_portfolio(
    universe: UniverseDep, session: SessionDep, binance: BinanceDep, finder: FinderDep
) -> PortfolioOut:
    """The saved holdings and the assets that can be held. Holdings kept on Binance are
    read again first when the last read is more than a few minutes old."""
    universe = _follow_exchange(session, universe, binance, finder)
    source, holdings = job.stored_holdings(session)
    problem = (
        "These holdings do not share enough price history to analyse yet."
        if holdings and job.stored_analysis(session) is None
        else None
    )
    return PortfolioOut(
        source=source,
        read_at=job.read_at(session),
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


@router.post("/regular-buying", response_model=job.RegularBuying)
def post_regular_buying(
    body: RegularBuyingIn, universe: UniverseDep, session: SessionDep
) -> job.RegularBuying:
    """Where a plan of regular purchases might end up, against putting the same total in
    at once. A simulation only: nothing is saved and nothing is bought."""
    if any(w < 0 for w in body.weights.values()):
        raise HTTPException(status_code=422, detail="A share cannot be negative.")
    try:
        return job.regular_buying(
            body.weights,
            body.amount,
            body.every,
            body.purchases,
            build_mixed_panel(session, universe),
            universe,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/lookup", response_model=SupportedAsset)
def post_lookup(
    body: LookupIn, universe: UniverseDep, session: SessionDep, finder: FinderDep
) -> SupportedAsset:
    """Find an asset by its ticker so it can be tried in a mix. One RADAR has not seen
    before is looked up in the market data and its price history fetched, which can
    take up to a minute. This only reads prices."""
    ticker = body.ticker.strip().upper().removesuffix("/USD")
    wanted = ticker if body.kind == "stock" else f"{ticker}/USD"
    known = next(
        (a for a in universe.assets if a.symbol == wanted and a.asset_class == body.kind), None
    )
    if known is None:
        if finder is None:
            raise HTTPException(status_code=409, detail="No market data key is configured.")
        name = f"{discover.STOCK_PREFIX}{ticker}" if body.kind == "stock" else ticker
        found = finder(universe, [name])
        known = next((a for a in found if a.symbol == wanted), None)
    if known is None:
        raise HTTPException(
            status_code=404,
            detail=f"No {body.kind} prices were found for {ticker}.",
        )
    session.commit()
    return SupportedAsset(symbol=known.symbol, name=known.name, asset_class=known.asset_class)


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


@router.get("/analysis", response_model=job.Analysis)
def get_analysis(session: SessionDep) -> job.Analysis:
    """Where the portfolio's risk comes from, its loss limits, and past episodes replayed."""
    analysis = job.stored_analysis(session)
    if analysis is None:
        raise HTTPException(status_code=404, detail="No portfolio analysis yet")
    return analysis
