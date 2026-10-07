"""Scheduled economic events: how markets have behaved around them.

The dates come from `events.toml`. For each kind of event and each market, five
questions fixed in advance (`docs/DECISIONS.md` 055) are answered from dates and daily
closing prices only: does the market move more on the day, does it lean one way the day
before or on the day, and does the day's move carry on over the next day or week.

Pure functions. Each event's figures use that event's day and the days around it;
nothing here forecasts, so there is no later data to leak into an earlier figure.
"""

import os
import tomllib
from datetime import UTC, date, datetime, time
from functools import cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.stats import binomtest, mannwhitneyu

from radar.signals.track import SIGNIFICANCE, survivors, wilson

VERSION = "events-1"
DEFAULT_FILE = Path(__file__).parent.parent / "events.toml"
FILE_ENV = "RADAR_EVENTS_FILE"
EASTERN = ZoneInfo("America/New_York")
MIN_EVENTS = 30

SizeVerdict = Literal[
    "moves more on these days",
    "moves less on these days",
    "no measurable difference",
    "not enough events",
]
LeanVerdict = Literal["leans up", "leans down", "no measurable pattern", "not enough events"]
CarryVerdict = Literal[
    "tends to carry on", "tends to reverse", "no measurable pattern", "not enough events"
]


class EventKind(BaseModel):
    key: str
    name: str
    # When on the day it is announced, in US Eastern time.
    time_eastern: time
    source: str
    dates: list[date]

    def at(self, day: date) -> datetime:
        """The moment of the announcement on `day`, in UTC."""
        return datetime.combine(day, self.time_eastern, tzinfo=EASTERN).astimezone(UTC)


class EventFile(BaseModel):
    events: list[EventKind]


def load_events(path: Path | None = None) -> list[EventKind]:
    path = path or Path(os.environ.get(FILE_ENV) or DEFAULT_FILE)
    with path.open("rb") as handle:
        return EventFile.model_validate(tomllib.load(handle)).events


@cache
def get_events() -> tuple[EventKind, ...]:
    return tuple(load_events())


class Upcoming(BaseModel):
    key: str
    name: str
    at: datetime
    days_until: int


def upcoming(kinds: list[EventKind], now: datetime, limit: int = 6) -> list[Upcoming]:
    """The next scheduled events, soonest first. One already announced today is past."""
    found = [
        Upcoming(key=k.key, name=k.name, at=k.at(day), days_until=(day - now.date()).days)
        for k in kinds
        for day in k.dates
        if k.at(day) > now
    ]
    return sorted(found, key=lambda e: e.at)[:limit]


class Size(BaseModel):
    """Test 1: the size of the event day's move against every other day."""

    n: int
    on_event: float | None
    other_days: float | None
    p_value: float | None
    verdict: SizeVerdict


class Share(BaseModel):
    """Tests 2 to 5: how often something happened around the event, against any day."""

    n: int
    share: float | None
    low: float | None
    high: float | None
    baseline: float | None
    p_value: float | None
    verdict: LeanVerdict | CarryVerdict


class MarketResult(BaseModel):
    symbol: str
    n_events: int
    first_day: date | None
    last_day: date | None
    size: Size
    day_before: Share
    event_day: Share
    next_day: Share
    next_week: Share


class EventResult(BaseModel):
    key: str
    name: str
    markets: list[MarketResult]


def positions(days: pd.DatetimeIndex, dates: list[date]) -> np.ndarray:
    """Row of each event's trading day in `days`. A date that is not a trading day in
    this market (a holiday) is left out."""
    lookup = {stamp.date(): i for i, stamp in enumerate(days)}
    found: np.ndarray = np.array([lookup[d] for d in dates if d in lookup], dtype=int)
    return found


def _share(hits: np.ndarray, baseline: np.ndarray) -> Share:
    """How often `hits` was true, against how often `baseline` is. NaN-free booleans."""
    n = len(hits)
    base = float(baseline.mean()) if len(baseline) else None
    if n == 0 or base is None:
        return Share(
            n=n,
            share=None,
            low=None,
            high=None,
            baseline=base,
            p_value=None,
            verdict="not enough events",
        )
    count = int(hits.sum())
    low, high = wilson(count, n)
    return Share(
        n=n,
        share=count / n,
        low=low,
        high=high,
        baseline=base,
        p_value=float(binomtest(count, n, base).pvalue),
        verdict="not enough events",
    )


