import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from radar.ingest.raw_store import RawStore, read_raw, source_for

Load = Callable[[str], dict[str, Any]]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "alpaca"


@pytest.fixture
def load() -> Load:
    def _load(name: str) -> dict[str, Any]:
        body: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        return body

    return _load


def test_source_names() -> None:
    assert source_for("/v1beta3/crypto/us-1/bars") == "alpaca_crypto_bars_us-1"
    assert source_for("/v2/stocks/bars") == "alpaca_stock_bars"
    assert source_for("/v1beta1/news") == "alpaca_news"
    assert source_for("/v1beta3/crypto/us/latest/bars") is None


def test_bars_round_trip_unchanged(tmp_path: Path, load: Load) -> None:
    body = load("crypto_bars_page1.json")
    params = {"symbols": "BTC/USD", "timeframe": "1Hour", "page_token": None}
    path = RawStore(tmp_path).record("/v1beta3/crypto/us/bars", params, body)

    assert path is not None
    assert path.parent.parent == tmp_path / "alpaca_crypto_bars_us" / "BTC-USD"
    assert path.parent.name.startswith("date=")
    rows, metadata = read_raw(path)
    sent = body["bars"]["BTC/USD"]
    assert [{k: r[k] for k in sent[0]} for r in rows] == sent
    assert {r["symbol"] for r in rows} == {"BTC/USD"}
    assert json.loads(metadata["request"]) == {"symbols": "BTC/USD", "timeframe": "1Hour"}
    assert metadata["path"] == "/v1beta3/crypto/us/bars"


def test_news_round_trip_keeps_nested_fields(tmp_path: Path, load: Load) -> None:
    body = load("news.json")
    path = RawStore(tmp_path).record("/v1beta1/news", {"symbols": "BTCUSD"}, body)
    assert path is not None
    rows, _ = read_raw(path)
    first = body["news"][0]
    assert rows[0]["id"] == first["id"]
    assert rows[0]["symbols"] == first["symbols"]
    assert rows[0]["images"] == first["images"]
    assert rows[0]["extra"] is None


def test_unknown_fields_are_kept_in_extra(tmp_path: Path) -> None:
    bar = {"t": "2024-01-01T00:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0, "n": 0, "vw": 1}
    body = {"bars": {"GLD": [{**bar, "new_field": 7}]}}
    path = RawStore(tmp_path).record("/v2/stocks/bars", {"symbols": "GLD"}, body)
    assert path is not None
    rows, _ = read_raw(path)
    assert json.loads(rows[0]["extra"]) == {"new_field": 7}


def test_raw_layer_is_append_only(tmp_path: Path, load: Load) -> None:
    store = RawStore(tmp_path)
    body = load("crypto_bars_page1.json")
    first = store.record("/v1beta3/crypto/us/bars", {"symbols": "BTC/USD"}, body)
    assert first is not None
    before = first.read_bytes()
    second = store.record("/v1beta3/crypto/us/bars", {"symbols": "BTC/USD"}, body)
    assert second is not None
    assert second != first
    assert first.read_bytes() == before
    assert len(list(tmp_path.rglob("*.parquet"))) == 2


def test_empty_and_untracked_responses_write_nothing(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    assert store.record("/v1beta1/news", {"symbols": "GLD"}, {"news": []}) is None
    assert store.record("/v1beta3/crypto/us/latest/bars", {}, {"bars": {}}) is None
    assert list(tmp_path.rglob("*")) == []
