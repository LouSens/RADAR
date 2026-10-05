"""Store holdings and analyse the portfolio's risk (spec F6, F10). All I/O lives here.

Holdings arrive through a `HoldingsSource`. Saving them replaces the stored set and
recomputes the analysis, which is kept as one row so that requests only ever read it.
The worker recomputes it as new prices arrive.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import structlog
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.analytics import summary
from radar.db.models import Portfolio, PortfolioAnalysis, PortfolioHolding
from radar.features.panels import MixedPanel
from radar.models import portfolio as model
from radar.models.holdings import Holding, Holdings, HoldingsSource
from radar.models.tail_risk import MIN_WINDOW
from radar.pipelines.datasets import build_mixed_panel
from radar.universe import Universe

log = structlog.get_logger(__name__)

PORTFOLIO_ID = 1


class Position(BaseModel):
    symbol: str
    name: str
    quantity: float
    tag: str | None
    # Price at the close of the last session used, and the holding's value at it.
    price: float
    value: float
    weight: float


class Trusts(BaseModel):
    xray: summary.Trust
    risk: summary.Trust
    stress: summary.Trust


class Analysis(BaseModel):
    """Everything the Portfolio screen shows, as stored."""

    as_of: AwareDatetime
    model_version: str
    value: float
    positions: list[Position]
    xray: model.Xray
    limits: list[model.LimitHorizon]
    stress: list[model.StressResult]
    trust: Trusts


def stored_holdings(session: Session) -> tuple[str | None, list[Holding]]:
    """The saved holdings and where they came from."""
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    if portfolio is None:
        return None, []
    rows = session.scalars(
        select(PortfolioHolding)
        .where(PortfolioHolding.portfolio_id == PORTFOLIO_ID)
        .order_by(PortfolioHolding.symbol)
    ).all()
    return portfolio.source, [
        Holding(
            symbol=r.symbol,
            quantity=r.quantity,
            tag="core" if r.tag == "core" else "satellite" if r.tag == "satellite" else None,
        )
        for r in rows
    ]


def save(session: Session, source: HoldingsSource) -> Holdings:
    """Replace the stored holdings with what the source holds. Does not commit."""
    read = source.read()
    now = datetime.now(UTC)
    session.execute(
        insert(Portfolio)
        .values(id=PORTFOLIO_ID, name="My portfolio", source=read.source, updated_at=now)
        .on_conflict_do_update(
            index_elements=[Portfolio.id], set_={"source": read.source, "updated_at": now}
        )
    )
    session.execute(delete(PortfolioHolding).where(PortfolioHolding.portfolio_id == PORTFOLIO_ID))
    session.execute(delete(PortfolioAnalysis).where(PortfolioAnalysis.portfolio_id == PORTFOLIO_ID))
    if read.holdings:
        session.execute(
            insert(PortfolioHolding),
            [
                {
                    "portfolio_id": PORTFOLIO_ID,
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "tag": h.tag,
                }
                for h in read.holdings
            ],
        )
    return read


def analyse(
    holdings: list[Holding],
    panel: MixedPanel,
    universe: Universe,
    *,
    min_window: int = MIN_WINDOW,
) -> Analysis:
    """The full analysis of a set of holdings on a price panel. Pure given its inputs."""
    symbols = [h.symbol for h in holdings]
    prices = panel.prices[symbols]
    priced = prices.ffill().iloc[-1]
    if priced.isna().any():
        missing = ", ".join(str(s) for s in priced[priced.isna()].index)
        raise model.NotEnoughHistoryError(f"No stored price for {missing}.")
    values = np.array([h.quantity * float(priced[h.symbol]) for h in holdings])
    total = float(values.sum())
    weights = values / total
    returns = panel.returns[symbols]

    xray = model.xray(returns, weights)
    limits = model.loss_limits(model.mix_returns(returns, weights), min_window=min_window)
    episodes = [
        model.Episode(name=e.name, start=e.start, end=e.end) for e in universe.stress_episodes
    ]
    stress = model.stress(prices, weights, episodes)

    day = next((h for h in limits if h.horizon_days == 1), None)
    shown = (
        [
            {
                "reliable": m.backtest.reliable,
                "n": m.backtest.n,
                "breaches": m.backtest.breaches,
                "expected_breaches": m.backtest.expected_breaches,
            }
            for level in day.levels
            for m in level.methods
            if m.method == day.shown
        ]
        if day
        else []
    )
    available = [s for s in stress if s.available]
    return Analysis(
        as_of=pd.Timestamp(panel.prices.index[-1]).to_pydatetime(),
        model_version=model.MODEL_VERSION,
        value=total,
        positions=[
            Position(
                symbol=h.symbol,
                name=universe.get(h.symbol).name,
                quantity=h.quantity,
                tag=h.tag,
                price=float(priced[h.symbol]),
                value=float(values[i]),
                weight=float(weights[i]),
            )
            for i, h in enumerate(holdings)
        ],
        xray=xray,
        limits=limits,
        stress=stress,
        trust=Trusts(
            xray=summary.grade_xray(xray.n_days),
            risk=summary.grade_risk(shown),  # type: ignore[arg-type]
            stress=summary.grade_stress(
                len(available), sum(1 for s in available if s.missing), len(stress)
            ),
        ),
    )


def refresh(session: Session, universe: Universe, panel: MixedPanel | None = None) -> str | None:
    """Recompute and store the analysis of the saved holdings. Does not commit.

    Returns None on success, or one sentence saying why there is no analysis.
    """
    _, holdings = stored_holdings(session)
    session.execute(delete(PortfolioAnalysis).where(PortfolioAnalysis.portfolio_id == PORTFOLIO_ID))
    if not holdings:
        return "There are no holdings yet."
    try:
        result = analyse(holdings, panel or build_mixed_panel(session, universe), universe)
    except model.NotEnoughHistoryError as error:
        return str(error)
    session.add(
        PortfolioAnalysis(
            portfolio_id=PORTFOLIO_ID,
            as_of=result.as_of,
            computed_at=datetime.now(UTC),
            model_version=result.model_version,
            payload=result.model_dump(mode="json"),
        )
    )
    return None


def stored_analysis(session: Session) -> Analysis | None:
    row = session.get(PortfolioAnalysis, PORTFOLIO_ID)
    return None if row is None else Analysis.model_validate(row.payload)


def run(engine: Engine, universe: Universe) -> int:
    """Refresh the stored analysis with the latest prices. Returns 1 when one was stored."""
    with Session(engine) as session:
        problem = refresh(session, universe)
        session.commit()
    if problem:
        log.info("portfolio_skipped", reason=problem)
        return 0
    log.info("portfolio_done")
    return 1
