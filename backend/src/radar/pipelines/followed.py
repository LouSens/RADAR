"""Which assets the models run for: the followed markets, and every holding with enough
price history (decision 095).

A model here is only shown with a check on days it had not seen, and those checks start
after 500 days of prices. So a holding is analysed once it has that many, and until then
the screen says how many it has. Nothing is fitted on a short record and passed off as
the same thing.
"""

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.db.session import session_scope
from radar.models.holdings import CASH
from radar.pipelines import discover
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines.signals import daily_close
from radar.universe import Asset, Universe

# Days of prices before a holding is analysed: what the walk-forward checks need
# before their first unseen day (`min_train` in the volatility and risk jobs).
MIN_DAYS = 500


class HoldingStanding(BaseModel):
    """Where one holding stands: analysed, or how far it is from being."""

    symbol: str
    name: str
    days: int
    needed: int = MIN_DAYS
    analysed: bool


def _held(session: Session, universe: Universe) -> list[Asset]:
    """The assets behind the stored holdings, cash left out, in the universe's order."""
    _, holdings = portfolio_job.stored_holdings(session)
    symbols = {h.symbol for h in holdings if h.symbol != CASH}
    return [a for a in discover.extend(universe, session).assets if a.symbol in symbols]


def standing(session: Session, universe: Universe) -> list[HoldingStanding]:
    """Every holding with how many days of prices it has and whether that is enough."""
    found = []
    for asset in _held(session, universe):
        days = len(daily_close(session, asset))
        found.append(
            HoldingStanding(
                symbol=asset.symbol,
                name=asset.name,
                days=days,
                analysed=asset.is_primary or days >= MIN_DAYS,
            )
        )
    return found


def assets(session: Session, universe: Universe) -> list[Asset]:
    """The assets the models run for: the followed markets first, then each other
    holding with enough history."""
    primary = list(universe.primary)
    known = {a.symbol for a in primary}
    enough = {s.symbol for s in standing(session, universe) if s.analysed}
    extra = [a for a in _held(session, universe) if a.symbol in enough and a.symbol not in known]
    return primary + extra


def of(engine: Engine, universe: Universe) -> list[Asset]:
    """`assets`, for a job that has only the engine."""
    with session_scope(engine) as session:
        return assets(session, universe)
