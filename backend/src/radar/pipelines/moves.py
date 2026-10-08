"""Why it moved (spec F13), put together for one asset from what is stored: its daily
closes, its wider market's, the dates of scheduled events, the market's state, and the
headlines of each day.

Nothing is stored by this module: it is arithmetic on stored prices, done when asked.
What may be said, and what the split rests on, is in `analytics/moves.py` and
`docs/DECISIONS.md` 095 and 096.
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.analytics import events, moves
from radar.db.models import NewsArticle, NewsSymbol
from radar.pipelines.relationships import regime_labels
from radar.pipelines.signals import daily_close
from radar.universe import Asset, Universe

# Days shown, newest first, and headlines listed for each.
DAYS = 30
HEADLINES = 3


class Headline(BaseModel):
    headline: str
    source: str
    url: str | None
    created_at: datetime


class Day(BaseModel):
    """One day of one asset. Every share is a fraction: 0.031 is 3.1%."""

    day: date
    move: float
    # What the wider market did, times the asset's sensitivity to it, and the rest. Both
    # are None when the link to the wider market did not clear its bar or has none.
    market: float | None
    own: float | None
    sensitivity: float | None
    # The move as a multiple of a usual day lately; None in the first sessions.
    times_usual: float | None
    # The share of the earlier days the move was larger than; None with too few.
    rank: float | None
    # Scheduled events that fell on the day, by name. Never given as the cause.
    events: list[str]
    # The market's state before and after, when it changed on the day.
    state_from: str | None
    state_to: str | None
    # Published that day. Never given as the cause.
    headlines: list[Headline]


class WhyItMoved(BaseModel):
    symbol: str
    # The wider market the asset is set against, if it has one.
    reference: str | None
    reference_name: str | None
    evidence: moves.Evidence | None
    # Whether the split into market and own is shown.
    split_shown: bool
    days: list[Day]


def reference_for(universe: Universe, asset: Asset) -> Asset | None:
    """The wider market of an asset: Bitcoin for another coin, the US stock index for
    another stock or fund. Bitcoin, gold and the stock index have none: they are what
    others are measured against (decision 095)."""
    if asset.kind is not None:
        return None
    wanted = "bitcoin" if asset.asset_class == "crypto" else "stocks"
    return next((a for a in universe.assets if a.kind == wanted), None)


def _returns(session: Session, asset: Asset) -> pd.Series:
    close = daily_close(session, asset)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    return close.pct_change().dropna()


def _headlines(session: Session, asset: Asset, first: date) -> dict[date, list[Headline]]:
    start = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
    rows = session.execute(
        select(NewsArticle)
        .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
        .where(
            NewsSymbol.symbol == asset.symbol,
            NewsArticle.duplicate_of.is_(None),
            NewsArticle.created_at >= start,
        )
        .order_by(NewsArticle.created_at.desc())
    ).scalars()
    by_day: dict[date, list[Headline]] = {}
    for article in rows:
        day = article.created_at.astimezone(UTC).date()
        listed = by_day.setdefault(day, [])
        if len(listed) < HEADLINES:
            listed.append(
                Headline(
                    headline=article.headline,
                    source=article.source,
                    url=article.url,
                    created_at=article.created_at,
                )
            )
    return by_day


def _number(value: float) -> float | None:
    return None if pd.isna(value) else float(value)


def build(session: Session, universe: Universe, asset: Asset, days: int = DAYS) -> WhyItMoved:
    """The last `days` days of an asset, each with its split (where that is allowed), how
    unusual its size was, and what else is known about the day."""
    own = _returns(session, asset)
    reference = reference_for(universe, asset)
    judged: moves.Evidence | None = None
    parts = pd.DataFrame(columns=["market", "own", "sensitivity"])
    if reference is not None and not own.empty:
        market = _returns(session, reference)
        judged = moves.evidence(own, market)
        if judged.passed:
            parts = moves.split(own, market)

    usual = moves.usual_size(own)
    rank = moves.size_rank(own)
    shown = own.iloc[-days:]
    scheduled: dict[date, list[str]] = {}
    for kind in events.get_events():
        for day in kind.dates:
            scheduled.setdefault(day, []).append(kind.name)

    # The state known at each day's close, and at the close before it.
    closes = pd.DatetimeIndex(own.index).tz_localize("UTC") + timedelta(days=1)
    labels = pd.Series(regime_labels(session, asset.symbol, closes).to_numpy(), index=own.index)
    before = labels.shift(1)

    news = _headlines(session, asset, shown.index[0].date()) if len(shown) else {}
    out: list[Day] = []
    for stamp in pd.DatetimeIndex(shown.index):
        day = stamp.date()
        move = float(shown.get(stamp, float("nan")))
        size = usual.get(stamp)
        now, earlier = labels.get(stamp), before.get(stamp)
        changed = isinstance(now, str) and isinstance(earlier, str) and now != earlier
        out.append(
            Day(
                day=day,
                move=move,
                market=_number(parts["market"].get(stamp, float("nan"))),
                own=_number(parts["own"].get(stamp, float("nan"))),
                sensitivity=_number(parts["sensitivity"].get(stamp, float("nan"))),
                times_usual=(
                    None if size is None or pd.isna(size) or size == 0 else abs(move) / size
                ),
                rank=_number(rank.get(stamp, float("nan"))),
                events=scheduled.get(day, []),
                state_from=str(earlier) if changed else None,
                state_to=str(now) if changed else None,
                headlines=news.get(day, []),
            )
        )
    out.reverse()
    return WhyItMoved(
        symbol=asset.symbol,
        reference=None if reference is None else reference.symbol,
        reference_name=None if reference is None else reference.name,
        evidence=judged,
        split_shown=bool(judged and judged.passed),
        days=out,
    )
