"""Measure how the markets have behaved around scheduled events, and store the result.

One stored row holds everything the Calendar screen shows about the past. The list of
events still to come is read from the dates file when asked for, not stored.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.analytics import events, summary
from radar.pipelines import relationships
from radar.pipelines.signals import daily_close
from radar.universe import Universe

log = structlog.get_logger(__name__)

NAME = "events"
# Trading days in a week: Bitcoin trades every day, the others on market sessions.
WEEK = {"crypto": 7, "stock": 5}


class Stored(BaseModel):
    """What was found, as stored."""

    results: list[events.EventResult]
    names: dict[str, str]
    # How many comparisons had enough events and were corrected together.
    direction_tests: int
    size_tests: int
    trust: dict[str, summary.Trust]


class Calendar(Stored):
    upcoming: list[events.Upcoming]
    computed_at: AwareDatetime | None = None


def build(session: Session, universe: Universe, kinds: list[events.EventKind]) -> Stored:
    closes = {a.symbol: (daily_close(session, a), WEEK[a.asset_class]) for a in universe.primary}
    measured = [
        events.EventResult(
            key=kind.key,
            name=kind.name,
            markets=[
                events.measure(symbol, close, kind.dates, week)
                for symbol, (close, week) in closes.items()
            ],
        )
        for kind in kinds
    ]
    judged = events.judge(measured)
    direction, size = events.comparisons(judged)
    return Stored(
        results=judged,
        names={a.symbol: a.name for a in universe.primary},
        direction_tests=direction,
        size_tests=size,
        trust={r.key: summary.grade_events([m.n_events for m in r.markets]) for r in judged},
    )


def run(engine: Engine, universe: Universe) -> int:
    """Recompute and store. Returns the number of event kinds stored."""
    kinds = list(events.get_events())
    with Session(engine) as session:
        stored = build(session, universe, kinds)
        days = [m.first_day for r in stored.results for m in r.markets if m.first_day]
        ends = [m.last_day for r in stored.results for m in r.markets if m.last_day]
        today = datetime.now(UTC).date()
        payload: dict[str, Any] = stored.model_dump(mode="json")
        relationships._store(
            session,
            NAME,
            None,
            events.VERSION,
            payload,
            min(days, default=today),
            max(ends, default=today),
        )
        session.commit()
    log.info("events_done", kinds=len(stored.results))
    return len(stored.results)


def calendar(session: Session, now: datetime) -> Calendar | None:
    """The stored findings with the events still to come, or None before the first run."""
    row = relationships.current(session, NAME, None)
    if row is None:
        return None
    stored = Stored.model_validate(row.metrics)
    return Calendar(
        **stored.model_dump(),
        upcoming=events.upcoming(list(events.get_events()), now),
        computed_at=row.trained_at,
    )
