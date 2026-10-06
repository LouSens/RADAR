"""Routes for signals and their track records. They read stored results only."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BaseModel

from radar.api.routes import SessionDep, UniverseDep, find_asset
from radar.db.models import SignalTrackRecord
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines import rebalance
from radar.pipelines import signals as job
from radar.signals import detect, track

router = APIRouter(prefix="/api/v1")

SignalType = Literal["regime_change", "abnormal_move", "sentiment_shock"]


class RecordSummary(BaseModel):
    """Enough of a track record to quote beside a signal."""

    n: int
    verdict: track.Verdict
    size_verdict: track.SizeVerdict
    # Typical size of the next day's move after the signal, and on all days.
    mean_size: float | None
    baseline_mean_size: float | None
    # After the signal and on all days: how often the next day ended higher.
    share_positive: float | None
    baseline_share_positive: float | None


class SignalOut(BaseModel):
    id: int
    symbol: str
    name: str
    # When the day the signal describes had ended.
    ts: AwareDatetime
    type: SignalType
    variant: str
    detail: dict[str, Any]
    record: RecordSummary | None


class SignalsOut(BaseModel):
    signals: list[SignalOut]
    # Where the portfolio stands against the user's target. These describe the present
    # and are not forecasts, so they have no track record.
    portfolio: list[rebalance.Signal]


class SignalRecordOut(track.TrackRecord):
    name: str
    computed_at: AwareDatetime


class SignalRecordsOut(BaseModel):
    type: SignalType
    records: list[SignalRecordOut]
    # How many records and horizons were tested together and corrected for.
    tested: int


def _summary(row: SignalTrackRecord | None) -> RecordSummary | None:
    if row is None:
        return None
    record = track.TrackRecord.model_validate(row.payload)
    day = record.horizons[0] if record.horizons else None
    return RecordSummary(
        n=record.n,
        verdict=record.verdict,
        size_verdict=record.size_verdict,
        mean_size=day.signal.mean_size if day else None,
        baseline_mean_size=day.baseline.mean_size if day else None,
        share_positive=day.signal.share_positive if day else None,
        baseline_share_positive=day.baseline.share_positive if day else None,
    )


@router.get("/signals", response_model=SignalsOut)
def get_signals(
    universe: UniverseDep,
    session: SessionDep,
    symbol: str | None = None,
    type: SignalType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> SignalsOut:
    """Recent signals, newest first, each with what followed its kind in the past."""
    wanted = find_asset(universe, symbol).symbol if symbol else None
    rows = job.recent(session, symbol=wanted, type_=type, limit=limit)
    analysis = portfolio_job.stored_analysis(session)
    return SignalsOut(
        signals=[
            SignalOut(
                id=signal.id,
                symbol=signal.symbol,
                name=universe.get(signal.symbol).name,
                ts=signal.ts,
                type=signal.type,
                variant=signal.variant,
                detail=signal.payload,
                record=_summary(record),
            )
            for signal, record in rows
        ],
        portfolio=analysis.plan.signals if analysis and analysis.plan else [],
    )


@router.get("/signals/track-records/{type}", response_model=SignalRecordsOut)
def get_track_records(type: str, universe: UniverseDep, session: SessionDep) -> SignalRecordsOut:
    """What followed one kind of signal in the past, on each market, against all days."""
    if type not in detect.TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown signal type: {type}")
    rows = job.track_records(session, type)
    every = [
        track.TrackRecord.model_validate(r.payload)
        for kind in detect.TYPES
        for r in job.track_records(session, kind)
    ]
    return SignalRecordsOut(
        type=type,
        records=[
            SignalRecordOut(
                **track.TrackRecord.model_validate(r.payload).model_dump(),
                name=universe.get(r.symbol).name,
                computed_at=r.computed_at,
            )
            for r in rows
        ],
        tested=sum(1 for r in every for h in r.horizons if h.signal.n >= track.MIN_OCCURRENCES),
    )
