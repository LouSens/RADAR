import json

import pytest

from radar.providers.alpaca_stream import (
    CRYPTO_STREAM_URL,
    NEWS_STREAM_URL,
    StreamSession,
    control_messages,
    validate_stream_url,
)
from radar.providers.errors import DisallowedURLError


@pytest.mark.parametrize("url", [CRYPTO_STREAM_URL, NEWS_STREAM_URL])
def test_data_stream_urls_are_allowed(url: str) -> None:
    assert validate_stream_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "wss://paper-api.alpaca.markets/stream",
        "wss://api.alpaca.markets/stream",
        "ws://stream.data.alpaca.markets/v1beta1/news",
        "https://stream.data.alpaca.markets/v1beta1/news",
        "wss://stream.data.alpaca.markets.evil.example/v1beta1/news",
        "wss://stream.data.alpaca.markets@evil.example/v1beta1/news",
        "wss://stream.data.alpaca.markets:8443/v1beta1/news",
        "wss://data.alpaca.markets/v1beta1/news",
        "",
    ],
)
def test_any_other_stream_url_is_rejected(url: str) -> None:
    with pytest.raises(DisallowedURLError):
        validate_stream_url(url)
    with pytest.raises(DisallowedURLError):
        StreamSession(url)


def test_control_messages_drop_market_data() -> None:
    frame = json.dumps(
        [
            {"T": "b", "S": "BTC/USD", "o": 1.0},
            {"T": "success", "msg": "authenticated"},
            {"T": "error", "code": 406, "msg": "connection limit exceeded"},
        ]
    )
    assert [m["T"] for m in control_messages(frame)] == ["success", "error"]
    assert control_messages(json.dumps({"T": "subscription", "bars": ["BTC/USD"]})) == [
        {"T": "subscription", "bars": ["BTC/USD"]}
    ]
