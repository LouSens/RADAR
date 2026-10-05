import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from pydantic import SecretStr

from radar.providers.alpaca_rest import DEFAULT_BASE_URL, AlpacaDataClient
from radar.providers.rate_limit import TokenBucket

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "alpaca"

FAKE_KEY_ID = "test-key-id-not-real"
FAKE_SECRET = "test-secret-not-real"  # noqa: S105


@pytest.fixture
def load() -> Callable[[str], dict[str, Any]]:
    def _load(name: str) -> dict[str, Any]:
        body: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        return body

    return _load


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    """Mock of the data host. Any request to another host fails the test."""
    with respx.mock(base_url=DEFAULT_BASE_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(api: respx.MockRouter, sleeps: list[float]) -> Iterator[AlpacaDataClient]:
    limiter = TokenBucket(rate_per_minute=6000, capacity=1000)
    with AlpacaDataClient(
        SecretStr(FAKE_KEY_ID),
        SecretStr(FAKE_SECRET),
        rate_limiter=limiter,
        max_retries=3,
        sleep=sleeps.append,
    ) as c:
        yield c
