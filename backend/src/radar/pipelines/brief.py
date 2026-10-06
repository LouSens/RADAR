"""Assemble, write, and store the daily brief (spec F7). All I/O lives here.

The brief is built only from stored results: nothing is computed for it. One row is
kept per day and subject (each market, and the portfolio), replaced if the job runs
again on the same day.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.brief import payload as facts
from radar.brief import writer as brief_writer
from radar.db.models import Brief
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines import signals as signals_job
from radar.signals import detect, track
from radar.universe import Asset, Universe

log = structlog.get_logger(__name__)

SIGNAL_WINDOW_DAYS = 7
PORTFOLIO = "PORTFOLIO"
LEVEL_WORDS = {"low": "low risk", "moderate": "moderate risk", "high": "high risk"}


def _asset_facts(
    session: Session, universe: Universe, asset: Asset, now: datetime
) -> facts.AssetFacts:
    # The summary route already gathers a market's stored answers; the brief reads the
    # same ones so the two can never disagree.
    from radar.api.routes import get_summary

    summary = get_summary(asset.symbol, universe, session)
    since = now - timedelta(days=SIGNAL_WINDOW_DAYS)
    recent = [
        (signal, record)
        for signal, record in signals_job.recent(session, symbol=asset.symbol, limit=20)
        if signal.ts >= since and signal.type in detect.FEED_TYPES
    ]
    signals = []
    for signal, record in recent:
        scored = track.TrackRecord.model_validate(record.payload) if record is not None else None
        signals.append(
            facts.SignalFacts(
                type=signal.type,
                variant=signal.variant,
                days_ago=max(0, (now.date() - signal.ts.date()).days),
                occurrences=scored.n if scored else 0,
                verdict=scored.verdict if scored else "not enough occurrences",
                size_verdict=scored.size_verdict if scored else "not enough occurrences",
            )
        )
    return facts.AssetFacts(
        symbol=asset.symbol,
        name=asset.name.split(" (")[0],
        state=facts.StateFacts(
            label=summary.state.label,
            probability_percent=min(round(summary.state.probability * 100), 99),
            more_than=summary.state.probability > 0.995,
            days_in_state=summary.state.days_in_state,
        )
        if summary.state
        else None,
        outlook=facts.OutlookFacts(
            horizon_days=summary.outlook.horizon_days,
            held=round(summary.outlook.level * 10),
            out_of=10,
            low=_shown(summary.outlook.low),
            high=_shown(summary.outlook.high),
            price=_shown(summary.outlook.start_price),
        )
        if summary.outlook
        else None,
        swings=facts.SwingsFacts(typical_day_percent=round(summary.swings.forecast * 100, 1))
        if summary.swings
        else None,
        risk=facts.RiskFacts(
            loss_percent=round(summary.risk.limit * 100, 1),
            one_in=round(1 / (1 - summary.risk.level)),
        )
        if summary.risk
        else None,
        signals=signals,
        signal_window_days=SIGNAL_WINDOW_DAYS,
    )


def _shown(value: float) -> float:
    """A dollar figure as the text will show it: whole dollars from a thousand up."""
    return float(round(value)) if abs(value) >= 1000 else round(value, 2)


def _off_target(analysis: portfolio_job.Analysis) -> tuple[str | None, list[str]]:
    plan = analysis.plan
    if plan is None or plan.target is None:
        return None, []
    target = plan.target
    name = (
        "a mix of your own"
        if target.weights or target.level is None
        else LEVEL_WORDS.get(target.level, target.level)
    )
    found = []
    for signal in plan.signals:
        if signal.kind == "drift":
            found.append(
                "at least one holding is more than 5 points of the whole from its target share"
            )
        elif signal.kind == "turbulent":
            found.append("part of it is in a market that is turbulent right now")
        else:
            found.append("it is moving more or less than the target's range")
    return name, list(dict.fromkeys(found))


def _portfolio_facts(session: Session) -> facts.PortfolioFacts | None:
    analysis = portfolio_job.stored_analysis(session)
    if analysis is None:
        return None
    level = analysis.risk_level
    month = (
        next((h for h in analysis.simulation.horizons if h.summary.steps == 30), None)
        if analysis.simulation
        else None
    )
    eighty = next((i for i in month.summary.intervals if i.level == 0.8), None) if month else None
    target, off = _off_target(analysis)
    return facts.PortfolioFacts(
        value=_shown(analysis.value),
        risk_level=level.label if level else None,
        times_stocks=round(level.ratio, 2) if level else None,
        typical_day=_shown(analysis.xray.daily_volatility * analysis.covered_value),
        range_days=month.summary.steps if month and eighty else None,
        range_held=8 if eighty else None,
        range_out_of=10 if eighty else None,
        range_low=_shown(eighty.low) if eighty else None,
        range_high=_shown(eighty.high) if eighty else None,
        target=target,
        off_target=off,
    )


def build(session: Session, universe: Universe, now: datetime) -> facts.Payload:
    """Everything the brief may say, from stored results as of now."""
    return facts.Payload(
        day=now.date().isoformat(),
        assets=[_asset_facts(session, universe, asset, now) for asset in universe.primary],
        portfolio=_portfolio_facts(session),
    )


def store(
    session: Session, day: date, payload: facts.Payload, items: list[brief_writer.Item]
) -> int:
    """Upsert one row per subject for the day. Does not commit."""
    by_symbol: dict[str, Any] = {a.symbol: a.model_dump(mode="json") for a in payload.assets}
    if payload.portfolio is not None:
        by_symbol[PORTFOLIO] = payload.portfolio.model_dump(mode="json")
    now = datetime.now(UTC)
    for item in items:
        statement = insert(Brief).values(
            day=day,
            symbol=item.symbol,
            name=item.name,
            payload=by_symbol[item.symbol],
            sentences=[s.model_dump() for s in item.sentences],
            text=item.text,
            writer=item.writer,
            generated_at=now,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[Brief.day, Brief.symbol],
                set_={
                    "name": statement.excluded.name,
                    "payload": statement.excluded.payload,
                    "sentences": statement.excluded.sentences,
                    "text": statement.excluded.text,
                    "writer": statement.excluded.writer,
                    "generated_at": now,
                },
            )
        )
    return len(items)


def run(
    engine: Engine,
    universe: Universe,
    writer: brief_writer.BriefWriter | None = None,
    now: datetime | None = None,
) -> int:
    """Write and store today's brief. Returns the number of items stored."""
    moment = now or datetime.now(UTC)
    with Session(engine) as session:
        payload = build(session, universe, moment)
        items = brief_writer.write(payload, writer)
        stored = store(session, moment.date(), payload, items)
        session.commit()
    log.info("brief_done", day=moment.date().isoformat(), items=stored)
    return stored


def latest(session: Session) -> list[Brief]:
    """The most recent day's rows, markets first in the order stored, portfolio last."""
    day = session.scalar(select(Brief.day).order_by(Brief.day.desc()).limit(1))
    if day is None:
        return []
    rows = list(session.scalars(select(Brief).where(Brief.day == day).order_by(Brief.id)))
    return sorted(rows, key=lambda row: row.symbol == PORTFOLIO)
