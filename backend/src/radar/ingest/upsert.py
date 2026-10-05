"""Idempotent writes to the clean layer.

Every function upserts on the natural key and returns how many rows actually changed,
so writing the same data twice reports zero the second time.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import Bar, IngestionRun, NewsArticle, NewsSymbol
from radar.providers import schemas

BATCH = 2_000
BAR_VALUES = ("open", "high", "low", "close", "volume", "trade_count", "vwap", "is_quote_only")
ARTICLE_VALUES = ("created_at", "updated_at", "headline", "summary", "author", "url", "source")


def bar_row(symbol: str, timeframe: str, loc: str, bar: schemas.Bar) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "loc": loc,
        "ts": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "trade_count": bar.trade_count,
        "vwap": bar.vwap,
        "is_quote_only": bar.volume == 0,
    }


def upsert_bars(session: Session, rows: Sequence[dict[str, Any]]) -> int:
    """Insert bars, or update the ones whose values differ. Returns rows changed."""
    changed = 0
    for start in range(0, len(rows), BATCH):
        statement = insert(Bar).values(list(rows[start : start + BATCH]))
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[Bar.symbol, Bar.timeframe, Bar.loc, Bar.ts],
            set_={
                **{column: excluded[column] for column in BAR_VALUES},
                "received_at": func.now(),
            },
            where=tuple_(*(getattr(Bar, c) for c in BAR_VALUES)).is_distinct_from(
                tuple_(*(excluded[c] for c in BAR_VALUES))
            ),
        ).returning(Bar.ts)
        changed += len(session.execute(upsert).all())
    return changed


def article_row(article: schemas.NewsArticle) -> dict[str, Any]:
    return {
        "id": article.id,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
        "headline": article.headline,
        "summary": article.summary,
        "author": article.author,
        "url": article.url,
        "source": article.source,
    }


def upsert_news(session: Session, articles: Sequence[schemas.NewsArticle], symbol: str) -> int:
    """Store articles and link them to the canonical `symbol`. Returns rows changed.

    An article already stored is replaced only by a revision that is at least as new.
    """
    changed = 0
    unique = list({a.id: a for a in articles}.values())
    for start in range(0, len(unique), BATCH):
        batch = unique[start : start + BATCH]
        statement = insert(NewsArticle).values([article_row(a) for a in batch])
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[NewsArticle.id],
            set_={
                **{column: excluded[column] for column in ARTICLE_VALUES},
                "received_at": func.now(),
            },
            where=(excluded.updated_at >= NewsArticle.updated_at)
            & tuple_(*(getattr(NewsArticle, c) for c in ARTICLE_VALUES)).is_distinct_from(
                tuple_(*(excluded[c] for c in ARTICLE_VALUES))
            ),
        ).returning(NewsArticle.id)
        changed += len(session.execute(upsert).all())

        links = insert(NewsSymbol).values([{"article_id": a.id, "symbol": symbol} for a in batch])
        linked = links.on_conflict_do_nothing().returning(NewsSymbol.article_id)
        changed += len(session.execute(linked).all())
    return changed


def finished_windows(session: Session, job: str, key: str) -> set[tuple[datetime, datetime]]:
    """Windows of this job and key that completed and need no refetch."""
    rows = session.execute(
        select(IngestionRun.window_start, IngestionRun.window_end).where(
            IngestionRun.job == job, IngestionRun.key == key, IngestionRun.status == "done"
        )
    ).all()
    return {(r.window_start, r.window_end) for r in rows}


def record_run(
    session: Session,
    *,
    job: str,
    key: str,
    window_start: datetime,
    window_end: datetime,
    status: str,
    rows: int,
    started_at: datetime,
    error: str | None = None,
) -> None:
    values = {
        "job": job,
        "key": key,
        "window_start": window_start,
        "window_end": window_end,
        "status": status,
        "rows": rows,
        "error": error,
        "started_at": started_at,
        "finished_at": func.now(),
    }
    statement = insert(IngestionRun).values(values)
    session.execute(
        statement.on_conflict_do_update(
            constraint="uq_ingestion_runs_job",
            set_={k: statement.excluded[k] for k in ("status", "rows", "error", "started_at")}
            | {"finished_at": func.now()},
        )
    )
