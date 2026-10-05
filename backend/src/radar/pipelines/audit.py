"""Phase 0 data audit: probe the live Alpaca data API and write docs/DATA_AUDIT.md.

Answers every "verify in Phase 0" item in section 3 of the spec. Read-only: market data
and news endpoints on the data host, nothing else.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from radar.config import Settings, load_settings
from radar.logging import get_logger
from radar.pipelines.audit_report import (
    DAY,
    HOUR,
    AuditResults,
    BarStats,
    DayBoundary,
    EarliestBar,
    History,
    HttpProbe,
    MinuteWindow,
    NewsAudit,
    NewsCounts,
    RecentVolume,
    StreamProbe,
    day_boundary,
    expected_bar_count,
    latest_full_week_start,
    quarterly_week_starts,
    render,
)
from radar.providers.alpaca_rest import AlpacaDataClient, Param
from radar.providers.alpaca_stream import CRYPTO_STREAM_URL, NEWS_STREAM_URL, StreamSession
from radar.providers.errors import AlpacaError, AlpacaHTTPError
from radar.providers.schemas import Bar

log = get_logger(__name__)

REPORT_PATH = Path("docs/DATA_AUDIT.md")
RESULTS_PATH = Path("data/audit/audit_results.json")

PRIMARY = ["BTC/USD", "PAXG/USD"]
OTHER_CRYPTO = ["ETH/USD", "SOL/USD"]
LOCS = ["us", "us-1", "eu-1"]
UNDESCRIBED_LOCS = ["us-2", "bs-1"]
STOCKS = ["SPY", "GLD"]
NEWS_SYMBOLS = ["BTCUSD", "PAXGUSD", "GLD", "SPY", "IAU", "GDX"]
GOLD_NEWS_SET = {"GLD", "IAU", "GDX", "PAXGUSD"}
GOLD_SET_LABEL = "any of GLD, IAU, GDX, PAXGUSD"

CRYPTO_EPOCH = datetime(2009, 1, 1, tzinfo=UTC)
STOCK_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
RECENT_DAYS = 30


def _describe(error: Exception) -> str:
    return str(error)[:160]


# --- bars ------------------------------------------------------------------------------


def probe_earliest(client: AlpacaDataClient) -> list[EarliestBar]:
    results: list[EarliestBar] = []
    for symbol in PRIMARY + OTHER_CRYPTO:
        for loc in LOCS + UNDESCRIBED_LOCS:
            for timeframe in ("1Day", "1Hour", "1Min"):
                row = EarliestBar(symbol=symbol, venue=loc, timeframe=timeframe)
                try:
                    page = next(
                        client.iter_crypto_bar_pages(
                            [symbol], timeframe, CRYPTO_EPOCH, loc=loc, limit=1, max_pages=1
                        )
                    )
                    bars = page.bars.get(symbol, [])
                    row.first_ts = bars[0].timestamp if bars else None
                    row.error = None if bars else "no bars returned"
                except AlpacaError as exc:
                    row.error = _describe(exc)
                results.append(row)
                if row.error and loc in UNDESCRIBED_LOCS:
                    break  # one failed call is enough to characterise an unusable location
    for symbol in STOCKS:
        for timeframe in ("1Day", "1Hour", "1Min"):
            row = EarliestBar(symbol=symbol, venue="stocks", timeframe=timeframe)
            try:
                page = next(
                    client.iter_stock_bar_pages(
                        [symbol], timeframe, STOCK_EPOCH, limit=1, max_pages=1
                    )
                )
                bars = page.bars.get(symbol, [])
                row.first_ts = bars[0].timestamp if bars else None
                row.error = None if bars else "no bars returned"
            except AlpacaError as exc:
                row.error = _describe(exc)
            results.append(row)
    return results


def probe_history(
    client: AlpacaDataClient, now: datetime
) -> tuple[list[History], list[RecentVolume], list[DayBoundary]]:
    """Full 1Day and 1Hour history per primary symbol and location."""
    histories: list[History] = []
    volumes: list[RecentVolume] = []
    boundaries: list[DayBoundary] = []
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_start = today - RECENT_DAYS * DAY

    for symbol in PRIMARY:
        for loc in LOCS:
            daily: list[Bar] = []
            recent_hourly: dict[datetime, Bar] = {}
            for timeframe, step in (("1Day", DAY), ("1Hour", HOUR)):
                history = History(symbol=symbol, venue=loc, timeframe=timeframe)
                try:
                    for page in client.iter_crypto_bar_pages(
                        [symbol], timeframe, CRYPTO_EPOCH, loc=loc
                    ):
                        for bar in page.bars.get(symbol, []):
                            history.stats.add(bar)
                            if timeframe == "1Day":
                                daily.append(bar)
                            elif bar.timestamp >= recent_start - 10 * DAY:
                                recent_hourly[bar.timestamp] = bar
                except AlpacaError as exc:
                    history.error = _describe(exc)
                history.expected_bars = expected_bar_count(
                    history.stats.first_ts, history.stats.last_ts, step
                )
                histories.append(history)
                log.info(
                    "audit_history", symbol=symbol, loc=loc, tf=timeframe, n=history.stats.bars
                )

            recent = BarStats()
            for ts, bar in recent_hourly.items():
                if recent_start <= ts < today:
                    recent.add(bar)
            volumes.append(RecentVolume(symbol=symbol, venue=loc, days=RECENT_DAYS, stats=recent))
            boundaries.append(day_boundary(symbol, loc, daily, recent_hourly))

    for symbol in STOCKS:
        try:
            pages = client.iter_stock_bar_pages([symbol], "1Day", now - 365 * DAY)
            stock_daily = [bar for page in pages for bar in page.bars.get(symbol, [])]
            boundaries.append(day_boundary(symbol, "stocks", stock_daily, {}))
        except AlpacaError as exc:
            log.warning("audit_stock_boundary_failed", symbol=symbol, error=_describe(exc))
    return histories, volumes, boundaries


def probe_minute_windows(
    client: AlpacaDataClient, earliest: Sequence[EarliestBar], now: datetime
) -> list[MinuteWindow]:
    windows: list[MinuteWindow] = []
    latest = latest_full_week_start(now)
    first_minute = {
        (e.symbol, e.venue): e.first_ts for e in earliest if e.timeframe == "1Min" and e.first_ts
    }
    for symbol in PRIMARY:
        for loc in LOCS:
            first = first_minute.get((symbol, loc))
            if first is None:
                continue
            starts = [s for s in quarterly_week_starts(first, now) if s != latest]
            for start in [*starts, latest]:
                window = MinuteWindow(
                    symbol=symbol, venue=loc, start=start, is_latest_week=start == latest
                )
                try:
                    for page in client.iter_crypto_bar_pages(
                        [symbol], "1Min", start, start + 7 * DAY - timedelta(seconds=1), loc=loc
                    ):
                        for bar in page.bars.get(symbol, []):
                            is_weekend = bar.timestamp.astimezone(UTC).weekday() >= 5
                            (window.weekend if is_weekend else window.weekday).add(bar)
                except AlpacaError as exc:
                    window.error = _describe(exc)
                windows.append(window)
            log.info("audit_minute_windows", symbol=symbol, loc=loc, windows=len(starts) + 1)
    return windows


# --- news ------------------------------------------------------------------------------


def probe_news(client: AlpacaDataClient, start: datetime, end: datetime) -> NewsAudit:
    """Read every article tagged with the audited symbols and count them per year."""
    audit = NewsAudit(ran=True, start=start, end=end)
    labels = [*NEWS_SYMBOLS, GOLD_SET_LABEL]
    by_year: dict[str, Counter[int]] = {label: Counter() for label in labels}
    days: dict[str, set[Any]] = {label: set() for label in labels}
    first: dict[str, datetime] = {}
    try:
        for page in client.iter_news_pages(NEWS_SYMBOLS, start, end, sort="asc"):
            audit.available = True
            audit.pages += 1
            for article in page.news:
                audit.articles += 1
                created = article.created_at.astimezone(UTC)
                tagged = [s for s in NEWS_SYMBOLS if s in article.symbols]
                if GOLD_NEWS_SET.intersection(article.symbols):
                    tagged.append(GOLD_SET_LABEL)
                for label in tagged:
                    by_year[label][created.year] += 1
                    days[label].add(created.date())
                    first.setdefault(label, created)
            if audit.pages % 200 == 0 and page.news:
                log.info(
                    "audit_news_progress",
                    pages=audit.pages,
                    articles=audit.articles,
                    reached=page.news[-1].created_at.date().isoformat(),
                )
    except AlpacaError as exc:
        audit.error = _describe(exc)
        if audit.available is None:
            audit.available = False
    for label in labels:
        audit.counts.append(
            NewsCounts(
                label=label,
                by_year=dict(sorted(by_year[label].items())),
                days_with_news_by_year=dict(sorted(Counter(d.year for d in days[label]).items())),
                first_article=first.get(label),
            )
        )
    return audit


# --- generic HTTP probes ---------------------------------------------------------------


def http_probe(
    client: AlpacaDataClient,
    what: str,
    path: str,
    params: Mapping[str, Param],
    summarise: Callable[[dict[str, Any]], str],
) -> HttpProbe:
    request = path + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    try:
        body = client.get_json(path, params)
    except AlpacaHTTPError as exc:
        return HttpProbe(what=what, request=request, status=exc.status_code, detail=exc.message)
    except AlpacaError as exc:
        return HttpProbe(what=what, request=request, status=None, detail=_describe(exc))
    return HttpProbe(what=what, request=request, status=200, detail=summarise(body))


def _keys_under(key: str) -> Callable[[dict[str, Any]], str]:
    def summarise(body: dict[str, Any]) -> str:
        value = body.get(key)
        if isinstance(value, dict):
            inner = {k: (len(v) if isinstance(v, list) else v) for k, v in value.items()}
            return f"`{key}`: {inner}" if inner else f"`{key}` is empty"
        if isinstance(value, list):
            return f"`{key}`: {len(value)} items"
        return f"top-level keys: {sorted(body)}"

    return summarise


def probe_access(client: AlpacaDataClient, now: datetime) -> list[HttpProbe]:
    recent = (now - 5 * DAY).strftime("%Y-%m-%dT%H:%M:%SZ")
    older = (now - 10 * DAY).strftime("%Y-%m-%dT%H:%M:%SZ")
    crypto: dict[str, Param] = {"symbols": "BTC/USD", "timeframe": "1Day", "start": recent}
    stock: dict[str, Param] = {
        "symbols": "SPY",
        "timeframe": "1Day",
        "start": older,
        "end": recent,
        "adjustment": "all",
    }
    probes = []
    with AlpacaDataClient() as anonymous:
        probes.append(
            http_probe(
                anonymous,
                "Crypto historical bars without keys",
                "/v1beta3/crypto/us/bars",
                crypto,
                _keys_under("bars"),
            )
        )
    probes += [
        http_probe(
            client,
            "News, historical",
            "/v1beta1/news",
            {"symbols": "BTCUSD", "limit": 1},
            _keys_under("news"),
        ),
        http_probe(
            client,
            "Stock daily bars, SIP feed, older than 15 minutes",
            "/v2/stocks/bars",
            {**stock, "feed": "sip"},
            _keys_under("bars"),
        ),
        http_probe(
            client,
            "Stock daily bars, IEX feed",
            "/v2/stocks/bars",
            {**stock, "feed": "iex"},
            _keys_under("bars"),
        ),
        http_probe(
            client,
            "Stock latest bar, SIP feed (real time)",
            "/v2/stocks/bars/latest",
            {"symbols": "SPY", "feed": "sip"},
            _keys_under("bars"),
        ),
        http_probe(
            client,
            "Stock latest bar, IEX feed",
            "/v2/stocks/bars/latest",
            {"symbols": "SPY", "feed": "iex"},
            _keys_under("bars"),
        ),
    ]
    return probes


def probe_forex(client: AlpacaDataClient, now: datetime) -> list[HttpProbe]:
    start = (now - 10 * DAY).strftime("%Y-%m-%dT%H:%M:%SZ")
    probes = []
    for pair, what in (("EURUSD", "control pair"), ("XAUUSD", "gold"), ("XAU/USD", "gold")):
        probes.append(
            http_probe(
                client,
                f"Forex latest rate, {what}",
                "/v1beta1/forex/latest/rates",
                {"currency_pairs": pair},
                _keys_under("rates"),
            )
        )
    for pair, what in (("EURUSD", "control pair"), ("XAUUSD", "gold")):
        probes.append(
            http_probe(
                client,
                f"Forex historical rates, {what}",
                "/v1beta1/forex/rates",
                {"currency_pairs": pair, "timeframe": "1Day", "start": start},
                _keys_under("rates"),
            )
        )
    return probes


# --- streams ---------------------------------------------------------------------------


def _observed(messages: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for m in messages:
        extra = {k: v for k, v in m.items() if k != "T"}
        parts.append(f"{m.get('T')} {extra}" if extra else str(m.get("T")))
    return "; ".join(parts) or "no control message"


def _step(probe: StreamProbe, name: str, action: Callable[[], Sequence[Mapping[str, Any]]]) -> bool:
    """Run one stream step and record what the server said. Returns False on failure."""
    try:
        messages = action()
    except TimeoutError:
        probe.steps.append((name, "no reply within timeout"))
        return False
    except Exception as exc:
        probe.steps.append((name, f"failed: {type(exc).__name__}"))
        return False
    probe.steps.append((name, _observed(messages)))
    return not any(m.get("T") == "error" for m in messages)


def probe_stream(
    what: str,
    url: str,
    channels: Mapping[str, Sequence[str]],
    key_id: SecretStr,
    secret_key: SecretStr,
    also_open: tuple[str, str] | None = None,
) -> StreamProbe:
    """Connect, authenticate, subscribe; then open one more connection alongside."""
    probe = StreamProbe(what=what)
    try:
        first = StreamSession(url)
    except Exception as exc:
        probe.steps.append(("connect", f"failed: {type(exc).__name__}"))
        return probe
    with first:
        ok = _step(probe, "connect", first.read_control)
        ok = ok and _step(probe, "authenticate", lambda: first.authenticate(key_id, secret_key))
        if ok:
            _step(probe, f"subscribe {dict(channels)}", lambda: first.subscribe(channels))
        other_name, other_url = also_open or ("second connection to the same endpoint", url)
        try:
            second = StreamSession(other_url)
        except Exception as exc:
            probe.steps.append((f"{other_name}: connect", f"failed: {type(exc).__name__}"))
            return probe
        with second:
            if _step(probe, f"{other_name}: connect", second.read_control):
                _step(
                    probe,
                    f"{other_name}: authenticate",
                    lambda: second.authenticate(key_id, secret_key),
                )
    return probe


def probe_streams(key_id: SecretStr, secret_key: SecretStr) -> list[StreamProbe]:
    crypto_channels = {"bars": ["BTC/USD", "PAXG/USD", "ETH/USD", "SOL/USD"], "trades": ["BTC/USD"]}
    news_channels = {"news": ["BTCUSD", "PAXGUSD", "GLD", "SPY"]}
    return [
        probe_stream("Crypto stream", CRYPTO_STREAM_URL, crypto_channels, key_id, secret_key),
        probe_stream("News stream", NEWS_STREAM_URL, news_channels, key_id, secret_key),
        probe_stream(
            "Crypto and news streams open at the same time",
            CRYPTO_STREAM_URL,
            crypto_channels,
            key_id,
            secret_key,
            also_open=("news stream alongside", NEWS_STREAM_URL),
        ),
    ]


# --- orchestration ---------------------------------------------------------------------


def write_outputs(results: AuditResults) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(results.model_dump_json(indent=1), encoding="utf-8", newline="\n")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(results), encoding="utf-8", newline="\n")
    log.info("audit_written", report=str(REPORT_PATH), results=str(RESULTS_PATH))


def run_audit(
    *,
    news_start_year: int = 2015,
    skip_news: bool = False,
    skip_streams: bool = False,
    render_only: bool = False,
    settings: Settings | None = None,
) -> int:
    if render_only:
        results = AuditResults.model_validate_json(RESULTS_PATH.read_text(encoding="utf-8"))
        REPORT_PATH.write_text(render(results), encoding="utf-8", newline="\n")
        return 0

    settings = settings or load_settings()
    key_id, secret_key = settings.alpaca_api_key_id, settings.alpaca_api_secret_key
    if key_id is None or secret_key is None:
        log.error("missing_alpaca_keys", hint="copy .env.example to .env and fill in paper keys")
        return 1

    now = datetime.now(UTC).replace(microsecond=0)
    results = AuditResults(generated_at=now, authenticated=True)
    with AlpacaDataClient(key_id, secret_key) as client:
        results.access = probe_access(client, now)
        results.rate_limit_headers = dict(client.last_rate_limit)
        results.forex = probe_forex(client, now)
        log.info("audit_step_done", step="access_and_forex")
        write_outputs(results)  # checkpoint after every step so a stopped run keeps its work

        if not skip_streams:
            results.streams_ran = True
            results.streams = probe_streams(key_id, secret_key)
            log.info("audit_step_done", step="streams")
            write_outputs(results)

        results.earliest = probe_earliest(client)
        log.info("audit_step_done", step="earliest")
        write_outputs(results)
        results.history, results.recent_volume, results.day_boundaries = probe_history(client, now)
        write_outputs(results)
        results.minute_windows = probe_minute_windows(client, results.earliest, now)
        write_outputs(results)  # keep the bar results even if the long news scan fails

        if not skip_news:
            start = datetime(news_start_year, 1, 1, tzinfo=UTC)
            results.news = probe_news(client, start, now)
            log.info("audit_step_done", step="news", articles=results.news.articles)
    write_outputs(results)
    return 0
