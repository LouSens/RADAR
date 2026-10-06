"""Detect signals and keep score of what followed them (spec F7). All I/O lives here.

One run replays each market's history with the detectors, stores every day a rule
fired, and recomputes the track record of each kind of signal. Running it twice over
the same data stores the same rows.
"""

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import RegimeState, Signal, SignalTrackRecord
from radar.features.calendars import NEW_YORK
from radar.features.returns import log_returns
from radar.pipelines.datasets import build_regime_observations, load_field, stock_daily
from radar.pipelines.event_study import daily_inputs
from radar.pipelines.regime import current_model, day_end
from radar.signals import detect, track
from radar.universe import Asset, Universe

log = structlog.get_logger(__name__)

HOUR = pd.Timedelta(hours=1)
# How far ahead outcomes are measured: the next day and the next week, in the days each
# market trades.
HORIZONS = {"crypto": [(1, "1 day"), (7, "1 week")], "stock": [(1, "1 day"), (5, "1 week")]}


def daily_close(session: Session, asset: Asset) -> pd.Series:
    """Closing price by day: UTC days for crypto, trading sessions for stocks."""
    if asset.asset_class == "crypto":
        return load_field(session, [asset.symbol], "1Day")[asset.symbol].dropna()
    return stock_daily(session, [asset.symbol])[asset.symbol].dropna()


def hourly_returns(session: Session, asset: Asset) -> tuple[pd.Series, pd.Index]:
    """Hourly log returns between consecutive hours, and the day each belongs to."""
    prices = load_field(session, [asset.symbol], "1Hour")[asset.symbol].dropna()
    returns = log_returns(prices, step=HOUR).dropna()
    stamps = pd.DatetimeIndex(returns.index)
    if asset.asset_class == "crypto":
        return returns, stamps.floor("D")
    return returns, stamps.tz_convert(NEW_YORK).tz_localize(None).normalize()


def states(session: Session, asset: Asset) -> pd.DataFrame:
    """Each day's market state as it could have been known that day.

    Walk-forward for the past. For days after the app's current model was fitted, the
    readings that model stored are used, so the newest signals agree with the Current
    state page; those readings were also made without seeing later days.
    """
    observations = build_regime_observations(session, asset)
    result = detect.walk_forward_states(observations)
    registered = current_model(session, asset.symbol)
    if registered is None:
        return result
    rows = session.execute(
        select(RegimeState.ts, RegimeState.label, RegimeState.probability).where(
            RegimeState.symbol == asset.symbol, RegimeState.model_id == registered.id
        )
    ).all()
    if not rows:
        return result
    ends = day_end(asset, pd.DatetimeIndex(observations.index))
    day_of = pd.Series(observations.index, index=ends)
    stored = pd.DataFrame(
        {"label": [r[1] for r in rows], "probability": [float(r[2]) for r in rows]},
        index=pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], utc=True)),
    )
    stored = stored[stored.index.isin(day_of.index)]
    stored.index = pd.Index(day_of.reindex(stored.index).to_numpy())
    cutoff = pd.Timestamp(registered.train_end, tz=observations.index.tz)  # type: ignore[attr-defined]
    recent = stored[stored.index > cutoff]
    if recent.empty:
        return result
    return pd.concat([result[result.index <= cutoff], recent]).sort_index()


def occurrences(session: Session, asset: Asset) -> dict[str, list[detect.Occurrence]]:
    """Every day each rule fired for one market, by signal type."""
    known = states(session, asset)
    hourly, days = hourly_returns(session, asset)
    found: dict[str, list[detect.Occurrence]] = {
        "regime_change": detect.regime_changes(known),
        "abnormal_move": detect.abnormal_moves(hourly, days, known["label"]),
        "sentiment_shock": [],
    }
    tone = daily_inputs(session, asset)["tone"].dropna()
    if len(tone):
        found["sentiment_shock"] = detect.sentiment_shocks(tone)
    return found


