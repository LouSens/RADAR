"""The Binance source: it reads holdings and can do nothing else."""

import hashlib
import hmac
import inspect
import re
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest
from pydantic import SecretStr

from radar.models.holdings import HoldingsSource
from radar.providers import binance
from radar.providers.binance import BinanceError, BinanceSource, DisallowedRequestError

KEY = SecretStr("test-key-not-real")
SECRET = SecretStr("test-secret-not-real")
KNOWN = ["BTC/USD", "ETH/USD", "PAXG/USD", "SPY"]

SPOT = {
    "balances": [
        {"asset": "BTC", "free": "0.40000000", "locked": "0.10000000"},
        {"asset": "LDETH", "free": "2.00000000", "locked": "0"},
        {"asset": "PAXG", "free": "1.5", "locked": "0"},
        {"asset": "USDT", "free": "250.0", "locked": "0"},
        {"asset": "DOGE", "free": "1000", "locked": "0"},
        {"asset": "BNB", "free": "0.000000001", "locked": "0"},
    ]
}
MARGIN = {"userAssets": [{"asset": "ETH", "netAsset": "0.5"}]}
FUTURES = [
    {
        "symbol": "BTCUSDT",
        "positionAmt": "-0.200",
        "entryPrice": "90000",
        "markPrice": "80000",
        "liquidationPrice": "100000",
        "leverage": "5",
    },
    {
        "symbol": "PAXGUSDT",
        "positionAmt": "-3",
        "entryPrice": "4000",
        "markPrice": "4100",
        "liquidationPrice": "0",
        "leverage": "2",
    },
    {"symbol": "SOLUSDT", "positionAmt": "0", "entryPrice": "0", "markPrice": "150"},
]


def account(
    requests: list[httpx.Request], *, margin_status: int = 200, spot_status: int = 200
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_790_000_000_000})
        if path == "/api/v3/account":
            if spot_status != 200:
                return httpx.Response(spot_status, json={"code": -2015, "msg": "Invalid API-key."})
            return httpx.Response(200, json=SPOT)
        if path == "/sapi/v1/margin/account":
            return httpx.Response(margin_status, json=MARGIN if margin_status == 200 else {})
        if path == "/fapi/v2/positionRisk":
            return httpx.Response(200, json=FUTURES)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_it_reads_balances_and_nets_them_with_futures() -> None:
    requests: list[httpx.Request] = []
    source = BinanceSource(KEY, SECRET, KNOWN, transport=account(requests))
    reading = source.read_account()

    assert reading.holdings.source == "binance"
    assert [(h.symbol, round(h.quantity, 8)) for h in reading.holdings.holdings] == [
        ("BTC/USD", 0.3),  # 0.5 held, 0.2 sold short in futures
        ("ETH/USD", 2.5),  # 2 lent out through savings, 0.5 in margin
    ]
    left_out = {u.symbol: u.reason for u in reading.holdings.unsupported}
    assert left_out == {
        "DOGE": "RADAR has no price history for this.",
        "PAXG/USD": "Net short or flat after futures. Only long exposure is analysed.",
        "USDT": "A cash balance. It is left out of the risk figures.",
    }
    bitcoin, gold = reading.leveraged
    assert (bitcoin.symbol, bitcoin.quantity, bitcoin.leverage) == ("BTC/USD", -0.2, 5)
    assert bitcoin.distance_to_liquidation == pytest.approx(0.25)
    assert gold.liquidation_price is None
    assert gold.distance_to_liquidation is None


def test_every_request_is_a_get_to_a_reading_endpoint_and_is_signed() -> None:
    requests: list[httpx.Request] = []
    source: HoldingsSource = BinanceSource(KEY, SECRET, KNOWN, transport=account(requests))
    source.read()

    assert [(r.method, r.url.host, r.url.path) for r in requests] == [
        ("GET", "api.binance.com", "/api/v3/time"),
        ("GET", "api.binance.com", "/api/v3/account"),
        ("GET", "api.binance.com", "/sapi/v1/margin/account"),
        ("GET", "fapi.binance.com", "/fapi/v2/positionRisk"),
    ]
    assert all((r.url.host, r.url.path) in binance.ALLOWED for r in requests)
    assert all(r.content == b"" for r in requests)
    assert "x-mbx-apikey" not in requests[0].headers  # the clock needs no key
    for request in requests[1:]:
        assert request.headers["x-mbx-apikey"] == KEY.get_secret_value()
        query = request.url.query.decode()
        unsigned, signature = query.rsplit("&signature=", 1)
        assert dict(parse_qsl(unsigned))["timestamp"] == "1790000000000"
        expected = hmac.new(
            SECRET.get_secret_value().encode(), unsigned.encode(), hashlib.sha256
        ).hexdigest()
        assert signature == expected
        assert SECRET.get_secret_value() not in str(request.url)