def measure(symbol: str, close: pd.Series, dates: list[date], week: int) -> MarketResult:
    """The five questions for one kind of event on one market. `close` is indexed by
    trading day; `week` is the number of trading days in a week for this market."""
    days = pd.DatetimeIndex(close.index)
    logged = np.log(close.to_numpy(dtype=float))
    ret = np.full(len(logged), np.nan)
    ret[1:] = np.diff(logged)
    ahead = np.full(len(logged), np.nan)
    ahead[:-week] = logged[week:] - logged[:-week]
    nxt = np.full(len(logged), np.nan)
    nxt[:-1] = ret[1:]

    at = positions(days, dates)
    at = at[(at >= 2) & np.isfinite(ret[at])]
    is_event = np.zeros(len(ret), dtype=bool)
    is_event[at] = True
    known = np.isfinite(ret)

    # 1. Size of the day's move.
    on_event, others = np.abs(ret[at]), np.abs(ret[known & ~is_event])
    size = Size(
        n=len(on_event),
        on_event=float(on_event.mean()) if len(on_event) else None,
        other_days=float(others.mean()) if len(others) else None,
        p_value=float(mannwhitneyu(on_event, others).pvalue)
        if len(on_event) and len(others)
        else None,
        verdict="not enough events",
    )
    # 2 and 3. Which way the day before and the day itself went.
    up = ret[known] > 0
    before = at[np.isfinite(ret[at - 1])] - 1
    day_before = _share(ret[before] > 0, up)
    event_day = _share(ret[at] > 0, up)
    # 4 and 5. Whether the next day and the next week went the same way as the day.
    both = known & np.isfinite(nxt)
    carry_day = _share(
        np.sign(nxt[at[np.isfinite(nxt[at])]]) == np.sign(ret[at[np.isfinite(nxt[at])]]),
        np.sign(nxt[both]) == np.sign(ret[both]),
    )
    week_known = known & np.isfinite(ahead)
    with_week = at[np.isfinite(ahead[at])]
    carry_week = _share(
        np.sign(ahead[with_week]) == np.sign(ret[with_week]),
        np.sign(ahead[week_known]) == np.sign(ret[week_known]),
    )
    return MarketResult(
        symbol=symbol,
        n_events=len(at),
        first_day=days[at[0]].date() if len(at) else None,
        last_day=days[at[-1]].date() if len(at) else None,
        size=size,
        day_before=day_before,
        event_day=event_day,
        next_day=carry_day,
        next_week=carry_week,
    )


def _lean(share: Share, passes: bool) -> LeanVerdict:
    if share.n < MIN_EVENTS:
        return "not enough events"
    if not passes or share.low is None or share.high is None or share.baseline is None:
        return "no measurable pattern"
    if share.low > share.baseline:
        return "leans up"
    if share.high < share.baseline:
        return "leans down"
    return "no measurable pattern"


def _carry(share: Share, passes: bool) -> CarryVerdict:
    lean = _lean(share, passes)
    if lean == "leans up":
        return "tends to carry on"
    if lean == "leans down":
        return "tends to reverse"
    return lean


def judge(results: list[EventResult], level: float = SIGNIFICANCE) -> list[EventResult]:
    """Set every verdict, correcting each family for how many comparisons it holds:
    the direction tests together, and the size tests together."""
    cells = [(i, j) for i, r in enumerate(results) for j, _ in enumerate(r.markets)]
    names = ("day_before", "event_day", "next_day", "next_week")
    direction = []
    sizes = []
    for i, j in cells:
        market = results[i].markets[j]
        if market.size.n >= MIN_EVENTS and market.size.p_value is not None:
            sizes.append((i * 100 + j, 0, market.size.p_value))
        for k, name in enumerate(names):
            share: Share = getattr(market, name)
            if share.n >= MIN_EVENTS and share.p_value is not None:
                direction.append((i * 100 + j, k, share.p_value))
    passed_size = survivors(sizes, level)
    passed_direction = survivors(direction, level)

    judged = []
    for i, result in enumerate(results):
        markets = []
        for j, market in enumerate(result.markets):
            cell = i * 100 + j
            size = market.size
            if size.n < MIN_EVENTS:
                size_verdict: SizeVerdict = "not enough events"
            elif (cell, 0) not in passed_size or size.on_event is None or size.other_days is None:
                size_verdict = "no measurable difference"
            elif size.on_event > size.other_days:
                size_verdict = "moves more on these days"
            else:
                size_verdict = "moves less on these days"
            update: dict[str, Size | Share] = {
                "size": size.model_copy(update={"verdict": size_verdict})
            }
            for k, name in enumerate(names):
                share = getattr(market, name)
                passes = (cell, k) in passed_direction
                verdict = _lean(share, passes) if k < 2 else _carry(share, passes)
                update[name] = share.model_copy(update={"verdict": verdict})
            markets.append(market.model_copy(update=update))
        judged.append(result.model_copy(update={"markets": markets}))
    return judged


def comparisons(results: list[EventResult]) -> tuple[int, int]:
    """How many direction tests and how many size tests had enough events to judge."""
    direction = sum(
        1
        for r in results
        for m in r.markets
        for share in (m.day_before, m.event_day, m.next_day, m.next_week)
        if share.n >= MIN_EVENTS
    )
    size = sum(1 for r in results for m in r.markets if m.size.n >= MIN_EVENTS)
    return direction, size
