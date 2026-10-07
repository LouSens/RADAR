"""The account's record, on a few trades whose answers can be worked out by hand."""

from datetime import UTC, datetime, timedelta

import pytest

from radar.models import ledger
from radar.models.ledger import Entry

T0 = datetime(2025, 1, 1, tzinfo=UTC)


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def buy(n: int, units: float, dollars: float, asset: str = "SOL", fee: float = 0.0) -> Entry:
    return Entry(at=day(n), asset=asset, kind="buy", units=units, dollars=dollars, fee=fee)


def sell(n: int, units: float, dollars: float, asset: str = "SOL") -> Entry:
    return Entry(at=day(n), asset=asset, kind="sell", units=-units, dollars=dollars)


def test_the_average_cost_is_what_was_paid_for_the_units_still_held() -> None:
    now = ledger.standing([buy(0, 2, 200), buy(1, 2, 400)])["SOL"]
    assert (now.units, now.cost) == (4, 600)
    assert now.average_cost == 150  # the break-even price
    assert (now.bought, now.purchases, now.realised) == (600, 2, 0)
    assert now.first == day(0)


def test_selling_realises_the_gain_over_the_average_and_leaves_the_average_alone() -> None:
    now = ledger.standing([buy(0, 2, 200), buy(1, 2, 400), sell(2, 1, 180)])["SOL"]
    # One unit sold for 180 that cost 150 on average.
    assert now.realised == pytest.approx(30)
    assert now.units == 3
    assert now.cost == pytest.approx(450)
    assert now.average_cost == pytest.approx(150)
    assert (now.sold, now.sales) == (180, 1)


def test_selling_everything_empties_the_holding_and_a_new_purchase_starts_afresh() -> None:
    now = ledger.standing([buy(0, 2, 200), sell(1, 2, 150), buy(2, 1, 90)])["SOL"]
    assert now.realised == pytest.approx(-50)
    assert (now.units, now.cost, now.average_cost) == (1, 90, 90)


def test_entries_are_taken_in_time_order_whatever_order_they_come_in() -> None:
    in_order = [buy(0, 2, 200), sell(1, 1, 150)]
    assert ledger.standing(reversed(in_order)) == ledger.standing(in_order)


def test_rewards_add_units_at_no_cost_and_are_counted_apart() -> None:
    reward = Entry(at=day(1), asset="SOL", kind="reward", units=0.5)
    now = ledger.standing([buy(0, 2, 200), reward])["SOL"]
    assert (now.units, now.cost, now.reward_units) == (2.5, 200, 0.5)
    assert now.average_cost == 80
    assert now.unpriced == 0


def test_coins_from_outside_take_that_days_market_price_and_say_so() -> None:
    arrived = Entry(at=day(1), asset="SOL", kind="arrived", units=1.0)
    priced = ledger.standing([arrived], price_at=lambda asset, at: 120.0)["SOL"]
    assert (priced.cost, priced.priced_at_market, priced.unpriced) == (120, 1, 0)
    assert priced.purchases == 0  # an arrival is not a purchase

    unknown = ledger.standing([arrived])["SOL"]
    assert (unknown.cost, unknown.priced_at_market, unknown.unpriced) == (0, 0, 1)


def test_coins_sent_out_take_their_cost_with_them_and_realise_nothing() -> None:
    left = Entry(at=day(1), asset="SOL", kind="left", units=-1.0)
    now = ledger.standing([buy(0, 2, 200), left])["SOL"]
    assert (now.units, now.cost, now.realised) == (1, 100, 0)


def test_cash_is_not_a_holding_and_fees_are_added_up() -> None:
    entries = [buy(0, 2, 200, fee=0.2), buy(0, 100, 100, asset="USDT"), buy(1, 1, 90, fee=0.1)]
    result = ledger.standing(entries)
    assert list(result) == ["SOL"]
    assert result["SOL"].fees == pytest.approx(0.3)


def test_a_round_trip_runs_from_nothing_held_to_nothing_held() -> None:
    entries = [
        buy(0, 2, 200),
        buy(1, 2, 300),
        sell(3, 3.99, 480),  # all but a crumb
        buy(10, 1, 100),
        sell(12, 0.5, 60),  # half only: still open
    ]
    trips = ledger.round_trips(entries, "SOL")
    assert len(trips) == 1
    trip = trips[0]
    assert (trip.opened, trip.closed, trip.days) == (day(0), day(3), 3)
    assert (trip.paid, trip.received, trip.gain) == (500, 480, -20)


