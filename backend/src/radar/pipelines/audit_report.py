"""Result models, pure statistics, and the Markdown renderer for the Phase 0 data audit."""

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from radar.providers.schemas import Bar

GOLD_NEWS_THRESHOLD_PER_DAY = 2.0  # spec 3.4
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

# --- models ----------------------------------------------------------------------------


class BarStats(BaseModel):
    bars: int = 0
    quote_only: int = 0
    volume: float = 0.0
    notional_usd: float = 0.0
    trades: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    def add(self, bar: Bar) -> None:
        self.bars += 1
        self.quote_only += bar.volume == 0
        self.volume += bar.volume
        self.notional_usd += bar.volume * bar.vwap
        self.trades += bar.trade_count
        if self.first_ts is None or bar.timestamp < self.first_ts:
            self.first_ts = bar.timestamp
        if self.last_ts is None or bar.timestamp > self.last_ts:
            self.last_ts = bar.timestamp

    @property
    def quote_only_share(self) -> float | None:
        return self.quote_only / self.bars if self.bars else None


class EarliestBar(BaseModel):
    symbol: str
    venue: str  # crypto location, or "stocks"
    timeframe: str
    first_ts: datetime | None = None
    error: str | None = None


class History(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    stats: BarStats = Field(default_factory=BarStats)
    expected_bars: int = 0
    error: str | None = None


class MinuteWindow(BaseModel):
    symbol: str
    venue: str
    start: datetime
    is_latest_week: bool = False
    weekday: BarStats = Field(default_factory=BarStats)
    weekend: BarStats = Field(default_factory=BarStats)
    error: str | None = None


class RecentVolume(BaseModel):
    symbol: str
    venue: str
    days: int
    stats: BarStats


class DayBoundary(BaseModel):
    symbol: str
    venue: str
    times_utc: dict[str, int]  # "HH:MM" -> number of 1Day bars stamped at that time
    days_checked: int = 0
    open_matches_hourly: int = 0
    high_low_match_hourly: int = 0


class NewsCounts(BaseModel):
    label: str
    by_year: dict[int, int] = Field(default_factory=dict)
    days_with_news_by_year: dict[int, int] = Field(default_factory=dict)
    first_article: datetime | None = None


class NewsAudit(BaseModel):
    ran: bool = False
    available: bool | None = None
    error: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    articles: int = 0
    pages: int = 0
    counts: list[NewsCounts] = Field(default_factory=list)


class HttpProbe(BaseModel):
    what: str
    request: str
    status: int | None
    detail: str


class StreamProbe(BaseModel):
    what: str
    steps: list[tuple[str, str]] = Field(default_factory=list)  # (step, observed)


class VenueAgreement(BaseModel):
    """How far daily closes on another venue sit from the base venue, as |a / b - 1|."""

    symbol: str
    base: str
    other: str
    days: int = 0
    median_abs_diff: float | None = None
    p95_abs_diff: float | None = None
    max_abs_diff: float | None = None
    max_diff_day: datetime | None = None


class PageSize(BaseModel):
    symbol: str
    venue: str
    timeframe: str
    requested_limit: int
    bars_in_first_page: int
    has_next_page: bool


class AuditResults(BaseModel):
    generated_at: datetime
    authenticated: bool
    rate_limit_headers: dict[str, str] = Field(default_factory=dict)
    access: list[HttpProbe] = Field(default_factory=list)
    earliest: list[EarliestBar] = Field(default_factory=list)
    history: list[History] = Field(default_factory=list)
    minute_windows: list[MinuteWindow] = Field(default_factory=list)
    recent_volume: list[RecentVolume] = Field(default_factory=list)
    day_boundaries: list[DayBoundary] = Field(default_factory=list)
    news: NewsAudit = Field(default_factory=NewsAudit)
    forex: list[HttpProbe] = Field(default_factory=list)
    streams_ran: bool = False
    streams: list[StreamProbe] = Field(default_factory=list)
    venue_agreement: list[VenueAgreement] = Field(default_factory=list)
    page_sizes: list[PageSize] = Field(default_factory=list)


# --- pure statistics -------------------------------------------------------------------


def expected_bar_count(first: datetime | None, last: datetime | None, step: timedelta) -> int:
    """Bars a gap-free continuous series would hold between two timestamps, inclusive."""
    if first is None or last is None:
        return 0
    return int((last - first) / step) + 1


def quarterly_week_starts(first: datetime, now: datetime) -> list[datetime]:
    """Monday 00:00 UTC of the first full week of each quarter, for weeks that have ended."""
    starts: list[datetime] = []
    year, quarter = first.year, (first.month - 1) // 3
    while True:
        quarter_start = datetime(year, quarter * 3 + 1, 1, tzinfo=UTC)
        monday = quarter_start + timedelta(days=(7 - quarter_start.weekday()) % 7)
        if monday + 7 * DAY > now:
            return starts
        if monday >= first:
            starts.append(monday)
        year, quarter = (year + 1, 0) if quarter == 3 else (year, quarter + 1)


def latest_full_week_start(now: datetime) -> datetime:
    """Monday 00:00 UTC of the most recent week that has fully ended."""
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday()) - 7 * DAY


