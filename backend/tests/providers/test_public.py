"""The keyless readers of public data: where they may go, and what they bring back."""

import httpx
import pandas as pd
import pytest

from radar.providers import binance_public, cftc
from radar.providers.public import DisallowedPublicRequestError, PublicDataError, PublicReader


def reader(handler: httpx.MockTransport, allowed: frozenset[tuple[str, str]]) -> PublicReader:
    return PublicReader(allowed, transport=handler, sleep=lambda _: None)


def test_the_lists_of_public_sources_are_exactly_these() -> None:
    assert {
        ("api.binance.com", "/api/v3/klines"),
        ("fapi.binance.com", "/fapi/v1/fundingRate"),
    } == binance_public.ALLOWED
    assert {
        ("publicreporting.cftc.gov", "/resource/72hh-3qpy.json"),
        ("publicreporting.cftc.gov", "/resource/gpe5-46if.json"),
    } == cftc.ALLOWED


@pytest.mark.parametrize(
    ("host", "path"),
    [
        ("api.binance.com", "/api/v3/order"),
        ("api.binance.com", "/api/v3/account"),
        ("fapi.binance.com", "/fapi/v1/order"),
        ("fapi.binance.com", "/fapi/v2/positionRisk"),
        ("api.alpaca.markets", "/v2/orders"),
        ("example.com", "/api/v3/klines"),
    ],
)
def test_anywhere_else_is_refused_before_anything_is_sent(host: str, path: str) -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=[])

    source = reader(httpx.MockTransport(handle), binance_public.ALLOWED | cftc.ALLOWED)
    with pytest.raises(DisallowedPublicRequestError):
        source.get(host, path, {})
    assert sent == []


def test_a_request_is_a_get_with_no_key_of_any_kind() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    source = reader(httpx.MockTransport(handle), binance_public.ALLOWED)
    source.get(*binance_public.BARS, {"symbol": "BTCUSDT"})
    request = seen[0]
    assert request.method == "GET"
    assert request.url.host == "api.binance.com"
    names = {name.lower() for name in request.headers}
    assert not names & {"x-mbx-apikey", "authorization", "apca-api-key-id", "apca-api-secret-key"}
    assert "signature" not in str(request.url)
    # The reader has no way to send anything but a GET.
    assert not any(hasattr(source, verb) for verb in ("post", "put", "delete", "patch"))


def test_a_redirect_or_an_error_is_reported_not_followed() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.com/elsewhere"})

    source = reader(httpx.MockTransport(handle), binance_public.ALLOWED)
    with pytest.raises(PublicDataError, match="302"):
        source.get(*binance_public.BARS, {})


def bar(open_ms: int, close: float, volume: float = 10.0, bought: float = 6.0) -> list[str | int]:
    price = str(close)
    return [
        open_ms,
        price,
        price,
        price,
        price,
        str(volume),
        open_ms + 3_599_999,
        "0",
        5,
        str(bought),
        "0",
        "0",
    ]


def test_hourly_bars_are_read_page_by_page_and_carry_the_volume_bought() -> None:
    hour = binance_public.HOUR_MS
    calls: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startTime"])
        calls.append(start)
        count = binance_public.PAGE if start == 0 else 3
        return httpx.Response(200, json=[bar(start + i * hour, 100 + i) for i in range(count)])

    source = reader(httpx.MockTransport(handle), binance_public.ALLOWED)
    frame = binance_public.hourly_bars(source, "BTCUSDT", 0, 5000 * hour)
    assert calls == [0, binance_public.PAGE * hour]
    assert len(frame) == binance_public.PAGE + 3
    assert frame.index[0] == pd.Timestamp("1970-01-01", tz="UTC")
    assert frame.index.is_monotonic_increasing
    assert frame["taker_buy"].iloc[0] == 6.0
    assert frame["volume"].iloc[0] == 10.0


def test_funding_rates_are_indexed_by_their_payment_time() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        rows = [
            {"symbol": "BTCUSDT", "fundingTime": 0, "fundingRate": "0.0001"},
            {"symbol": "BTCUSDT", "fundingTime": 28_800_000, "fundingRate": "-0.0002"},
        ]
        return httpx.Response(200, json=rows)

    source = reader(httpx.MockTransport(handle), binance_public.ALLOWED)
    series = binance_public.funding_rates(source, "BTCUSDT", 0, 10**9)
    assert series.tolist() == [0.0001, -0.0002]
    assert series.index[1] == pd.Timestamp("1970-01-01 08:00", tz="UTC")


def test_a_positioning_report_becomes_long_short_and_open_interest_by_date() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    cftc.DATE: "2024-01-09T00:00:00.000",
                    "m_money_positions_long_all": "300",
                    "m_money_positions_short_all": "100",
                    "open_interest_all": "1000",
                },
                {
                    cftc.DATE: "2024-01-02T00:00:00.000",
                    "m_money_positions_long_all": "200",
                    "m_money_positions_short_all": "100",
                    "open_interest_all": "1000",
                },
            ],
        )

    source = reader(httpx.MockTransport(handle), cftc.ALLOWED)
    frame = cftc.positions(source, cftc.GOLD)
    assert seen[0].url.host == "publicreporting.cftc.gov"
    assert seen[0].url.params["cftc_contract_market_code"] == "088691"
    assert list(frame.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-09")]
    assert frame["long"].tolist() == [200.0, 300.0]
    assert frame["open_interest"].tolist() == [1000.0, 1000.0]
