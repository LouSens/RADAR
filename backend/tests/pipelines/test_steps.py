"""What to do now, on an invented account whose answers can be worked out by hand."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from radar.pipelines import steps

NOW = datetime(2026, 10, 7, tzinfo=UTC)


def position(symbol: str, value: float, total: float, price: float = 100.0) -> Any:
    return SimpleNamespace(
        symbol=symbol, name=symbol, value=value, weight=value / total, price=price
    )


def account(**values: float) -> Any:
    total = sum(values.values())
    names = {"cash": "USD", "stocks": "SPY", "gold": "PAXG/USD", "coin": "BTC/USD"}
    return SimpleNamespace(
        value=total, positions=[position(names[k], v, total) for k, v in values.items()]
    )


def closes(days: int = 400, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, days))), index=index)


PLAN = {"SPY": 0.25, "PAXG/USD": 0.20, "BTC/USD": 0.07}
PRICES = {symbol: closes(seed=i) for i, symbol in enumerate(PLAN)}


def test_without_a_plan_there_is_nothing_to_do() -> None:
    found = steps.build(account(cash=300, stocks=100), None, PRICES, NOW)
    assert (found.has_plan, found.steps, found.spare) == (False, [], 0.0)


def test_cash_over_the_plan_goes_to_what_is_short_in_a_ladder() -> None:
    # 400 in all. The plan keeps 48% in cash (192), so 108 is over.
    found = steps.build(account(cash=300, stocks=50, gold=20, coin=30), PLAN, PRICES, NOW)
    assert found.has_plan
    assert found.cash_plan == pytest.approx(192)
    assert found.spare == pytest.approx(108)
    by_symbol = {s.symbol: s for s in found.steps}
    # Stocks should be 100 and are 50; gold should be 80 and is 20; the coin is at 28.
    assert set(by_symbol) == {"SPY", "PAXG/USD"}
    assert by_symbol["SPY"].amount == pytest.approx(50 * 108 / 110)
    assert by_symbol["PAXG/USD"].amount == pytest.approx(60 * 108 / 110)
    assert sum(s.amount for s in found.steps) == pytest.approx(108)  # never more than is over
    gold = by_symbol["PAXG/USD"]
    assert gold.kind == "buy"
    assert gold.share_now == pytest.approx(0.05)
    assert gold.share_plan == 0.20
    assert len(gold.rungs) == 3
    assert gold.rungs[0].price == pytest.approx(gold.price)
    assert gold.rungs[0].price > gold.rungs[1].price > gold.rungs[2].price
    assert sum(r.amount for r in gold.rungs) == pytest.approx(gold.amount)
    assert gold.weekly_swing is not None
    assert gold.rungs[1].below == pytest.approx(gold.weekly_swing)
    assert gold.place is not None
    assert 0 <= gold.place <= 1
    assert gold.past is not None
    assert gold.past.months >= 12
    assert found.by > found.as_of


def test_small_amounts_get_fewer_parts_and_nothing_under_the_smallest_purchase() -> None:
    # 12 is over: enough for two parts of 5 or more, not three.
    found = steps.build(account(cash=204, stocks=88, gold=80, coin=28), PLAN, PRICES, NOW)
    assert [(s.symbol, len(s.rungs)) for s in found.steps] == [("SPY", 2)]
    assert found.steps[0].amount == pytest.approx(12)
    # A little cash over, under the threshold: nothing is listed.
    calm = steps.build(account(cash=196, stocks=96, gold=80, coin=28), PLAN, PRICES, NOW)
    assert calm.steps == []
    assert calm.spare == pytest.approx(4)


def test_with_less_cash_than_planned_nothing_is_bought() -> None:
    found = steps.build(account(cash=100, stocks=100, gold=100, coin=100), PLAN, PRICES, NOW)
    assert found.spare < 0
    assert [s.kind for s in found.steps] == ["trim"]


def test_a_holding_well_above_its_share_is_listed_to_trim_back_to_it() -> None:
    # The coin is 25% of 400 against a plan of 7%: 72 over.
    found = steps.build(account(cash=192, stocks=100, gold=8, coin=100), PLAN, PRICES, NOW)
    trims = [s for s in found.steps if s.kind == "trim"]
    assert [s.symbol for s in trims] == ["BTC/USD"]
    assert trims[0].amount == pytest.approx(72)
    assert trims[0].rungs == []


def test_a_market_with_no_prices_is_left_out_and_short_history_gets_one_part() -> None:
    short = {"SPY": closes(days=30), "BTC/USD": PRICES["BTC/USD"]}
    found = steps.build(account(cash=300, stocks=50, gold=20, coin=30), PLAN, short, NOW)
    assert [s.symbol for s in found.steps] == ["SPY"]
    assert len(found.steps[0].rungs) == 1
    assert found.steps[0].past is None
    assert found.steps[0].place is None


def test_prices_to_buy_at_come_from_the_newest_price_not_the_last_close() -> None:
    held = account(cash=300, stocks=50, gold=20, coin=30)
    at = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)
    last_close = float(PRICES["PAXG/USD"].iloc[-1])
    now_price = last_close * 0.9  # the price has fallen a tenth since the close
    found = steps.build(held, PLAN, PRICES, NOW, {"PAXG/USD": (now_price, at)})
    by_symbol = {s.symbol: s for s in found.steps}
    gold, stocks = by_symbol["PAXG/USD"], by_symbol["SPY"]
    assert gold.price == pytest.approx(now_price)
    assert gold.priced_at == at
    assert gold.rungs[0].price == pytest.approx(now_price)
    assert all(rung.price <= now_price for rung in gold.rungs)
    # Where it sits is read at the newest price too: lower than at the close.
    before = {s.symbol: s for s in steps.build(held, PLAN, PRICES, NOW).steps}["PAXG/USD"]
    assert gold.place is not None
    assert before.place is not None
    assert gold.place <= before.place
    # An asset with no newer price keeps its last close and says no time.
    assert stocks.price == pytest.approx(float(PRICES["SPY"].iloc[-1]))
    assert stocks.priced_at is None


def test_the_later_of_two_prices_is_the_one_used() -> None:
    from radar.pipelines import prices

    early = datetime(2026, 10, 7, 9, tzinfo=UTC)
    late = datetime(2026, 10, 7, 10, tzinfo=UTC)
    merged = prices.newest(
        {"A": (1.0, early), "B": (5.0, late)}, {"A": (2.0, late), "B": (4.0, early)}
    )
    assert merged == {"A": (2.0, late), "B": (5.0, late)}


def test_a_gap_just_under_the_smallest_order_is_still_bought() -> None:
    # 400 in all, plenty of cash over. The coin should be 28 and is 23.2: 4.8 short,
    # under the smallest order of 5. It is bought as one order of 5, and the largest
    # purchase gives up the 0.2, so no more is spent than is short.
    held = account(cash=306.8, stocks=50, gold=20, coin=23.2)
    found = steps.build(held, PLAN, PRICES, NOW)
    by_symbol = {s.symbol: s for s in found.steps}
    assert by_symbol["BTC/USD"].amount == pytest.approx(steps.SMALLEST)
    assert len(by_symbol["BTC/USD"].rungs) == 1
    assert sum(s.amount for s in found.steps) == pytest.approx(50 + 60 + 4.8)
    assert sum(s.amount for s in found.steps) <= found.spare


def test_a_gap_of_pennies_is_left_alone() -> None:
    held = account(cash=302, stocks=50, gold=20, coin=27)
    assert "BTC/USD" not in {s.symbol for s in steps.build(held, PLAN, PRICES, NOW).steps}
