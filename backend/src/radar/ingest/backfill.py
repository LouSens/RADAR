"""Resumable historical backfill of bars and news for the configured universe.

History is fetched in calendar-aligned windows. A window that lies wholly in the past
is recorded in `ingestion_runs` once it completes and is never fetched again. The
window that contains "now" is refetched on every run. Only bars whose period has ended
are stored, so a re-run with no new data changes zero rows.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Final

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.db.models import DataQualityReport
from radar.db.session import session_scope
from radar.ingest.upsert import bar_row, finished_windows, record_run, upsert_bars, upsert_news
from radar.logging import get_logger
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.errors import AlpacaError
from radar.providers.schemas import Bar, BarsPage, NewsArticle
from radar.quality.schemas import split_valid_bars
from radar.universe import Asset, Universe

log = get_logger(__name__)

JOB = "backfill"
STOCK_FEED: Final = "sip"
# The free plan serves consolidated stock data once it is 15 minutes old.
STOCK_DELAY = timedelta(minutes=16)
NEWS_HISTORY_START = datetime(2015, 1, 1, tzinfo=UTC)

BAR_LENGTH = {"1Hour": timedelta(hours=1), "1Day": timedelta(days=1)}

Window = tuple[datetime, datetime]
Fetch = Callable[[Session, Window], int]


@dataclass
class BackfillResult:
    rows_changed: int = 0
    windows_fetched: int = 0
    windows_skipped: int = 0
    bars_rejected: int = 0
    failures: list[str] = field(default_factory=list)


def month_windows(start: datetime, end: datetime) -> Iterator[Window]:
    """Calendar months from `start` up to the month that contains `end`."""
    cursor = start
    while cursor < end:
        first = cursor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (first + timedelta(days=32)).replace(day=1)
        yield cursor, next_month
        cursor = next_month


def year_windows(start: datetime, end: datetime) -> Iterator[Window]:
    """Calendar years from `start` up to the year that contains `end`."""
    cursor = start
    while cursor < end:
        next_year = datetime(cursor.year + 1, 1, 1, tzinfo=UTC)
        yield cursor, next_year
        cursor = next_year


def windows_for(timeframe: str, start: datetime, end: datetime) -> Iterator[Window]:
    return year_windows(start, end) if timeframe == "1Day" else month_windows(start, end)


def completed_bars(bars: list[Bar], timeframe: str, now: datetime) -> list[Bar]:
    """Drop bars whose period has not ended: their values can still change."""
    length = BAR_LENGTH[timeframe]
    return [bar for bar in bars if bar.timestamp + length <= now]


class Backfill:
    def __init__(
        self,
        client: AlpacaDataClient,
        engine: Engine,
        universe: Universe,
        *,
        now: datetime | None = None,
    ) -> None:
        self.client = client
        self.engine = engine
        self.universe = universe
        self.now = (now or datetime.now(UTC)).replace(microsecond=0)
        self.result = BackfillResult()

    # --- shared window loop --------------------------------------------------------

    def _run_windows(
        self, key: str, windows: Iterator[Window], end: datetime, fetch: Fetch
    ) -> None:
        with session_scope(self.engine) as session:
            done = finished_windows(session, JOB, key)
        for window in windows:
            if window in done:
                self.result.windows_skipped += 1
                continue
            started = datetime.now(UTC)
            closed = window[1] <= end  # otherwise the window is still filling up
            try:
                with session_scope(self.engine) as session:
                    changed = fetch(session, window)
                    record_run(
                        session,
                        job=JOB,
                        key=key,
                        window_start=window[0],
                        window_end=window[1],
                        status="done" if closed else "partial",
                        rows=changed,
                        started_at=started,
                    )
            except AlpacaError as exc:
                message = f"{key} {window[0]:%Y-%m-%d}: {exc}"[:300]
                self.result.failures.append(message)
                log.error("backfill_window_failed", key=key, window=str(window[0]), error=str(exc))
                with session_scope(self.engine) as session:
                    record_run(
                        session,
                        job=JOB,
                        key=key,
                        window_start=window[0],
                        window_end=window[1],
                        status="failed",
                        rows=0,
                        started_at=started,
                        error=str(exc)[:500],
                    )
                continue
            self.result.rows_changed += changed
            self.result.windows_fetched += 1
        log.info(
            "backfill_key_done",
            key=key,
            rows_changed=self.result.rows_changed,
            fetched=self.result.windows_fetched,
            skipped=self.result.windows_skipped,
        )

    # --- bars ----------------------------------------------------------------------

    def _bar_pages(
        self, asset: Asset, timeframe: str, window: Window, limit: datetime
    ) -> Iterator[BarsPage]:
        # The API treats `end` as inclusive; stop one second short of the next window.
        end = min(window[1], limit) - timedelta(seconds=1)
        if asset.asset_class == "crypto":
            return self.client.iter_crypto_bar_pages(
                [asset.bars_symbol], timeframe, window[0], end, loc=self.universe.crypto_location
            )
        return self.client.iter_stock_bar_pages(
            [asset.bars_symbol], timeframe, window[0], end, feed=STOCK_FEED
        )

    def backfill_bars(self, asset: Asset, timeframe: str) -> None:
        is_crypto = asset.asset_class == "crypto"
        loc = self.universe.crypto_location if is_crypto else STOCK_FEED
        end = self.now if is_crypto else self.now - STOCK_DELAY
        start = datetime.combine(asset.history_start, time(), tzinfo=UTC)
        key = f"bars:{asset.symbol}:{timeframe}:{loc}"

        def fetch(session: Session, window: Window) -> int:
            bars = [
                bar
                for page in self._bar_pages(asset, timeframe, window, end)
                for bar in page.bars.get(asset.bars_symbol, [])
            ]
            valid, rejected = split_valid_bars(completed_bars(bars, timeframe, self.now))
            if rejected:
                self.result.bars_rejected += len(rejected)
                session.add(
                    DataQualityReport(
                        symbol=asset.symbol,
                        check=f"bar_rejected:{timeframe}",
                        status="fail",
                        detail={"rejected": len(rejected), "examples": rejected[:20]},
                    )
                )
            rows = [bar_row(asset.symbol, timeframe, loc, bar) for bar in valid]
            return upsert_bars(session, rows) if rows else 0

        self._run_windows(key, windows_for(timeframe, start, end), end, fetch)

    # --- news ----------------------------------------------------------------------

    def backfill_news(self, asset: Asset, news_symbol: str) -> None:
        key = f"news:{news_symbol}"

        def fetch(session: Session, window: Window) -> int:
            articles: list[NewsArticle] = [
                article
                for page in self.client.iter_news_pages(
                    [news_symbol],
                    window[0],
                    min(window[1], self.now) - timedelta(seconds=1),
                    sort="asc",
                )
                for article in page.news
            ]
            return upsert_news(session, articles, asset.symbol) if articles else 0

        self._run_windows(key, month_windows(NEWS_HISTORY_START, self.now), self.now, fetch)

    # --- everything ----------------------------------------------------------------

    def run(self, *, bars: bool = True, news: bool = True) -> BackfillResult:
        if bars:
            for asset in self.universe.assets:
                for timeframe in self.universe.timeframes_for(asset):
                    self.backfill_bars(asset, timeframe)
        if news:
            for asset in self.universe.assets:
                for news_symbol in asset.news_symbols:
                    self.backfill_news(asset, news_symbol)
        return self.result
