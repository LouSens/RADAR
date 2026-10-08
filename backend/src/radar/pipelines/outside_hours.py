"""Hourly prices from a second source, for an asset whose own hours have gaps.

PAX Gold has no trade on Alpaca's venue in about one hour in twenty-five, which leaves
about one day in twelve without a usable measure of how much it moved (decision 089).
Binance trades the same coin in nearly every hour. An asset that names a Binance pair
in `hours_from` has its daily movement built from those hours (decision 091). Prices,
returns and everything shown as a price still come from the asset's own bars.

Read without a key through `providers/binance_public.py`, which only sends GET requests
to the pairs listed there.
"""

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import OutsideHour
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.providers import binance_public
from radar.providers.public import PublicReader
from radar.universe import Asset, Universe

log = get_logger(__name__)

VALUES = ("open", "high", "low", "close", "volume")
BATCH = 2000


def source_name(asset: Asset) -> str:
    return f"binance:{asset.hours_from}"


def upsert(session: Session, asset: Asset, bars: pd.DataFrame) -> int:
    """Store hourly bars, or update the ones whose values differ. Returns rows changed."""
    rows = [
        {
            "symbol": asset.symbol,
            "source": source_name(asset),
            "ts": stamp.to_pydatetime(),
            **{name: float(bars[name].iloc[row]) for name in VALUES},
        }
        for row, stamp in enumerate(pd.DatetimeIndex(bars.index))
    ]
    changed = 0
    for start in range(0, len(rows), BATCH):
        statement = insert(OutsideHour).values(rows[start : start + BATCH])
        excluded = statement.excluded
        result = session.execute(
            statement.on_conflict_do_update(
                index_elements=[OutsideHour.symbol, OutsideHour.source, OutsideHour.ts],
                set_={**{name: excluded[name] for name in VALUES}, "received_at": func.now()},
                where=tuple_(*(getattr(OutsideHour, name) for name in VALUES)).is_distinct_from(
                    tuple_(*(excluded[name] for name in VALUES))
                ),
            ).returning(OutsideHour.ts)
        )
        changed += len(result.all())
    return changed


def hourly_close(session: Session, asset: Asset) -> pd.Series:
    """The stored outside hours of an asset: closing price by the hour's start (UTC).
    Empty when the asset names no outside source or none has been read yet."""
    if asset.hours_from is None:
        return pd.Series(dtype=float)
    rows = session.execute(
        select(OutsideHour.ts, OutsideHour.close)
        .where(OutsideHour.symbol == asset.symbol, OutsideHour.source == source_name(asset))
        .order_by(OutsideHour.ts)
    ).all()
    index = pd.DatetimeIndex(pd.to_datetime([ts for ts, _ in rows], utc=True))
    return pd.Series([close for _, close in rows], index=index, dtype=float)


def sync(session: Session, asset: Asset, source: PublicReader, now: datetime) -> int:
    """Read the hours not stored yet, up to the last finished hour. The newest stored
    hour is read again, so a bar first seen while still forming is corrected."""
    if asset.hours_from is None:
        return 0
    last = session.scalar(
        select(func.max(OutsideHour.ts)).where(
            OutsideHour.symbol == asset.symbol, OutsideHour.source == source_name(asset)
        )
    )
    start = last or datetime.combine(asset.history_start, datetime.min.time(), tzinfo=UTC)
    end = pd.Timestamp(now).floor("h").to_pydatetime()
    if start >= end:
        return 0
    bars = binance_public.hourly_bars(
        source, asset.hours_from, int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    )
    return upsert(session, asset, bars) if len(bars) else 0


def run(engine: Engine, universe: Universe, source: PublicReader | None = None) -> int:
    """Bring every asset's outside hours up to date. Returns rows changed."""
    wanted = [asset for asset in universe.assets if asset.hours_from is not None]
    if not wanted:
        return 0
    changed = 0
    now = datetime.now(UTC)
    with source or binance_public.reader() as reading:
        for asset in wanted:
            with session_scope(engine) as session:
                rows = sync(session, asset, reading, now)
            log.info("outside_hours_synced", symbol=asset.symbol, rows=rows)
            changed += rows
    return changed
