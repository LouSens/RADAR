"""Reading a trading habit from trades placed on a price series made by hand."""

from datetime import UTC, datetime, timedelta
from typing import Literal

import numpy as np
import pandas as pd
import pytest

from radar.analytics import trading
from radar.models.ledger import Entry

START = datetime(2025, 1, 1, tzinfo=UTC)


def bars(close: np.ndarray) -> pd.DataFrame:
    index = pd.date_range(START, periods=len(close), freq="h", tz="UTC")
    return pd.DataFrame({"high": close * 1.001, "low": close * 0.999, "close": close}, index=index)


def trade(hour: int, kind: Literal["buy", "sell"], price: float, dollars: float = 100.0) -> Entry:
    units = dollars / price
    return Entry(
        at=START + timedelta(hours=hour, minutes=30),
        asset="SOL",
        kind=kind,
        units=units if kind == "buy" else -units,
        dollars=dollars,
    )


def test_a_trade_is_set_beside_the_day_and_week_before_and_after_it() -> None:
    close = np.linspace(100, 200, 600)  # rises steadily
    prices = bars(close)
    found = trading.context([trade(300, "buy", close[300])], prices, "SOL")
    row = found.iloc[0]
    assert row["before_day"] == pytest.approx(close[300] / close[276] - 1)
    assert row["before_week"] == pytest.approx(close[300] / close[132] - 1)
    assert row["after_day"] == pytest.approx(close[324] / close[300] - 1)
    assert row["after_week"] == pytest.approx(close[468] / close[300] - 1)
    # In a steady rise the latest price is the top of the week before it.
    assert row["place"] == pytest.approx(1.0)


def test_what_came_before_a_trade_does_not_change_when_later_prices_change() -> None:
    close = 100 + np.sin(np.arange(600) / 20) * 10
    changed = close.copy()
    changed[301:] *= 3
    entry = [trade(300, "buy", close[300])]
    first = trading.context(entry, bars(close), "SOL").iloc[0]
    second = trading.context(entry, bars(changed), "SOL").iloc[0]
    for column in ("before_day", "before_week", "place"):
        assert first[column] == second[column]
    assert first["after_day"] != second["after_day"]


def test_what_came_after_is_missing_for_a_trade_too_recent_to_have_it() -> None:
    close = np.linspace(100, 200, 400)
    found = trading.context([trade(390, "buy", close[390])], bars(close), "SOL")
    assert np.isnan(found.iloc[0]["after_day"])
    assert np.isnan(found.iloc[0]["after_week"])
    assert trading.habit(found, "buy").after_week is None  # type: ignore[union-attr]


def test_trades_without_a_week_of_prices_before_them_and_other_assets_are_left_out() -> None:
    close = np.linspace(100, 200, 400)
    other = Entry(at=START + timedelta(hours=300), asset="ETH", kind="buy", units=1, dollars=1)
    found = trading.context([trade(50, "buy", 105.0), other], bars(close), "SOL")
    assert found.empty
    assert trading.habit(found, "buy") is None


def test_a_habit_weights_each_trade_by_the_money_in_it() -> None:
    table = pd.DataFrame(
        {
            "at": [START, START],
            "kind": ["buy", "buy"],
            "dollars": [300.0, 100.0],
            "price": [1.0, 1.0],
            "before_day": [0.04, 0.0],
            "before_week": [0.0, 0.0],
            "place": [1.0, 0.0],
            "after_day": [np.nan, 0.02],
            "after_week": [np.nan, np.nan],
        }
    )
    found = trading.habit(table, "buy")
    assert found is not None
    assert (found.trades, found.dollars) == (2, 400.0)
    assert found.before_day == pytest.approx(0.03)
    assert found.place == pytest.approx(0.75)
    assert found.after_day == pytest.approx(0.02)  # only the trade that has one
    assert found.after_week is None


def test_buying_tops_and_selling_bottoms_is_told_apart_from_trading_at_random() -> None:
    hours = np.arange(3000)
    close = 100 + 10 * np.sin(hours / 30)
    prices = bars(close)
    peaks = [h for h in range(200, 2900) if close[h] > close[h - 1] and close[h] > close[h + 1]]
    troughs = [h for h in range(200, 2900) if close[h] < close[h - 1] and close[h] < close[h + 1]]
    chasing = [trade(h, "buy", close[h]) for h in peaks] + [
        trade(h, "sell", close[h]) for h in troughs
    ]
    found = trading.context(chasing, prices, "SOL")
    buys, sells = trading.habit(found, "buy"), trading.habit(found, "sell")
    typical = trading.usual(prices, pd.Timestamp(START))
    assert buys is not None
    assert sells is not None
    assert typical is not None
    assert buys.place > 0.95
    assert sells.place < 0.05
    assert 0.3 < typical.place < 0.7
    assert trading.place_is_unusual(found, "buy", prices)
    assert trading.place_is_unusual(found, "sell", prices)

    rng = np.random.default_rng(1)
    random_hours = rng.choice(np.arange(200, 2900), size=60, replace=False)
    at_random = trading.context(
        [trade(int(h), "buy", close[h]) for h in random_hours], prices, "SOL"
    )
    assert not trading.place_is_unusual(at_random, "buy", prices)
    assert not trading.place_is_unusual(found.head(5), "buy", prices)  # too few to judge