@pytest.mark.parametrize(
    ("method", "host", "path"),
    [
        ("POST", "api.binance.com", "/api/v3/account"),
        ("DELETE", "api.binance.com", "/api/v3/account"),
        ("GET", "api.binance.com", "/api/v3/openOrders"),
        ("POST", "api.binance.com", "/api/v3/order"),
        ("POST", "api.binance.com", "/sapi/v1/capital/withdraw/apply"),
        ("POST", "api.binance.com", "/sapi/v1/asset/transfer"),
        ("POST", "api.binance.com", "/sapi/v1/margin/loan"),
        ("POST", "fapi.binance.com", "/fapi/v1/order"),
        ("POST", "fapi.binance.com", "/fapi/v1/leverage"),
        ("GET", "fapi.binance.com", "/api/v3/account"),
        ("GET", "api.binance.com.evil.example", "/api/v3/account"),
        ("GET", "api.binance.us", "/api/v3/account"),
        ("GET", "api.binance.com", "/api/v3/account/../order"),
    ],
)
def test_anything_but_reading_is_refused_before_it_is_sent(
    method: str, host: str, path: str
) -> None:
    with pytest.raises(DisallowedRequestError):
        binance.check(method, host, path)
    if (host, path) in binance.ALLOWED:
        return  # the client has no way to send anything but a GET
    requests: list[httpx.Request] = []
    source = BinanceSource(KEY, SECRET, KNOWN, transport=account(requests))
    with pytest.raises(DisallowedRequestError):
        source._get((host, path), signed=True, clock=1)
    assert requests == []


def test_the_source_has_no_way_to_trade_or_move_funds() -> None:
    public = [name for name in dir(BinanceSource) if not name.startswith("_")]
    assert sorted(public) == ["close", "name", "read", "read_account"]
    banned = re.compile(r"order|withdraw|transfer|trade|buy|sell|cancel|loan|repay", re.I)
    members = [name for name, _ in inspect.getmembers(binance) if banned.search(name)]
    assert members == []
    source = Path(inspect.getfile(binance)).read_text(encoding="utf-8")
    # No writing verb is ever used on the HTTP client, and no trading path is spelled out.
    assert not re.search(r"\.(post|put|delete|patch|request)\(", source)
    assert not re.search(r"/(order|openOrders|withdraw|transfer|leverage|loan|repay)\b", source)
    assert len(binance.ALLOWED) == 4


def test_margin_or_futures_being_switched_off_is_not_an_error() -> None:
    requests: list[httpx.Request] = []
    source = BinanceSource(KEY, SECRET, KNOWN, transport=account(requests, margin_status=400))
    symbols = [h.symbol for h in source.read().holdings]
    assert symbols == ["BTC/USD", "ETH/USD"]


def test_a_refused_key_gives_a_plain_error_without_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = BinanceSource(KEY, SECRET, KNOWN, transport=account([], spot_status=401))
    with pytest.raises(BinanceError) as excinfo:
        source.read()
    message = str(excinfo.value)
    assert "401" in message
    assert "Invalid API-key" in message
    for secret in (KEY, SECRET):
        assert secret.get_secret_value() not in message
        assert secret.get_secret_value() not in caplog.text
        assert secret.get_secret_value() not in repr(source.__dict__)


def test_a_network_failure_is_reported_without_the_request() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    source = BinanceSource(KEY, SECRET, KNOWN, transport=httpx.MockTransport(broken))
    with pytest.raises(BinanceError, match="Could not reach Binance") as excinfo:
        source.read()
    assert excinfo.value.__cause__ is None
    assert "signature" not in str(excinfo.value)
