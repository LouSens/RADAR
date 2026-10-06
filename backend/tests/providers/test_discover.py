"""Finding assets the user holds that RADAR does not know yet."""

from datetime import date

import respx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.assets import sync_assets
from radar.db.models import Asset as AssetRow
from radar.db.models import Bar
from radar.models.holdings import NO_HISTORY, Holding, Holdings, Unsupported, resolve
from radar.pipelines import discover
from radar.pipelines import portfolio as job
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.binance import BinanceReading
from radar.universe import Universe

STOCK_BARS = "/v2/stocks/bars"
CRYPTO_BARS = "/v1beta3/crypto/us-1/bars"
UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Day"], "stock": ["1Day"]},
        "assets": [
            {
                "symbol": "BTC/USD",
                "name": "Bitcoin",
                "asset_class": "crypto",
                "is_primary": True,
                "bars_symbol": "BTC/USD",
                "history_start": "2021-01-01",
                "news_symbols": ["BTCUSD"],
                "news_start": "2022-01-01",
            }
        ],
    }
)


def bar(day: str, close: float = 10.0) -> dict[str, object]:
    return {
        "t": f"{day}T05:00:00Z",
        "o": close,
        "h": close,
        "l": close,
        "c": close,
        "v": 100,
        "n": 5,
        "vw": close,
    }


def page(symbol: str, *days: str) -> dict[str, object]:
    return {"bars": {symbol: [bar(d) for d in days]} if days else {}, "next_page_token": None}


def test_a_stock_name_is_looked_up_as_a_stock_only(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    stocks = api.get(STOCK_BARS).respond(json=page("PURR", "2025-12-03", "2025-12-04"))
    crypto = api.get(CRYPTO_BARS).respond(json=page("PURR/USD", "2024-01-01"))
    found = discover.find(client, "EQ_PURR", "us-1")
    assert found is not None
    assert (found.symbol, found.asset_class, found.bars_symbol) == ("PURR", "stock", "PURR")
    assert found.history_start == date(2025, 12, 3)
    assert stocks.call_count == 1
    assert crypto.call_count == 0
    assert stocks.calls.last.request.url.params["feed"] == "iex"


def test_any_other_name_is_looked_up_as_a_crypto_pair_only(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    # LINK is both a crypto name and a stock ticker: the stock must not be matched.
    stocks = api.get(STOCK_BARS).respond(json=page("LINK", "2020-01-02"))
    crypto = api.get(CRYPTO_BARS).respond(json=page("LINK/USD", "2021-03-01", "2021-03-02"))
    found = discover.find(client, "link", "us-1")
    assert found is not None
    assert (found.symbol, found.asset_class) == ("LINK/USD", "crypto")
    assert found.history_start == date(2021, 3, 1)
    assert stocks.call_count == 0
    assert crypto.call_count == 1


def test_a_name_with_no_prices_or_an_odd_name_finds_nothing(
    client: AlpacaDataClient, api: respx.MockRouter
) -> None:
    stocks = api.get(STOCK_BARS).respond(json=page("NOPE"))
    crypto = api.get(CRYPTO_BARS).respond(json=page("NOPE/USD"))
    assert discover.find(client, "EQ_NOPE", "us-1") is None
    assert discover.find(client, "NOPE", "us-1") is None
    calls = stocks.call_count + crypto.call_count
    for odd in ("", "A B", "../../x", "X" * 11, "DROP;TABLE"):
        assert discover.find(client, odd, "us-1") is None
    assert stocks.call_count + crypto.call_count == calls  # nothing was sent for those


def test_a_stock_name_never_resolves_to_a_crypto_pair() -> None:
    known = ["SOL/USD", "SPY"]
    assert resolve("EQ_SPY", known) == "SPY"
    assert resolve("EQ_SOL", known) is None
    assert resolve("SOL", known) == "SOL/USD"


def test_discovery_registers_the_asset_and_fetches_its_history(
    client: AlpacaDataClient, api: respx.MockRouter, engine: Engine, session: Session
) -> None:
    sync_assets(session, UNIVERSE)
    session.commit()
    api.get(STOCK_BARS).respond(json=page("PURR", "2025-12-03", "2025-12-04", "2025-12-05"))

    found = discover.discover(client, engine, UNIVERSE, ["EQ_PURR", "EQ_PURR"])
    assert [a.symbol for a in found] == ["PURR"]

    row = session.scalars(select(AssetRow).where(AssetRow.symbol == "PURR")).one()
    assert row.discovered
    assert not row.is_primary
    assert session.scalars(select(Bar.symbol).where(Bar.symbol == "PURR").distinct()).all() == [
        "PURR"
    ]

    extended = discover.extend(UNIVERSE, session)
    assert [a.symbol for a in extended.assets] == ["BTC/USD", "PURR"]
    assert extended.get("PURR").asset_class == "stock"
    assert discover.extend(extended, session) is extended  # nothing new to add
    # Known already: looking again finds nothing new and registers nothing.
    assert discover.discover(client, engine, extended, ["EQ_PURR"]) == []


def reading(known: list[str]) -> BinanceReading:
    held = [Holding(symbol="BTC/USD", quantity=1.0)]
    unsupported = []
    if "PURR" in known:
        held.append(Holding(symbol="PURR", quantity=20.0))
    else:
        unsupported.append(Unsupported(symbol="EQ_PURR", reason=NO_HISTORY))
    unsupported.append(Unsupported(symbol="XYZ", reason="Net short or flat after futures."))
    return BinanceReading(
        holdings=Holdings(source="binance", holdings=held, unsupported=unsupported), leveraged=[]
    )


def test_an_unknown_holding_is_found_and_the_exchange_read_again(
    client: AlpacaDataClient, api: respx.MockRouter, engine: Engine, session: Session
) -> None:
    sync_assets(session, UNIVERSE)
    session.commit()
    api.get(STOCK_BARS).respond(json=page("PURR", "2025-12-03", "2025-12-04"))
    reads: list[list[str]] = []
    asked: list[list[str]] = []

    def reader(universe: Universe) -> BinanceReading:
        reads.append([a.symbol for a in universe.assets])
        return reading(reads[-1])

    def finder(universe: Universe, names: list[str]) -> list[object]:
        asked.append(names)
        return list(discover.discover(client, engine, universe, names))

    result, universe = job.read_exchange(session, UNIVERSE, reader, finder)
    assert asked == [["EQ_PURR"]]  # only names with no price history are looked up
    assert reads == [["BTC/USD"], ["BTC/USD", "PURR"]]
    assert [h.symbol for h in result.holdings.holdings] == ["BTC/USD", "PURR"]
    assert universe.get("PURR").name == "PURR"

    # With no market data key, the reading is used as it came.
    reads.clear()
    plain, same = job.read_exchange(session, UNIVERSE, reader, None)
    assert reads == [["BTC/USD"]]
    assert same is UNIVERSE
    assert [u.symbol for u in plain.holdings.unsupported] == ["EQ_PURR", "XYZ"]
