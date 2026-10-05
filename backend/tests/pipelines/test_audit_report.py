from datetime import UTC, datetime, timedelta

from radar.pipelines.audit_report import (
    AuditResults,
    BarStats,
    History,
    HttpProbe,
    MinuteWindow,
    NewsAudit,
    NewsCounts,
    StreamProbe,
    day_boundary,
    days_covered,
    expected_bar_count,
    latest_full_week_start,
    quarterly_week_starts,
    render,
)
from radar.providers.schemas import Bar

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def bar(ts: datetime, *, o: float = 10, h: float = 11, low: float = 9, v: float = 1) -> Bar:
    return Bar.model_validate(
        {"t": ts, "o": o, "h": h, "l": low, "c": 10, "v": v, "n": 1, "vw": 10}
    )


def test_bar_stats_counts_quote_only_bars() -> None:
    stats = BarStats()
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    for i, volume in enumerate([0.0, 2.0, 0.0, 1.0]):
        stats.add(bar(t0 + i * HOUR, v=volume))
    assert stats.bars == 4
    assert stats.quote_only == 2
    assert stats.quote_only_share == 0.5
    assert stats.volume == 3.0
    assert stats.notional_usd == 30.0
    assert (stats.first_ts, stats.last_ts) == (t0, t0 + 3 * HOUR)
    assert BarStats().quote_only_share is None


def test_expected_bar_count_is_inclusive() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    assert expected_bar_count(t0, t0, HOUR) == 1
    assert expected_bar_count(t0, t0 + DAY, HOUR) == 25
    assert expected_bar_count(None, t0, HOUR) == 0


def test_quarterly_weeks_are_full_past_mondays() -> None:
    first = datetime(2024, 2, 10, tzinfo=UTC)
    now = datetime(2024, 10, 9, tzinfo=UTC)
    starts = quarterly_week_starts(first, now)
    # 2024-01-01 is a Monday but precedes the first bar; 2024-10-07's week has not ended.
    assert starts == [datetime(2024, 4, 1, tzinfo=UTC), datetime(2024, 7, 1, tzinfo=UTC)]
    assert all(s.weekday() == 0 for s in starts)
    assert all(s + 7 * DAY <= now for s in starts)


def test_latest_full_week_has_ended_and_holds_a_weekend() -> None:
    now = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)  # a Monday
    start = latest_full_week_start(now)
    assert start == datetime(2026, 9, 28, tzinfo=UTC)
    assert start.weekday() == 0
    assert start + 7 * DAY <= now


def test_day_boundary_reads_stamp_and_checks_against_hourly() -> None:
    stamp = datetime(2024, 1, 1, 5, tzinfo=UTC)
    hourly = {}
    daily = []
    for d in range(3):
        day_start = stamp + d * DAY
        for k in range(24):
            hourly[day_start + k * HOUR] = bar(day_start + k * HOUR, o=10 + k, h=20 + k, low=5 - k)
        daily.append(bar(day_start, o=10, h=43, low=-18))
    result = day_boundary("BTC/USD", "us", daily, hourly)
    assert result.times_utc == {"05:00": 3}
    assert result.days_checked == 2  # the newest daily bar is skipped
    assert result.open_matches_hourly == 2
    assert result.high_low_match_hourly == 2


def test_day_boundary_detects_mismatch() -> None:
    stamp = datetime(2024, 1, 1, tzinfo=UTC)
    hourly = {stamp + k * HOUR: bar(stamp + k * HOUR) for k in range(48)}
    daily = [bar(stamp, o=99, h=120, low=1), bar(stamp + DAY)]
    result = day_boundary("BTC/USD", "us", daily, hourly)
    assert result.days_checked == 1
    assert result.open_matches_hourly == 0
    assert result.high_low_match_hourly == 0


def test_days_covered_handles_partial_years() -> None:
    start, end = datetime(2015, 1, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC)
    assert days_covered(2016, start, end) == 366
    assert days_covered(2026, start, end) == 277
    assert days_covered(2027, start, end) == 0


def test_render_reports_measurements_and_skipped_sections() -> None:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    stats = BarStats(bars=10, quote_only=4, first_ts=t0, last_ts=t0 + 9 * HOUR)
    results = AuditResults(
        generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        authenticated=True,
        history=[
            History(symbol="PAXG/USD", venue="us", timeframe="1Hour", stats=stats, expected_bars=10)
        ],
        minute_windows=[
            MinuteWindow(
                symbol="BTC/USD",
                venue="us",
                start=t0,
                weekday=BarStats(bars=7200, quote_only=720),
                weekend=BarStats(bars=2880, quote_only=1440),
            )
        ],
        forex=[
            HttpProbe(
                what="Forex latest rate, gold",
                request="/x?currency_pairs=XAUUSD",
                status=400,
                detail="invalid pair",
            )
        ],
    )
    text = render(results)
    assert "| PAXG/USD | us | 1Hour |" in text
    assert "40.0%" in text  # quote-only share over full history
    assert "| BTC/USD | us | 2024 | 1 | 100.0% | 21.4% | 10.0% | 50.0% |" in text
    assert "invalid pair" in text
    assert text.count("Not run in this audit.") == 2  # streams and news
    assert text.endswith("\n")


def test_render_news_rates_use_days_covered() -> None:
    results = AuditResults(
        generated_at=datetime(2026, 10, 5, tzinfo=UTC),
        authenticated=True,
        streams_ran=True,
        streams=[StreamProbe(what="News stream", steps=[("connect", "success")])],
        news=NewsAudit(
            ran=True,
            available=True,
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
            articles=730,
            pages=15,
            counts=[
                NewsCounts(label="GLD", by_year={2025: 730}, days_with_news_by_year={2025: 292})
            ],
        ),
    )
    text = render(results)
    assert "| GLD | none | 730 |" in text
    assert "| GLD | 2.00 (80.0%) |" in text
    assert "| connect | success |" in text
