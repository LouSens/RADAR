"""The data profile against the real test database."""

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.ingest.upsert import bar_row, upsert_bars, upsert_news
from radar.pipelines.profile import build_profile, render
from radar.providers import schemas
from radar.universe import Universe

UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Hour", "1Day"]},
        "assets": [
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2024-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            },
            {
                "symbol": "GLD",
                "name": "Gold",
                "asset_class": "stock",
                "bars_symbol": "GLD",
                "history_start": "2024-01-01",
            },
        ],
    }
)


def wire(ts: datetime, price: float) -> schemas.Bar:
    return schemas.Bar.model_validate(
        {"t": ts, "o": price, "h": price, "l": price, "c": price, "v": 1, "n": 1, "vw": price}
    )


def seed(session: Session) -> None:
    sync_assets(session, UNIVERSE)
    rng = np.random.default_rng(0)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    hourly = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, 24 * 40)))
    for i, price in enumerate(hourly):
        if i == 500:
            continue  # one missing hour
        rows.append(
            bar_row("BTC/USD", "1Hour", "us-1", wire(start + i * timedelta(hours=1), price))
        )
    for day in range(40):
        stamp = start + day * timedelta(days=1)
        rows.append(bar_row("BTC/USD", "1Day", "us-1", wire(stamp, float(hourly[day * 24 + 23]))))
    # GLD: sessions from Tuesday 2024-01-02, daily bars stamped at midnight New York.
    for day in range(1, 40):
        stamp = start + day * timedelta(days=1)
        if stamp.weekday() >= 5 or (stamp.day == 15 and stamp.month == 1):
            continue  # weekends and Martin Luther King Jr. Day
        price = 50 + 0.1 * day
        rows.append(bar_row("GLD", "1Day", "sip", wire(stamp + timedelta(hours=5), price)))
        for hour in range(14, 21):
            rows.append(bar_row("GLD", "1Hour", "sip", wire(stamp + timedelta(hours=hour), price)))
    upsert_bars(session, rows)
    article = schemas.NewsArticle.model_validate(
        {"id": 1, "headline": "x", "created_at": start.isoformat(), "updated_at": start.isoformat()}
    )
    upsert_news(session, [article], "BTC/USD")
    session.commit()


def test_profile_measures_the_stored_data(engine: Engine, session: Session) -> None:
    seed(session)
    profile = build_profile(engine, UNIVERSE)

    coverage = {(r["symbol"], r["timeframe"]): r for r in profile.coverage.to_dict("records")}
    assert coverage[("BTC/USD", "1Hour")]["missing"] == 1
    assert coverage[("BTC/USD", "1Day")]["missing"] == 0
    assert coverage[("GLD", "1Day")]["missing"] == 0
    assert coverage[("GLD", "1Hour")]["missing"] == 0
    gold_sessions = int(coverage[("GLD", "1Day")]["bars"])

    returns = {r["symbol"]: r for r in profile.returns.to_dict("records")}
    assert returns["BTC/USD"]["days"] == 39
    assert returns["GLD"]["days"] == gold_sessions - 1

    volatility = {r["symbol"]: r for r in profile.volatility.to_dict("records")}
    assert volatility["BTC/USD"]["flagged"] == 0  # one missing hour is tolerated
    assert volatility["GLD"]["flagged"] == 1  # the first session has no previous close

    assert profile.panels["mixed_rows"] == gold_sessions
    assert list(profile.news["articles"]) == [1]

    text = render(profile)
    assert "| BTC/USD | 1Hour | 2024-01-01 |" in text
    assert "## 6. News articles per year" in text
    assert text.endswith("\n")
