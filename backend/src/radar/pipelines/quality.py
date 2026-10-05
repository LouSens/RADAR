"""The data quality job: check the clean layer, set flags, and write reports.

Checks stored bars against their schema and calendar, flags outlier bars, cleans news
text, and marks duplicate articles. Nothing is deleted and no price is ever filled in.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import Engine, bindparam, select, update
from sqlalchemy.orm import Session

from radar.db.models import Bar, DataQualityReport, NewsArticle, NewsSymbol
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.quality.gaps import expected_index, find_gaps
from radar.quality.news import clean_text, find_duplicates
from radar.quality.outliers import flag_outliers
from radar.quality.schemas import BAR_COLUMNS, invalid_rows
from radar.universe import Asset, Universe

log = get_logger(__name__)

# A series missing more than this share of its expected bars is reported as a warning.
GAP_WARNING_SHARE = 0.05
MAX_EXAMPLES = 20


@dataclass
class Finding:
    symbol: str | None
    check: str
    status: str  # "ok", "warn", or "fail"
    detail: dict[str, Any]


def load_bars(session: Session, symbol: str, timeframe: str) -> pd.DataFrame:
    columns = [getattr(Bar, name) for name in BAR_COLUMNS]
    rows = session.execute(
        select(*columns, Bar.loc, Bar.is_outlier, Bar.is_quote_only)
        .where(Bar.symbol == symbol, Bar.timeframe == timeframe)
        .order_by(Bar.ts)
    ).all()
    frame = pd.DataFrame(rows, columns=[*BAR_COLUMNS, "loc", "is_outlier", "is_quote_only"])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


def check_series(session: Session, asset: Asset, timeframe: str) -> list[Finding]:
    frame = load_bars(session, asset.symbol, timeframe)
    name = f"{timeframe}"
    if frame.empty:
        return [Finding(asset.symbol, f"bars_present:{name}", "fail", {"bars": 0})]
    findings: list[Finding] = []

    failures = invalid_rows(frame[BAR_COLUMNS])
    findings.append(
        Finding(
            asset.symbol,
            f"bar_schema:{name}",
            "fail" if failures else "ok",
            {
                "bars": len(frame),
                "invalid": len(failures),
                "examples": [
                    {"ts": frame.loc[i, "ts"].isoformat(), "checks": sorted(set(c))}
                    for i, c in list(failures.items())[:MAX_EXAMPLES]
                ],
            },
        )
    )

    actual = pd.DatetimeIndex(frame["ts"])
    gaps = find_gaps(expected_index(asset.asset_class, timeframe, actual[0], actual[-1]), actual)
    largest = sorted(gaps.gaps, key=lambda g: g.missing, reverse=True)[:MAX_EXAMPLES]
    findings.append(
        Finding(
            asset.symbol,
            f"gaps:{name}",
            "warn" if gaps.missing_share > GAP_WARNING_SHARE else "ok",
            {
                "first": actual[0].isoformat(),
                "last": actual[-1].isoformat(),
                "expected": gaps.expected,
                "present": gaps.present,
                "missing": gaps.missing,
                "missing_share": round(gaps.missing_share, 6),
                "outside_calendar": gaps.outside_calendar,
                "gap_count": len(gaps.gaps),
                "largest_gaps": [
                    {"start": g.start.isoformat(), "end": g.end.isoformat(), "missing": g.missing}
                    for g in largest
                ],
            },
        )
    )

    # Hourly series have breaks (stock sessions, missing bars); daily ones are compared
    # bar to bar.
    step = pd.Timedelta(hours=1) if timeframe == "1Hour" else None
    flags = flag_outliers(frame.set_index("ts")["close"], step=step)
    stored = frame.set_index("ts")["is_outlier"]
    changed = flags[flags != stored]
    if len(changed):
        session.connection().execute(
            update(Bar)
            .where(
                Bar.symbol == asset.symbol,
                Bar.timeframe == timeframe,
                Bar.ts == bindparam("b_ts"),
            )
            .values(is_outlier=bindparam("b_flag")),
            [
                {"b_ts": ts, "b_flag": bool(flag)}
                for ts, flag in zip(
                    pd.DatetimeIndex(changed.index).to_pydatetime(), changed.tolist(), strict=True
                )
            ],
        )
    findings.append(
        Finding(
            asset.symbol,
            f"outliers:{name}",
            "ok",
            {
                "flagged": int(flags.sum()),
                "newly_changed": len(changed),
                "examples": [ts.isoformat() for ts in flags[flags].index[:MAX_EXAMPLES]],
            },
        )
    )
    findings.append(
        Finding(
            asset.symbol,
            f"quote_only:{name}",
            "ok",
            {
                "quote_only": int(frame["is_quote_only"].sum()),
                "share": round(float(frame["is_quote_only"].mean()), 6),
            },
        )
    )
    return findings


def clean_news(session: Session) -> Finding:
    """Rewrite stored headlines and summaries whose cleaned form differs."""
    rows = session.execute(select(NewsArticle.id, NewsArticle.headline, NewsArticle.summary)).all()
    changes = [
        {"b_id": r.id, "b_headline": clean_text(r.headline), "b_summary": clean_text(r.summary)}
        for r in rows
        if clean_text(r.headline) != r.headline or clean_text(r.summary) != r.summary
    ]
    if changes:
        session.connection().execute(
            update(NewsArticle)
            .where(NewsArticle.id == bindparam("b_id"))
            .values(headline=bindparam("b_headline"), summary=bindparam("b_summary")),
            changes,
        )
    return Finding(None, "news_text", "ok", {"articles": len(rows), "cleaned": len(changes)})


def mark_news_duplicates(session: Session) -> Finding:
    rows = session.execute(
        select(NewsArticle.id, NewsSymbol.symbol, NewsArticle.created_at, NewsArticle.headline)
        .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
        .order_by(NewsArticle.created_at)
    ).all()
    frame = pd.DataFrame(rows, columns=["id", "symbol", "created_at", "headline"])
    duplicates = find_duplicates(frame) if len(frame) else {}

    stored = dict(
        session.execute(
            select(NewsArticle.id, NewsArticle.duplicate_of).where(
                NewsArticle.duplicate_of.is_not(None)
            )
        ).all()
    )
    changes = [
        {"b_id": article, "b_original": duplicates.get(article)}
        for article in set(duplicates) | set(stored)
        if duplicates.get(article) != stored.get(article)
    ]
    if changes:
        session.connection().execute(
            update(NewsArticle)
            .where(NewsArticle.id == bindparam("b_id"))
            .values(duplicate_of=bindparam("b_original")),
            changes,
        )
    return Finding(
        None,
        "news_duplicates",
        "ok",
        {"links": len(frame), "duplicates": len(duplicates), "newly_changed": len(changes)},
    )


def run_quality(engine: Engine, universe: Universe) -> list[Finding]:
    """Run every check and store one report row per finding."""
    findings: list[Finding] = []
    for asset in universe.assets:
        for timeframe in universe.timeframes_for(asset):
            with session_scope(engine) as session:
                findings.extend(check_series(session, asset, timeframe))
    with session_scope(engine) as session:
        findings.append(clean_news(session))
        findings.append(mark_news_duplicates(session))
    with session_scope(engine) as session:
        session.add_all(
            DataQualityReport(symbol=f.symbol, check=f.check, status=f.status, detail=f.detail)
            for f in findings
        )
    worst = {"ok": 0, "warn": 1, "fail": 2}
    log.info(
        "quality_done",
        findings=len(findings),
        warnings=sum(f.status == "warn" for f in findings),
        failures=sum(f.status == "fail" for f in findings),
        worst=max((f.status for f in findings), key=lambda s: worst[s], default="ok"),
    )
    return findings
