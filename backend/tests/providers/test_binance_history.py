"""The account-history reader: it lists past events and can do nothing else."""

import hashlib
import hmac
import inspect
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
import pytest
from pydantic import SecretStr

from radar.providers import binance_history
from radar.providers.binance import BinanceError, DisallowedRequestError
from radar.providers.binance_history import BinanceHistory

KEY = SecretStr("test-key-not-real")
SECRET = SecretStr("test-secret-not-real")
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 30, tzinfo=UTC)
T0 = 1_790_000_000_000

BODIES: dict[str, object] = {
    "/api/v3/time": {"serverTime": T0},
    "/api/v3/myTrades": [
        {
            "symbol": "SOLUSDT",
            "id": 7,
            "price": "150.0",
            "qty": "2.0",
            "quoteQty": "300.0",
            "commission": "0.002",
            "commissionAsset": "SOL",
            "time": T0,
            "isBuyer": True,
        },
        {
            "symbol": "SOLUSDT",
            "id": 8,
            "price": "180.0",
            "qty": "0.5",
            "quoteQty": "90.0",
            "commission": "0.09",
            "commissionAsset": "USDT",
            "time": T0 + 1000,
            "isBuyer": False,
        },
    ],
    "/sapi/v1/capital/deposit/hisrec": [{"coin": "USDT", "amount": "500", "insertTime": T0}],
    "/sapi/v1/capital/withdraw/history": [
        {"coin": "USDT", "amount": "100", "applyTime": "2026-09-22 10:00:00"}
    ],
    "/sapi/v1/convert/tradeFlow": {
        "list": [
            {
                "orderStatus": "SUCCESS",
                "fromAsset": "USDT",
                "fromAmount": "200",
                "toAsset": "BTC",
                "toAmount": "0.002",
                "createTime": T0,
            },
            {
                "orderStatus": "FAIL",
                "fromAsset": "USDT",
                "fromAmount": "1",
                "toAsset": "BTC",
                "toAmount": "0",
                "createTime": T0,
            },
        ]
    },
    "/sapi/v1/fiat/payments": {
        "data": [
            {
                "status": "Completed",
                "cryptoCurrency": "BTC",
                "obtainAmount": "0.001",
                "sourceAmount": "100",
                "fiatCurrency": "USD",
                "totalFee": "2",
                "createTime": T0,
            }
        ]
    },
    "/sapi/v1/asset/assetDividend": {
        "rows": [{"asset": "USDT", "amount": "0.5", "divTime": T0, "enInfo": "Flexible"}]
    },
    "/fapi/v1/income": [
        {"incomeType": "FUNDING_FEE", "asset": "USDT", "income": "-0.4", "time": T0, "symbol": "X"}
    ],
    "/sapi/v1/accountSnapshot": {
        "snapshotVos": [
            {
                "updateTime": T0,
                "data": {
                    "balances": [
                        {"asset": "BTC", "free": "0.1", "locked": "0.05"},
                        {"asset": "ETH", "free": "0", "locked": "0"},
                    ]
                },
            }
        ]
    },
}