def test_trading_is_set_beside_putting_the_same_new_money_in_and_holding() -> None:
    # Buy 2 at 100, sell both at 120, buy 2 back at 110. Price now 150.
    entries = [buy(0, 2, 200), sell(1, 2, 240), buy(2, 2, 220)]
    found = ledger.against_holding(entries, "SOL", price_now=150)
    assert found is not None
    # Only the first 200 was new money; the second purchase was paid from the sale.
    assert found.put_in == 200
    # As traded: 2 units and the 20 left over from the sale.
    assert found.as_traded == pytest.approx(2 * 150 + 20)
    # Held: the 2 units bought with the 200, never sold.
    assert found.if_held == pytest.approx(300)
    assert found.difference == pytest.approx(20)


def test_selling_low_and_buying_back_higher_shows_as_behind_holding() -> None:
    entries = [buy(0, 2, 200), sell(1, 2, 160), buy(2, 2, 240)]
    found = ledger.against_holding(entries, "SOL", price_now=150)
    assert found is not None
    # 160 from the sale and 80 of new money bought the second lot.
    assert found.put_in == pytest.approx(280)
    assert found.as_traded == pytest.approx(300)
    assert found.if_held == pytest.approx((2 + 80 / 120) * 150)
    assert found.difference < 0


def test_nothing_is_compared_when_nothing_was_bought() -> None:
    assert ledger.against_holding([], "SOL", 100) is None
    assert ledger.against_holding([sell(0, 1, 100)], "SOL", 100) is None


def test_the_gap_between_history_and_what_is_held_is_a_share_of_what_is_held() -> None:
    assert ledger.missing_share(1.05, 1.0) == pytest.approx(0.05)
    assert ledger.missing_share(0.9, 1.0) == pytest.approx(-0.1)
    assert ledger.missing_share(0.5, 0.0) is None


def test_a_pair_is_split_only_when_it_trades_against_dollars() -> None:
    assert ledger.split_pair("SOLUSDT") == ("SOL", "USDT")
    assert ledger.split_pair("PAXGFDUSD") == ("PAXG", "FDUSD")
    assert ledger.split_pair("ETHBTC") is None
    assert ledger.split_pair("USDT") is None


def test_a_fee_in_the_asset_reduces_what_was_received_and_one_in_dollars_adds_to_cost() -> None:
    in_asset = ledger.from_fill("SOLUSDT", T0, True, 2.0, 300.0, 0.002, "SOL")
    assert in_asset is not None
    assert in_asset.units == pytest.approx(1.998)
    assert in_asset.dollars == 300.0
    assert in_asset.fee == pytest.approx(0.3)

    in_dollars = ledger.from_fill("SOLUSDT", T0, False, 0.5, 90.0, 0.09, "USDT")
    assert in_dollars is not None
    assert (in_dollars.kind, in_dollars.units) == ("sell", -0.5)
    assert in_dollars.dollars == pytest.approx(89.91)

    elsewhere = ledger.from_fill("SOLUSDT", T0, True, 1.0, 150.0, 0.0001, "BNB")
    assert elsewhere is not None
    assert (elsewhere.units, elsewhere.dollars, elsewhere.fee) == (1.0, 150.0, 0.0)
    assert ledger.from_fill("ETHBTC", T0, True, 1.0, 0.05, 0.0, "BNB") is None


def test_a_swap_is_a_purchase_a_sale_or_one_coin_for_another() -> None:
    bought = ledger.from_conversion(T0, "USDT", 200.0, "BTC", 0.002)
    assert [(e.kind, e.asset, e.units, e.dollars) for e in bought] == [("buy", "BTC", 0.002, 200.0)]
    sold = ledger.from_conversion(T0, "BTC", 0.002, "USDC", 210.0)
    assert [(e.kind, e.asset, e.units, e.dollars) for e in sold] == [("sell", "BTC", -0.002, 210.0)]
    swapped = ledger.from_conversion(T0, "ETH", 1.0, "SOL", 20.0)
    assert [(e.kind, e.asset, e.units, e.dollars) for e in swapped] == [
        ("left", "ETH", -1.0, None),
        ("arrived", "SOL", 20.0, None),
    ]
    assert ledger.from_conversion(T0, "USDT", 5.0, "USDC", 5.0) == []