def build(
    session: Session, universe: Universe
) -> tuple[list[track.TrackRecord], list[dict[str, Any]]]:
    """Track records for every market, corrected together, and the signal rows."""
    records: list[track.TrackRecord] = []
    rows: list[dict[str, Any]] = []
    for asset in universe.primary:
        close = daily_close(session, asset)
        for type_, found in occurrences(session, asset).items():
            for variant in sorted({o.variant for o in found}):
                days = [o.day for o in found if o.variant == variant]
                records.append(
                    track.record(
                        type_, asset.symbol, variant, days, close, HORIZONS[asset.asset_class]
                    )
                )
            if not found or type_ not in detect.FEED_TYPES:
                continue
            ends = day_end(asset, pd.DatetimeIndex([o.day for o in found]))
            for occurrence, end in zip(found, ends, strict=True):
                if pd.isna(end):
                    continue
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "ts": end.to_pydatetime(),
                        "type": type_,
                        "variant": occurrence.variant,
                        "payload": occurrence.detail,
                    }
                )
    return track.correct_family(records), rows


def store(session: Session, records: list[track.TrackRecord], rows: list[dict[str, Any]]) -> int:
    """Upsert track records and signals. Returns the number of signals stored."""
    now = datetime.now(UTC)
    ids: dict[tuple[str, str, str], int] = {}
    for record in records:
        statement = insert(SignalTrackRecord).values(
            type=record.type,
            symbol=record.symbol,
            variant=record.variant,
            computed_at=now,
            n=record.n,
            verdict=record.verdict,
            payload=record.model_dump(mode="json"),
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[
                SignalTrackRecord.type,
                SignalTrackRecord.symbol,
                SignalTrackRecord.variant,
            ],
            set_={
                "computed_at": now,
                "n": statement.excluded.n,
                "verdict": statement.excluded.verdict,
                "payload": statement.excluded.payload,
            },
        ).returning(SignalTrackRecord.id)
        ids[(record.type, record.symbol, record.variant)] = int(
            session.execute(upsert).scalar_one()
        )
    for start in range(0, len(rows), 1000):
        batch = [
            {**row, "track_record_id": ids.get((row["type"], row["symbol"], row["variant"]))}
            for row in rows[start : start + 1000]
        ]
        statement = insert(Signal).values(batch)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[Signal.symbol, Signal.ts, Signal.type],
                set_={
                    "variant": statement.excluded.variant,
                    "payload": statement.excluded.payload,
                    "track_record_id": statement.excluded.track_record_id,
                },
            )
        )
    # A rule that has changed, or a type no longer shown, leaves rows behind that
    # the replay no longer produces. They go, so the feed is exactly the replay.
    wanted = {(row["symbol"], row["ts"], row["type"]) for row in rows}
    stale = [
        found.id
        for found in session.scalars(select(Signal))
        if (found.symbol, found.ts, found.type) not in wanted
    ]
    if stale:
        session.execute(delete(Signal).where(Signal.id.in_(stale)))
    return len(rows)


def run(engine: Engine, universe: Universe) -> int:
    """Detect, score, and store. Returns the number of signals stored."""
    with Session(engine) as session:
        records, rows = build(session, universe)
        stored = store(session, records, rows)
        session.commit()
    log.info("signals_done", signals=stored, track_records=len(records))
    return stored


def recent(
    session: Session,
    *,
    symbol: str | None = None,
    type_: str | None = None,
    limit: int = 50,
) -> list[tuple[Signal, SignalTrackRecord | None]]:
    """The newest signals first, each with its track record."""
    query = (
        select(Signal, SignalTrackRecord)
        .outerjoin(SignalTrackRecord, Signal.track_record_id == SignalTrackRecord.id)
        .order_by(Signal.ts.desc(), Signal.id.desc())
        .limit(limit)
    )
    if symbol is not None:
        query = query.where(Signal.symbol == symbol)
    if type_ is not None:
        query = query.where(Signal.type == type_)
    return [(row[0], row[1]) for row in session.execute(query).all()]


def track_records(session: Session, type_: str) -> list[SignalTrackRecord]:
    return list(
        session.scalars(
            select(SignalTrackRecord)
            .where(SignalTrackRecord.type == type_)
            .order_by(SignalTrackRecord.symbol, SignalTrackRecord.variant)
        ).all()
    )