def account(requests: list[httpx.Request], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path != "/api/v3/time" and status != 200:
            return httpx.Response(status, json={"code": -2015, "msg": "Invalid API-key."})
        return httpx.Response(200, json=BODIES[request.url.path])

    return httpx.MockTransport(handler)


def read_everything(history: BinanceHistory) -> None:
    history.fills("SOLUSDT")
    history.movements(START, END)
    history.conversions(START, END)
    history.card_purchases(START, END)
    history.rewards(START, END)
    history.futures_income(START, END)
    history.daily_balances()


def test_every_request_is_a_signed_get_to_a_listed_endpoint_with_no_body() -> None:
    requests: list[httpx.Request] = []
    read_everything(BinanceHistory(KEY, SECRET, transport=account(requests)))

    assert {(r.url.host, r.url.path) for r in requests} == set(binance_history.ALLOWED)
    assert all(r.method == "GET" for r in requests)
    assert all(r.content == b"" for r in requests)
    assert "x-mbx-apikey" not in requests[0].headers  # the clock needs no key
    for request in requests[1:]:
        query = request.url.query.decode()
        unsigned, signature = query.rsplit("&signature=", 1)
        assert "timestamp" in dict(parse_qsl(unsigned))
        expected = hmac.new(
            SECRET.get_secret_value().encode(), unsigned.encode(), hashlib.sha256
        ).hexdigest()
        assert signature == expected
        assert SECRET.get_secret_value() not in str(request.url)


def test_the_listed_endpoints_are_exactly_the_eight_agreed_and_the_clock() -> None:
    assert {
        ("api.binance.com", "/api/v3/time"),
        ("api.binance.com", "/api/v3/myTrades"),
        ("api.binance.com", "/sapi/v1/accountSnapshot"),
        ("api.binance.com", "/sapi/v1/capital/deposit/hisrec"),
        ("api.binance.com", "/sapi/v1/capital/withdraw/history"),
        ("api.binance.com", "/sapi/v1/convert/tradeFlow"),
        ("api.binance.com", "/sapi/v1/fiat/payments"),
        ("api.binance.com", "/sapi/v1/asset/assetDividend"),
        ("fapi.binance.com", "/fapi/v1/income"),
    } == binance_history.ALLOWED


@pytest.mark.parametrize(
    ("method", "host", "path"),
    [
        ("POST", "api.binance.com", "/api/v3/myTrades"),
        ("DELETE", "api.binance.com", "/api/v3/myTrades"),
        ("POST", "api.binance.com", "/api/v3/order"),
        ("GET", "api.binance.com", "/api/v3/openOrders"),
        ("GET", "api.binance.com", "/api/v3/allOrders"),
        ("POST", "api.binance.com", "/sapi/v1/capital/withdraw/apply"),
        ("GET", "api.binance.com", "/sapi/v1/capital/withdraw/apply"),
        ("POST", "api.binance.com", "/sapi/v1/capital/withdraw/history"),
        ("POST", "api.binance.com", "/sapi/v1/convert/acceptQuote"),
        ("POST", "api.binance.com", "/sapi/v1/convert/getQuote"),
        ("POST", "api.binance.com", "/sapi/v1/asset/transfer"),
        ("POST", "fapi.binance.com", "/fapi/v1/order"),
        ("GET", "fapi.binance.com", "/fapi/v1/userTrades"),
        ("GET", "api.binance.com.evil.example", "/api/v3/myTrades"),
        ("GET", "api.binance.us", "/api/v3/myTrades"),
        ("GET", "api.binance.com", "/api/v3/myTrades/../order"),
        ("GET", "fapi.binance.com", "/api/v3/myTrades"),
    ],
)
def test_anything_else_is_refused_before_it_is_sent(method: str, host: str, path: str) -> None:
    with pytest.raises(DisallowedRequestError):
        binance_history.check(method, host, path)
    requests: list[httpx.Request] = []
    history = BinanceHistory(KEY, SECRET, transport=account(requests))
    if method == "GET":
        with pytest.raises(DisallowedRequestError):
            history._get((host, path))
    assert requests == []


def test_the_reader_has_no_way_to_act_on_the_account() -> None:
    public = sorted(name for name in dir(BinanceHistory) if not name.startswith("_"))
    assert public == [
        "card_purchases",
        "close",
        "conversions",
        "daily_balances",
        "fills",
        "futures_income",
        "movements",
        "rewards",
    ]
    source = Path(inspect.getfile(binance_history)).read_text(encoding="utf-8")
    # One checked way out, GET only, and no path that places, quotes, applies or moves.
    assert source.count("self._client.send(") == 1
    assert not re.search(r"\.(get|post|put|delete|patch|request)\(f?[\"']http", source)
    assert not re.search(r"\"(POST|PUT|DELETE|PATCH)\"", source)
    assert not re.search(
        r"/(order|openOrders|allOrders|apply|transfer|leverage|loan|repay|acceptQuote|getQuote)\b",
        source,
    )


def test_fills_give_what_was_paid_and_follow_pages_by_id() -> None:
    requests: list[httpx.Request] = []
    fills = BinanceHistory(KEY, SECRET, transport=account(requests)).fills("SOLUSDT", since=START)

    assert [(f.bought, f.quantity, f.price, f.amount) for f in fills] == [
        (True, 2.0, 150.0, 300.0),
        (False, 0.5, 180.0, 90.0),
    ]
    assert fills[0].at.utcoffset() is not None
    sent = dict(parse_qsl(requests[1].url.query.decode()))
    assert sent["symbol"] == "SOLUSDT"
    assert sent["startTime"] == str(int(START.timestamp() * 1000))


def test_the_other_reads_parse_and_skip_what_did_not_complete() -> None:
    history = BinanceHistory(KEY, SECRET, transport=account([]))

    moves = history.movements(START, END)
    assert [(m.asset, m.quantity, m.arrived) for m in moves] == [
        ("USDT", 500.0, True),
        ("USDT", 100.0, False),
    ]
    swaps = history.conversions(START, END)
    assert [(s.from_asset, s.from_quantity, s.to_asset, s.to_quantity) for s in swaps] == [
        ("USDT", 200.0, "BTC", 0.002)
    ]
    bought = history.card_purchases(START, END)
    assert (bought[0].asset, bought[0].quantity, bought[0].paid, bought[0].fee) == (
        "BTC",
        0.001,
        100.0,
        2.0,
    )
    assert history.rewards(START, END)[0].quantity == 0.5
    assert history.futures_income(START, END)[0].amount == -0.4
    balances = history.daily_balances()
    assert list(balances.values()) == [{"BTC": pytest.approx(0.15)}]


def test_a_time_without_a_zone_is_rejected() -> None:
    history = BinanceHistory(KEY, SECRET, transport=account([]))
    with pytest.raises(ValueError, match="zone"):
        history.movements(datetime(2026, 9, 1), END)  # noqa: DTZ001


def test_a_refused_key_gives_a_plain_error_without_credentials() -> None:
    history = BinanceHistory(KEY, SECRET, transport=account([], status=401))
    with pytest.raises(BinanceError) as caught:
        history.fills("SOLUSDT")
    message = str(caught.value)
    assert "401" in message
    assert KEY.get_secret_value() not in message
    assert SECRET.get_secret_value() not in message
