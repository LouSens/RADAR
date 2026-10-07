from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from radar.providers.alpaca_rest import AlpacaDataClient, collect_bars
from radar.providers.errors import AlpacaError, AlpacaHTTPError, AlpacaTransportError

from .conftest import FAKE_KEY_ID, FAKE_SECRET

Load = Callable[[str], dict[str, Any]]

START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 8, tzinfo=UTC)
CRYPTO_BARS = "/v1beta3/crypto/us/bars"


# --- typed responses ---------------------------------------------------------------


def test_crypto_bars_follow_pagination_to_the_end(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    page1, page2 = load("crypto_bars_page1.json"), load("crypto_bars_page2.json")
    page2["next_page_token"] = None
    token = page1["next_page_token"]
    assert token
    second = api.get(CRYPTO_BARS, params={"page_token": token}).respond(json=page2)
    first = api.get(CRYPTO_BARS).respond(json=page1)

    bars = collect_bars(client.iter_crypto_bar_pages(["BTC/USD"], "1Hour", START, END, limit=3))[
        "BTC/USD"
    ]

    assert first.call_count == 1
    assert second.call_count == 1
    assert len(bars) == 6
    assert [b.timestamp for b in bars] == sorted(b.timestamp for b in bars)
    assert bars[0].timestamp == START
    assert all(b.timestamp.utcoffset() is not None for b in bars)
    assert all(b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high for b in bars)

    sent = first.calls.last.request.url.params
    assert sent["symbols"] == "BTC/USD"
    assert sent["timeframe"] == "1Hour"
    assert sent["start"] == "2024-01-01T00:00:00Z"
    assert sent["end"] == "2024-01-08T00:00:00Z"
    assert "page_token" not in sent


def test_max_pages_stops_pagination(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    route = api.get(CRYPTO_BARS).respond(json=load("crypto_bars_page1.json"))
    pages = list(client.iter_crypto_bar_pages(["BTC/USD"], "1Hour", START, max_pages=1))
    assert len(pages) == 1
    assert route.call_count == 1


def test_repeated_page_token_raises_instead_of_looping(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    route = api.get(CRYPTO_BARS).respond(json=load("crypto_bars_page1.json"))
    with pytest.raises(AlpacaError, match="did not advance"):
        list(client.iter_crypto_bar_pages(["BTC/USD"], "1Hour", START))
    assert route.call_count == 2


def test_stock_bars_are_requested_adjusted(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    body = load("stock_bars.json")
    body["next_page_token"] = None
    route = api.get("/v2/stocks/bars").respond(json=body)
    bars = collect_bars(client.iter_stock_bar_pages(["SPY", "GLD"], "1Day", START, END))
    assert set(bars) == {"SPY", "GLD"}
    assert bars["SPY"][0].volume > 0
    assert route.calls.last.request.url.params["adjustment"] == "all"


def test_latest_crypto_endpoints_parse(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    for kind in ("bars", "quotes", "trades"):
        api.get(f"/v1beta3/crypto/us/latest/{kind}").respond(
            json=load(f"crypto_latest_{kind}.json")
        )
    symbols = ["BTC/USD", "PAXG/USD"]

    bars = client.get_crypto_latest_bars(symbols).bars
    quotes = client.get_crypto_latest_quotes(symbols).quotes
    trades = client.get_crypto_latest_trades(symbols).trades

    assert set(bars) == set(quotes) == set(trades) == set(symbols)
    assert quotes["BTC/USD"].ask_price >= quotes["BTC/USD"].bid_price > 0
    assert trades["PAXG/USD"].price > 0
    assert quotes["BTC/USD"].timestamp.utcoffset() is not None


def test_snapshots_parse_and_allow_missing_parts(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    stocks = api.get("/v2/stocks/snapshots").respond(json=load("stock_snapshots.json"))
    api.get("/v1beta3/crypto/us-1/snapshots").respond(json=load("crypto_snapshots.json"))

    found = client.get_stock_snapshots(["AAA", "BBB"])
    coins = client.get_crypto_snapshots(["BTC/USD"], loc="us-1").snapshots

    assert stocks.calls.last.request.url.params["feed"] == "iex"
    full = found["AAA"]
    assert full.daily_bar is not None
    assert full.previous_daily_bar is not None
    assert full.daily_bar.close / full.previous_daily_bar.close - 1 == pytest.approx(
        500.5 / 495 - 1
    )
    assert full.latest_quote is not None
    assert full.latest_quote.timestamp.utcoffset() is not None
    assert found["BBB"].daily_bar is None
    assert found["BBB"].latest_quote is None
    assert coins["BTC/USD"].latest_trade is not None
    assert coins["BTC/USD"].latest_trade.price == 86000.0


def test_dividends_and_splits_parse_and_are_asked_for_by_ex_date(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    route = api.get("/v1/corporate-actions").respond(json=load("corporate_actions.json"))

    pages = list(client.iter_corporate_action_pages(["AAA"], date(2024, 1, 1), date(2024, 12, 31)))

    sent = route.calls.last.request.url.params
    assert sent["start"] == "2024-01-01"
    assert sent["end"] == "2024-12-31"
    assert sent["types"] == "cash_dividend,forward_split,reverse_split"
    actions = pages[0].corporate_actions
    assert actions.cash_dividends[0].ex_date == date(2024, 3, 5)
    assert actions.cash_dividends[0].rate == 0.04
    assert (actions.forward_splits[0].new_rate, actions.forward_splits[0].old_rate) == (10, 1)
    assert actions.reverse_splits == []


def test_option_snapshots_carry_implied_volatility_where_there_is_one(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    route = api.get("/v1beta1/options/snapshots/AAA").respond(json=load("option_snapshots.json"))

    pages = list(
        client.iter_option_snapshot_pages(
            "AAA", expires_from=date(2026, 11, 1), expires_to=date(2026, 11, 30), kind="call"
        )
    )

    sent = route.calls.last.request.url.params
    assert sent["feed"] == "indicative"
    assert sent["expiration_date_gte"] == "2026-11-01"
    assert sent["type"] == "call"
    quoted = pages[0].snapshots["AAA261113C00500000"]
    assert quoted.implied_volatility == 0.1538
    assert quoted.greeks is not None
    assert quoted.greeks.delta == 0.52
    assert pages[0].snapshots["AAA261113C00900000"].implied_volatility is None


def test_an_option_underlying_that_is_not_a_plain_symbol_is_rejected(
    client: AlpacaDataClient,
) -> None:
    with pytest.raises(ValueError, match="underlying"):
        next(client.iter_option_snapshot_pages("../v2/orders"))


def test_news_parses_and_uses_provider_symbol_format(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load
) -> None:
    body = load("news.json")
    body["next_page_token"] = None
    route = api.get("/v1beta1/news").respond(json=body)

    pages = list(client.iter_news_pages(["BTCUSD"], START, END))

    assert len(pages) == 1
    article = pages[0].news[0]
    assert article.headline.startswith("Synthetic")
    assert "BTCUSD" in article.symbols
    assert article.created_at.utcoffset() is not None
    assert article.url is not None
    assert article.url.startswith("https://example.invalid/")
    assert route.calls.last.request.url.params["symbols"] == "BTCUSD"


def test_empty_and_null_collections_parse(client: AlpacaDataClient, api: respx.MockRouter) -> None:
    api.get(CRYPTO_BARS).respond(json={"bars": None, "next_page_token": None})
    api.get("/v1beta1/news").respond(json={"news": [], "next_page_token": None})
    assert collect_bars(client.iter_crypto_bar_pages(["BTC/USD"], "1Day", START)) == {}
    assert next(client.iter_news_pages(["PAXGUSD"])).news == []


# --- input validation --------------------------------------------------------------


def test_naive_datetimes_are_rejected(client: AlpacaDataClient) -> None:
    naive = datetime(2024, 1, 1)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        next(client.iter_crypto_bar_pages(["BTC/USD"], "1Day", naive))


@pytest.mark.parametrize("loc", ["../v2", "us/../../v2/orders", "US", ""])
def test_bad_crypto_location_is_rejected(client: AlpacaDataClient, loc: str) -> None:
    with pytest.raises(ValueError, match="location"):
        client.get_crypto_latest_bars(["BTC/USD"], loc=loc)


def test_bad_timeframe_is_rejected(client: AlpacaDataClient) -> None:
    with pytest.raises(ValueError, match="timeframe"):
        next(client.iter_crypto_bar_pages(["BTC/USD"], "1Fortnight", START))


# --- retries -----------------------------------------------------------------------


def test_retries_on_429_and_5xx_then_succeeds(
    client: AlpacaDataClient, api: respx.MockRouter, load: Load, sleeps: list[float]
) -> None:
    route = api.get("/v1beta3/crypto/us/latest/bars").mock(
        side_effect=[
            httpx.Response(429, json={"message": "too many requests"}),
            httpx.Response(503),
            httpx.Response(200, json=load("crypto_latest_bars.json")),
        ]
    )
    assert client.get_crypto_latest_bars(["BTC/USD"]).bars
    assert route.call_count == 3
    assert len(sleeps) == 2
    assert 0 < sleeps[0] <= 0.5
    assert sleeps[0] < sleeps[1] * 2  # ceiling doubles; jitter keeps each in [half, full]
    assert 0.5 <= sleeps[1] <= 1.0


def test_retry_after_header_is_honoured(
    client: AlpacaDataClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    api.get("/v1beta1/news").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(200, json={"news": []}),
        ]
    )
    client.get_json("/v1beta1/news")
    assert sleeps == [7.0]


def test_gives_up_after_max_retries(
    client: AlpacaDataClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get("/v1beta1/news").respond(500, json={"message": "boom"})
    with pytest.raises(AlpacaHTTPError) as excinfo:
        client.get_json("/v1beta1/news")
    assert excinfo.value.status_code == 500
    assert route.call_count == 4  # first try plus max_retries=3
    assert len(sleeps) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(
    client: AlpacaDataClient, api: respx.MockRouter, sleeps: list[float], status: int
) -> None:
    route = api.get("/v1beta1/news").respond(status, json={"message": "nope"})
    with pytest.raises(AlpacaHTTPError) as excinfo:
        client.get_json("/v1beta1/news")
    assert excinfo.value.status_code == status
    assert excinfo.value.message == "nope"
    assert route.call_count == 1
    assert sleeps == []


def test_transport_errors_are_retried_then_raised(
    client: AlpacaDataClient, api: respx.MockRouter, sleeps: list[float]
) -> None:
    route = api.get("/v1beta1/news").mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(AlpacaTransportError):
        client.get_json("/v1beta1/news")
    assert route.call_count == 4
    assert len(sleeps) == 3


# --- secrets -----------------------------------------------------------------------


def test_auth_headers_are_sent_when_keys_are_given(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    route = api.get("/v1beta1/news").respond(json={"news": []})
    client.get_json("/v1beta1/news")
    headers = route.calls.last.request.headers
    assert headers["APCA-API-KEY-ID"] == FAKE_KEY_ID
    assert headers["APCA-API-SECRET-KEY"] == FAKE_SECRET


def test_no_auth_headers_without_keys(api: respx.MockRouter) -> None:
    route = api.get("/v1beta3/crypto/us/latest/bars").respond(json={"bars": {}})
    with AlpacaDataClient() as anonymous:
        anonymous.get_crypto_latest_bars(["BTC/USD"])
    headers = route.calls.last.request.headers
    assert "APCA-API-KEY-ID" not in headers
    assert "APCA-API-SECRET-KEY" not in headers


def test_half_configured_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="both"):
        AlpacaDataClient(SecretStr(FAKE_KEY_ID), None)


def test_keys_never_appear_in_errors_or_repr(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    api.get("/v1beta1/news").respond(403, json={"message": "forbidden"})
    with pytest.raises(AlpacaHTTPError) as excinfo:
        client.get_json("/v1beta1/news")
    for text in (str(excinfo.value), repr(excinfo.value), repr(client), str(vars(client))):
        assert FAKE_KEY_ID not in text
        assert FAKE_SECRET not in text


def test_rate_limit_headers_are_recorded(client: AlpacaDataClient, api: respx.MockRouter) -> None:
    api.get("/v1beta1/news").respond(
        json={"news": []}, headers={"X-RateLimit-Limit": "200", "X-RateLimit-Remaining": "199"}
    )
    client.get_json("/v1beta1/news")
    assert client.last_rate_limit == {"x-ratelimit-limit": "200", "x-ratelimit-remaining": "199"}
