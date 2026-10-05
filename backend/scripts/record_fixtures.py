"""Record test fixtures from the live Alpaca data API.

Run with `uv run python backend/scripts/record_fixtures.py`. Needs `.env`.

Only response bodies are written. Auth headers never reach disk. Market data keeps the
real structure with a few trimmed rows. News keeps the real schema and field types, but
every piece of text (headline, summary, author, content, URLs) is replaced with invented
values, so no provider text is committed.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radar.config import load_settings
from radar.logging import configure_logging, get_logger
from radar.providers.alpaca_rest import AlpacaDataClient, Param

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "alpaca"
ROWS = 3
CRYPTO = "BTC/USD,PAXG/USD"

log = get_logger("record_fixtures")


def trim(body: dict[str, Any], key: str) -> dict[str, Any]:
    """Keep the first few rows per symbol."""
    rows = body.get(key)
    if isinstance(rows, dict):
        body[key] = {s: v[:ROWS] if isinstance(v, list) else v for s, v in rows.items()}
    return body


def synthesise_news(body: dict[str, Any]) -> dict[str, Any]:
    """Replace all provider text with invented values, keeping keys and types."""
    keep = {"created_at", "updated_at", "symbols", "source"}
    articles: list[dict[str, Any]] = []
    for n, real in enumerate(body.get("news", [])[:ROWS], start=1):
        fake: dict[str, Any] = {}
        for key, value in real.items():
            if key in keep or isinstance(value, bool) or value is None:
                fake[key] = value
            elif key == "id":
                fake[key] = 90_000_000 + n
            elif key == "url":
                fake[key] = f"https://example.invalid/news/{n}"
            elif key == "images":
                fake[key] = [
                    {"size": size, "url": f"https://example.invalid/images/{n}-{size}.png"}
                    for size in ("large", "small", "thumb")
                ]
            elif key == "author":
                fake[key] = f"Test Author {n}"
            elif key == "content":
                fake[key] = ""
            elif isinstance(value, str):
                fake[key] = f"Synthetic {key} {n}: an invented sentence for tests."
            elif isinstance(value, int | float):
                fake[key] = 0
            else:
                fake[key] = type(value)()
        articles.append(fake)
    return {**body, "news": articles}


def write(name: str, body: dict[str, Any]) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / name).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    log.info("fixture_written", name=name)


def main() -> int:
    configure_logging()
    settings = load_settings()
    if settings.alpaca_api_key_id is None or settings.alpaca_api_secret_key is None:
        log.error("missing_alpaca_keys", hint="fill in .env")
        return 1

    start = datetime(2024, 1, 1, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = datetime(2024, 1, 8, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    bars: dict[str, Param] = {
        "symbols": "BTC/USD",
        "timeframe": "1Hour",
        "start": start,
        "end": end,
        "limit": ROWS,
    }

    with AlpacaDataClient(settings.alpaca_api_key_id, settings.alpaca_api_secret_key) as client:
        page1 = client.get_json("/v1beta3/crypto/us/bars", bars)
        write("crypto_bars_page1.json", page1)
        page2 = client.get_json(
            "/v1beta3/crypto/us/bars", {**bars, "page_token": page1["next_page_token"]}
        )
        write("crypto_bars_page2.json", page2)

        for kind in ("bars", "quotes", "trades"):
            body = client.get_json(f"/v1beta3/crypto/us/latest/{kind}", {"symbols": CRYPTO})
            write(f"crypto_latest_{kind}.json", body)

        stocks = client.get_json(
            "/v2/stocks/bars",
            {
                "symbols": "SPY,GLD",
                "timeframe": "1Day",
                "start": start,
                "end": end,
                "adjustment": "all",
                "limit": 2 * ROWS,
            },
        )
        write("stock_bars.json", trim(stocks, "bars"))

        news = client.get_json("/v1beta1/news", {"symbols": "BTCUSD", "limit": ROWS})
        write("news.json", synthesise_news(news))
    return 0


if __name__ == "__main__":
    sys.exit(main())
