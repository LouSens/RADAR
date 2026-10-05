"""The raw layer: every provider response, appended as Parquet and never changed.

Layout: `<root>/<source>/<symbol>/date=<day received>/<time>_<id>.parquet`. Files are
only ever added. The clean layer is built from typed rows elsewhere; this layer exists
so anything can be rebuilt from what the provider actually sent.
"""

import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from radar.logging import get_logger

log = get_logger(__name__)

DEFAULT_ROOT = Path("data/raw")

BAR_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("t", pa.string()),
        ("o", pa.float64()),
        ("h", pa.float64()),
        ("l", pa.float64()),
        ("c", pa.float64()),
        ("v", pa.float64()),
        ("n", pa.int64()),
        ("vw", pa.float64()),
        ("extra", pa.string()),
    ]
)
NEWS_SCHEMA = pa.schema(
    [
        ("id", pa.int64()),
        ("headline", pa.string()),
        ("author", pa.string()),
        ("created_at", pa.string()),
        ("updated_at", pa.string()),
        ("summary", pa.string()),
        ("content", pa.string()),
        ("url", pa.string()),
        ("source", pa.string()),
        ("symbols", pa.list_(pa.string())),
        ("images", pa.list_(pa.struct([("size", pa.string()), ("url", pa.string())]))),
        ("extra", pa.string()),
    ]
)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_CRYPTO_BARS = re.compile(r"^/v1beta3/crypto/([a-z0-9-]+)/bars$")


def source_for(path: str) -> str | None:
    """Name the raw source for an API path, or None if the path is not stored."""
    crypto = _CRYPTO_BARS.match(path)
    if crypto:
        return f"alpaca_crypto_bars_{crypto.group(1)}"
    if path == "/v2/stocks/bars":
        return "alpaca_stock_bars"
    if path == "/v1beta1/news":
        return "alpaca_news"
    return None


def _rows(body: Mapping[str, Any], schema: pa.Schema) -> list[dict[str, Any]]:
    """Flatten a response into rows; fields outside the schema go to `extra` as JSON."""
    known = set(schema.names)
    if "news" in body:
        items = [(None, article) for article in body.get("news") or []]
    else:
        items = [(symbol, bar) for symbol, bars in (body.get("bars") or {}).items() for bar in bars]
    rows = []
    for symbol, item in items:
        row = {key: value for key, value in item.items() if key in known}
        if symbol is not None:
            row["symbol"] = symbol
        unknown = {key: value for key, value in item.items() if key not in known}
        row["extra"] = json.dumps(unknown, sort_keys=True) if unknown else None
        rows.append(row)
    return rows


class RawStore:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = root

    def record(self, path: str, params: Mapping[str, Any], body: dict[str, Any]) -> Path | None:
        """Store one response page. Usable directly as `AlpacaDataClient.on_page`."""
        source = source_for(path)
        if source is None:
            return None
        schema = NEWS_SCHEMA if source == "alpaca_news" else BAR_SCHEMA
        rows = _rows(body, schema)
        if not rows:
            return None

        received = datetime.now(UTC)
        request = {k: v for k, v in params.items() if v is not None and k != "page_token"}
        metadata = {
            "source": source,
            "path": path,
            "request": json.dumps(request, sort_keys=True),
            "received_at": received.isoformat(),
        }
        table = pa.Table.from_pylist(rows, schema=schema.with_metadata(metadata))

        symbol = _UNSAFE.sub("-", str(params.get("symbols", "all"))) or "all"
        directory = self.root / source / symbol / f"date={received:%Y-%m-%d}"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{received:%H%M%S%f}_{uuid.uuid4().hex[:8]}.parquet"
        # Exclusive create: an existing raw file is never overwritten.
        with target.open("xb") as handle:
            pq.write_table(table, handle, compression="zstd")
        return target


def read_raw(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Read one raw file back as rows plus its request metadata."""
    table = pq.read_table(path)
    metadata = {k.decode(): v.decode() for k, v in (table.schema.metadata or {}).items()}
    return table.to_pylist(), metadata
