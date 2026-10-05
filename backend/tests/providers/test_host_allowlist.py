"""The hard rule: market data host only, and no trading surface."""

import re
from pathlib import Path

import httpx
import pytest
import respx

from radar.providers.alpaca_rest import (
    DEFAULT_BASE_URL,
    AlpacaDataClient,
    validate_base_url,
)
from radar.providers.errors import AlpacaHTTPError, DisallowedURLError

SRC = Path(__file__).resolve().parents[2] / "src" / "radar"

FORBIDDEN_BASE_URLS = [
    "https://api.alpaca.markets",
    "https://paper-api.alpaca.markets",
    "https://broker-api.alpaca.markets",
    "https://stream.data.alpaca.markets",
    "http://data.alpaca.markets",
    "https://data.alpaca.markets.evil.example",
    "https://evil.example/data.alpaca.markets",
    "https://data.alpaca.markets@evil.example",
    "https://user:pass@data.alpaca.markets",
    "https://data.alpaca.markets:8443",
    "https://data.alpaca.markets/v2/orders",
    "https://DATA.alpaca.markets.",
    "https://localhost",
    "",
]


def test_default_base_url_is_the_data_host() -> None:
    assert DEFAULT_BASE_URL == "https://data.alpaca.markets"
    assert validate_base_url(DEFAULT_BASE_URL) == DEFAULT_BASE_URL


@pytest.mark.parametrize("url", FORBIDDEN_BASE_URLS)
def test_validate_rejects_any_other_base_url(url: str) -> None:
    with pytest.raises(DisallowedURLError):
        validate_base_url(url)


@pytest.mark.parametrize("url", FORBIDDEN_BASE_URLS)
def test_client_rejects_any_other_base_url(url: str) -> None:
    with pytest.raises(DisallowedURLError):
        AlpacaDataClient(base_url=url)


@pytest.mark.parametrize(
    "path",
    ["https://paper-api.alpaca.markets/v2/orders", "//paper-api.alpaca.markets/v2/orders", "v2/x"],
)
def test_absolute_or_scheme_relative_paths_are_rejected(
    client: AlpacaDataClient, api: respx.MockRouter, path: str
) -> None:
    with pytest.raises(DisallowedURLError):
        client.get_json(path)
    assert not api.calls


def test_redirect_to_another_host_is_not_followed(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    api.get("/v1beta1/news").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://paper-api.alpaca.markets/v2/account"}
        )
    )
    with pytest.raises(AlpacaHTTPError) as excinfo:
        client.get_json("/v1beta1/news")
    assert excinfo.value.status_code == 302
    assert len(api.calls) == 1


def test_request_hook_blocks_other_hosts() -> None:
    request = httpx.Request("GET", "https://paper-api.alpaca.markets/v2/orders")
    with pytest.raises(DisallowedURLError):
        AlpacaDataClient._assert_allowed_host(request)


def test_client_has_no_trading_surface() -> None:
    banned = re.compile(r"order|position|account|transfer|trade_api|submit|buy|sell", re.I)
    public = [name for name in dir(AlpacaDataClient) if not name.startswith("__")]
    assert [name for name in public if banned.search(name)] == []


def test_source_never_mentions_trading_hosts_or_endpoints() -> None:
    banned = re.compile(
        r"(?<![.\w])api\.alpaca\.markets|paper-api|broker-api"
        r"|/v2/(orders|positions|account|transfers|wallets)"
    )
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if banned.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