def day_boundary(
    symbol: str, venue: str, daily: list[Bar], hourly: Mapping[datetime, Bar], check: int = 7
) -> DayBoundary:
    """Where 1Day bars are stamped, and whether they equal 24 hourly bars from that stamp."""
    times = Counter(b.timestamp.astimezone(UTC).strftime("%H:%M") for b in daily)
    result = DayBoundary(symbol=symbol, venue=venue, times_utc=dict(times))
    for bar in daily[:-1][-check:]:  # skip the newest bar: its day may not have ended
        hours = [
            hourly[bar.timestamp + k * HOUR]
            for k in range(24)
            if bar.timestamp + k * HOUR in hourly
        ]
        if bar.timestamp not in hourly or not hours:
            continue
        result.days_checked += 1
        result.open_matches_hourly += math.isclose(bar.open, hours[0].open, rel_tol=1e-9)
        result.high_low_match_hourly += math.isclose(
            bar.high, max(h.high for h in hours), rel_tol=1e-9
        ) and math.isclose(bar.low, min(h.low for h in hours), rel_tol=1e-9)
    return result


def venue_agreement(
    symbol: str, base: str, other: str, base_bars: Iterable[Bar], other_bars: Iterable[Bar]
) -> VenueAgreement:
    """Compare daily closes on the days both venues have a bar."""
    base_close = {b.timestamp: b.close for b in base_bars}
    diffs = sorted(
        (abs(b.close / base_close[b.timestamp] - 1.0), b.timestamp)
        for b in other_bars
        if b.timestamp in base_close
    )
    result = VenueAgreement(symbol=symbol, base=base, other=other, days=len(diffs))
    if diffs:
        result.median_abs_diff = diffs[len(diffs) // 2][0]
        result.p95_abs_diff = diffs[min(len(diffs) - 1, int(0.95 * len(diffs)))][0]
        result.max_abs_diff, result.max_diff_day = diffs[-1]
    return result


def days_covered(year: int, start: datetime, end: datetime) -> int:
    """Days of `year` that fall inside the audited range [start, end)."""
    lo = max(start.date(), date(year, 1, 1))
    hi = min(end.date(), date(year + 1, 1, 1))
    return max((hi - lo).days, 0)


def sum_stats(items: Iterable[BarStats]) -> BarStats:
    total = BarStats()
    for s in items:
        total.bars += s.bars
        total.quote_only += s.quote_only
        total.volume += s.volume
        total.notional_usd += s.notional_usd
        total.trades += s.trades
    return total


# --- rendering -------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def _pct2(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def _ts(value: datetime | None) -> str:
    return "none" if value is None else value.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def _num(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.4g}"


def _table(header: list[str], rows: Iterable[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return [*lines, ""]


def _probe_table(probes: list[HttpProbe]) -> list[str]:
    return _table(
        ["Probe", "Request", "Status", "Observed"],
        ([p.what, f"`{p.request}`", p.status or "no response", p.detail] for p in probes),
    )


def _news_rate(counts: NewsCounts, year: int, news: NewsAudit) -> float | None:
    if news.start is None or news.end is None:
        return None
    days = days_covered(year, news.start, news.end)
    return counts.by_year.get(year, 0) / days if days else None


def render(r: AuditResults) -> str:
    out: list[str] = [
        "# RADAR data audit",
        "",
        "Generated by `make audit` (`uv run radar audit`). Do not edit by hand; re-run instead.",
        "",
        f"- Run at: {_ts(r.generated_at)} UTC",
        f"- Authenticated with Alpaca keys: {'yes' if r.authenticated else 'no'}",
        "- Every number below is **measured** by this run unless a line says"
        " **documented, not measured**.",
        "- All timestamps are UTC.",
        "",
    ]

    out += ["## 1. Access and plan limits (spec 3.2)", ""]
    if r.rate_limit_headers:
        out += [
            "Rate-limit headers on an authenticated historical call: "
            + ", ".join(f"`{k}: {v}`" for k, v in r.rate_limit_headers.items())
            + ".",
            "",
        ]
    else:
        out += ["No rate-limit headers were returned.", ""]
    out += _probe_table(r.access)

    out += ["### WebSocket streams", ""]
    if not r.streams_ran:
        out += ["Not run in this audit.", ""]
    else:
        out += [
            "Gentle probe only: at most two connections open at once, a handful of symbols,"
            " no attempt to find a hard ceiling.",
            "",
        ]
        for probe in r.streams:
            out += [f"**{probe.what}**", ""]
            out += _table(["Step", "Observed"], ([s, o] for s, o in probe.steps))
        out += [
            "Not measured: the largest number of symbols one crypto or news connection may"
            " subscribe to. Only the handful above was tried. Documented, not measured: the"
            " stock stream is limited to 30 symbols on the Basic plan.",
            "",
        ]

    out += ["## 2. Crypto bars (spec 3.3)", "", "### 2.1 Earliest available bar", ""]
    out += _table(
        ["Symbol", "Venue", "Timeframe", "Earliest bar", "Note"],
        ([e.symbol, e.venue, e.timeframe, _ts(e.first_ts), e.error or ""] for e in r.earliest),
    )

    out += [
        "### 2.2 Quote-only bars over full history",
        "",
        'A quote-only bar has `volume == 0`. "Present" is bars received divided by the bars a'
        " gap-free series would hold between the first and last bar.",
        "",
    ]
    out += _table(
        ["Symbol", "Venue", "Timeframe", "First", "Last", "Bars", "Present", "Quote-only", "Note"],
        (
            [
                h.symbol,
                h.venue,
                h.timeframe,
                _ts(h.stats.first_ts),
                _ts(h.stats.last_ts),
                f"{h.stats.bars:,}",
                _pct(h.stats.bars / h.expected_bars if h.expected_bars else None),
                _pct(h.stats.quote_only_share),
                h.error or "",
            ]
            for h in r.history
        ),
    )

    out += [
        "### 2.3 Quote-only bars at 1Min (sampled)",
        "",
        "Sample: the first full Monday-to-Sunday week of every quarter since the first 1Min"
        " bar, plus the most recent full week. Every window therefore contains one weekend."
        " A full week holds 10,080 one-minute bars.",
        "",
    ]
    by_year: dict[tuple[str, str, int], list[MinuteWindow]] = {}
    for w in r.minute_windows:
        if not w.is_latest_week:
            by_year.setdefault((w.symbol, w.venue, w.start.year), []).append(w)
    rows: list[list[Any]] = []
    for (symbol, venue, year), windows in by_year.items():
        weekday, weekend = (
            sum_stats(w.weekday for w in windows),
            sum_stats(w.weekend for w in windows),
        )
        both = sum_stats([weekday, weekend])
        rows.append(
            [
                symbol,
                venue,
                year,
                len(windows),
                _pct(both.bars / (10_080 * len(windows))),
                _pct(both.quote_only_share),
                _pct(weekday.quote_only_share),
                _pct(weekend.quote_only_share),
            ]
        )
    for w in (w for w in r.minute_windows if w.is_latest_week):
        both = sum_stats([w.weekday, w.weekend])
        rows.append(
            [
                w.symbol,
                w.venue,
                f"latest week ({w.start:%Y-%m-%d})",
                1,
                _pct(both.bars / 10_080),
                _pct(both.quote_only_share),
                _pct(w.weekday.quote_only_share),
                _pct(w.weekend.quote_only_share),
            ]
        )
    out += _table(
        [
            "Symbol",
            "Venue",
            "Period",
            "Weeks",
            "Present",
            "Quote-only",
            "Weekdays",
            "Weekend",
        ],
        rows,
    )
    failed = [w for w in r.minute_windows if w.error]
    if failed:
        out += [f"{len(failed)} sample windows failed; first error: {failed[0].error}", ""]

    out += [
        "### 2.4 Volume by venue",
        "",
        "Summed from 1Hour bars over the most recent complete UTC days.",
        "",
    ]
    us = {v.symbol: v.stats.volume for v in r.recent_volume if v.venue == "us"}
    out += _table(
        ["Symbol", "Venue", "Days", "Volume (units)", "Notional (USD)", "Trades", "Times `us`"],
        (
            [
                v.symbol,
                v.venue,
                v.days,
                _num(v.stats.volume),
                _num(v.stats.notional_usd),
                f"{v.stats.trades:,}",
                f"{v.stats.volume / us[v.symbol]:,.1f}x" if us.get(v.symbol) else "n/a",
            ]
            for v in r.recent_volume
        ),
    )

    out += [
        "### 2.5 Timestamp boundary of 1Day bars",
        "",
        '"Stamp" is the UTC time of day carried by 1Day bars, with the number of bars at each.'
        " The check compares recent daily bars with the 24 hourly bars starting at the stamp.",
        "",
    ]
    out += _table(
        ["Symbol", "Venue", "Stamp (UTC): bars", "Days checked", "Open matches", "High/low match"],
        (
            [
                d.symbol,
                d.venue,
                ", ".join(f"{t}: {n:,}" for t, n in sorted(d.times_utc.items())),
                d.days_checked or "n/a",
                d.open_matches_hourly if d.days_checked else "n/a",
                d.high_low_match_hourly if d.days_checked else "n/a",
            ]
            for d in r.day_boundaries
        ),
    )

    out += [
        "### 2.6 Price agreement between venues",
        "",
        "Absolute relative difference of 1Day closes, on days where both venues have a bar.",
        "",
    ]
    if r.venue_agreement:
        out += _table(
            ["Symbol", "Venues", "Days compared", "Median", "95th percentile", "Largest (day)"],
            (
                [
                    a.symbol,
                    f"{a.other} vs {a.base}",
                    f"{a.days:,}",
                    _pct2(a.median_abs_diff),
                    _pct2(a.p95_abs_diff),
                    f"{_pct2(a.max_abs_diff)} ({_ts(a.max_diff_day)[:10]})",
                ]
                for a in r.venue_agreement
            ),
        )
    else:
        out += ["Not run in this audit.", ""]

    out += [
        "### 2.7 Page size of historical bar requests",
        "",
        "Bars returned in the first page of a request from the earliest bar, and whether the"
        " API offered a next page. This sets how many calls a backfill needs.",
        "",
    ]
    if r.page_sizes:
        out += _table(
            ["Symbol", "Venue", "Timeframe", "Limit requested", "Bars in first page", "More pages"],
            (
                [
                    z.symbol,
                    z.venue,
                    z.timeframe,
                    f"{z.requested_limit:,}",
                    f"{z.bars_in_first_page:,}",
                    "yes" if z.has_next_page else "no",
                ]
                for z in r.page_sizes
            ),
        )
    else:
        out += ["Not run in this audit.", ""]

    out += ["## 3. News (spec 3.4)", ""]
    news = r.news
    if not news.ran:
        out += ["Not run in this audit.", ""]
    elif not news.available:
        out += [f"News endpoint not available: {news.error}", ""]
    else:
        out += [
            f"The historical news endpoint answered on this plan. Range audited:"
            f" {_ts(news.start)} to {_ts(news.end)}. Articles read: {news.articles:,}"
            f" in {news.pages:,} pages.",
            "",
        ]
        if news.error:
            out += [f"**The scan stopped early:** {news.error}", ""]
        years = sorted({y for c in news.counts for y in c.by_year})
        out += ["### 3.1 Articles per year", ""]
        out += _table(
            ["Symbol", "First article", *[str(y) for y in years]],
            (
                [c.label, _ts(c.first_article), *[f"{c.by_year.get(y, 0):,}" for y in years]]
                for c in news.counts
            ),
        )
        out += [
            "### 3.2 Articles per day, and share of days with any article",
            "",
            f"Spec threshold for F3 and F4: about {GOLD_NEWS_THRESHOLD_PER_DAY:g} articles per"
            " day. Partial years are divided by the days actually covered.",
            "",
        ]
        rate_rows: list[list[Any]] = []
        for c in news.counts:
            row: list[Any] = [c.label]
            for y in years:
                rate = _news_rate(c, y, news)
                days = days_covered(y, news.start, news.end) if news.start and news.end else 0
                share = c.days_with_news_by_year.get(y, 0) / days if days else None
                row.append("n/a" if rate is None else f"{rate:.2f} ({_pct(share)})")
            rate_rows.append(row)
        out += _table(["Symbol", *[str(y) for y in years]], rate_rows)

    out += ["## 4. Stocks (spec 3.5)", "", "See sections 2.1 and 2.5 for `SPY` and `GLD`.", ""]

    out += ["## 5. Forex (spec 3.6)", ""]
    out += _probe_table(r.forex)
    return "\n".join(out).rstrip() + "\n"
