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
