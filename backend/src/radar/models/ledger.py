"""The account's record: what was paid, what was made, and how trading compared with
holding. Pure: no database and no network here.

Everything is built from entries, one per thing that changed how much of an asset the
account has: a purchase, a sale, coins arriving or leaving, a reward. These are facts
from the exchange's own history, so nothing here is an estimate, with two stated
exceptions: coins that arrived from outside are given the market price of that day as
their cost, because what was paid for them elsewhere is unknown; and a swap of one coin
for another is priced at that day's market price for the same reason.

Cost is kept by the average method: every unit held costs the same, the average of what
was paid for the units still held. Selling leaves the average unchanged and realises
the difference between the sale price and that average.
"""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MODEL_VERSION = "ledger-1"
# Dollar stablecoins are cash: a trade against one is a trade against dollars.
CASH = frozenset({"USD", "USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USD1", "DAI"})
DUST = 1e-9

Kind = Literal["buy", "sell", "arrived", "left", "reward"]
PriceAt = Callable[[str, datetime], float | None]


class Entry(BaseModel):
    """One change in how much of an asset is held.

    `units` is positive when the holding grew. `dollars` is what was paid (for a
    purchase) or received (for a sale), fees included, always positive; it is missing
    when the exchange's record does not say, as for coins arriving from outside.
    """

    at: datetime
    asset: str
    kind: Kind
    units: float
    dollars: float | None = None
    fee: float = 0.0


class Standing(BaseModel):
    """Where one asset stands after all its entries."""

    asset: str
    units: float
    # What the units still held cost, and the same per unit. The average cost is also
    # the break-even price: above it the holding is in gain.
    cost: float
    average_cost: float | None
    # Gain already taken by selling, after fees.
    realised: float
    bought: float
    sold: float
    fees: float
    reward_units: float
    purchases: int
    sales: int
    first: datetime | None
    # Entries whose dollar value had to be taken from a market price, or could not be.
    priced_at_market: int
    unpriced: int


class RoundTrip(BaseModel):
    """From nothing held, to something, back to nothing."""

    asset: str
    opened: datetime
    closed: datetime
    days: float
    paid: float
    received: float
    gain: float


class Compared(BaseModel):
    """Trading as it was done, beside putting the same new money in and never selling."""

    asset: str
    # Money that came from outside this asset: purchases not paid for by earlier sales.
    put_in: float
    as_traded: float
    if_held: float
    difference: float


def standing(entries: Iterable[Entry], price_at: PriceAt | None = None) -> dict[str, Standing]:
    """Each asset's units, cost, break-even and realised gain, by the average method."""
    result: dict[str, Standing] = {}
    for entry in sorted(entries, key=lambda e: e.at):
        if entry.asset in CASH:
            continue
        now = result.setdefault(
            entry.asset,
            Standing(
                asset=entry.asset,
                units=0.0,
                cost=0.0,
                average_cost=None,
                realised=0.0,
                bought=0.0,
                sold=0.0,
                fees=0.0,
                reward_units=0.0,
                purchases=0,
                sales=0,
                first=entry.at,
                priced_at_market=0,
                unpriced=0,
            ),
        )
        dollars = entry.dollars
        if dollars is None and entry.kind != "reward":
            price = price_at(entry.asset, entry.at) if price_at else None
            if price is None:
                now.unpriced += 1
            else:
                dollars = abs(entry.units) * price
                now.priced_at_market += 1
        now.fees += entry.fee
        if entry.units > 0:
            now.units += entry.units
            if entry.kind == "reward":
                now.reward_units += entry.units
            else:
                now.cost += dollars or 0.0
            if entry.kind == "buy":
                now.bought += dollars or 0.0
                now.purchases += 1
        elif entry.units < 0 and now.units > DUST:
            leaving = min(-entry.units, now.units)
            share = leaving / now.units
            released = now.cost * share
            now.units -= leaving
            now.cost -= released
            if entry.kind == "sell":
                now.sold += dollars or 0.0
                now.sales += 1
                if dollars is not None:
                    now.realised += dollars - released
        if now.units <= DUST:
            now.units, now.cost = 0.0, 0.0
        now.average_cost = now.cost / now.units if now.units > DUST else None
    return result


def round_trips(entries: Iterable[Entry], asset: str, least: float = 0.02) -> list[RoundTrip]:
    """Each stretch from holding none of an asset to holding none again, by trading.

    A stretch counts as closed when what is left is under `least` of the most held
    during it, so that crumbs left by fees do not keep it open for ever.
    """
    trips: list[RoundTrip] = []
    units = most = paid = received = 0.0
    opened: datetime | None = None
    for entry in sorted(entries, key=lambda e: e.at):
        if entry.asset != asset or entry.kind not in ("buy", "sell") or entry.dollars is None:
            continue
        if entry.kind == "buy":
            if opened is None:
                opened, units, most, paid, received = entry.at, 0.0, 0.0, 0.0, 0.0
            units += entry.units
            paid += entry.dollars
            most = max(most, units)
        elif opened is not None:
            units += entry.units
            received += entry.dollars
            if units <= least * most:
                trips.append(
                    RoundTrip(
                        asset=asset,
                        opened=opened,
                        closed=entry.at,
                        days=(entry.at - opened).total_seconds() / 86_400,
                        paid=paid,
                        received=received,
                        gain=received - paid,
                    )
                )
                opened = None
    return trips


def against_holding(entries: Iterable[Entry], asset: str, price_now: float) -> Compared | None:
    """What the trading in one asset is worth now, beside what the same new money would
    be worth had it been put in at the same times and never sold.

    Sales go into a pool; a later purchase is paid from the pool first, and only the
    rest is new money. The holder buys with each amount of new money at that purchase's
    own price and keeps everything. Both are valued at `price_now`; the trader also
    keeps whatever is left in the pool.
    """
    units = pool = put_in = held_units = 0.0
    seen = False
    for entry in sorted(entries, key=lambda e: e.at):
        if entry.asset != asset or entry.kind not in ("buy", "sell") or not entry.dollars:
            continue
        seen = True
        if entry.kind == "buy":
            from_pool = min(pool, entry.dollars)
            fresh = entry.dollars - from_pool
            pool -= from_pool
            put_in += fresh
            held_units += fresh / (entry.dollars / entry.units)
            units += entry.units
        else:
            units = max(units + entry.units, 0.0)
            pool += entry.dollars
    if not seen or put_in <= 0:
        return None
    as_traded = units * price_now + pool
    if_held = held_units * price_now
    return Compared(
        asset=asset,
        put_in=put_in,
        as_traded=as_traded,
        if_held=if_held,
        difference=as_traded - if_held,
    )


def reconcile(now: Standing, held: float) -> tuple[Standing, float]:
    """Bring a standing down to the units actually held, and say what the rest cost.

    History can leave more units than the account really has: coins moved to another
    wallet, withdrawn, or swapped in a way the trade history does not list. What is
    really held is the truth. The extra units leave at their average cost, so nothing is
    counted as gained or lost on them, and their cost is returned so that it can be
    shown as money whose fate the record does not know.
    """
    extra = now.units - max(held, 0.0)
    if extra <= DUST or now.units <= DUST:
        return now, 0.0
    cost_gone = now.cost * extra / now.units
    left = now.units - extra
    return (
        now.model_copy(
            update={
                "units": left if left > DUST else 0.0,
                "cost": now.cost - cost_gone if left > DUST else 0.0,
                "average_cost": now.average_cost if left > DUST else None,
            }
        ),
        cost_gone,
    )


def missing_share(from_history: float, held: float) -> float | None:
    """How far the units rebuilt from history are from the units actually held, as a
    share of what is held. Missing when nothing is held."""
    if abs(held) <= DUST:
        return None
    return (from_history - held) / held


# ---------- Entries from an exchange's history -----------------------------------------


def split_pair(pair: str) -> tuple[str, str] | None:
    """A pair such as `SOLUSDT` as (asset, cash), when it trades against dollars."""
    for cash in sorted(CASH, key=len, reverse=True):
        if pair.endswith(cash) and len(pair) > len(cash):
            return pair[: -len(cash)], cash
    return None


def from_fill(
    pair: str,
    at: datetime,
    bought: bool,
    quantity: float,
    amount: float,
    fee: float,
    fee_asset: str,
) -> Entry | None:
    """One purchase or sale against dollars. A fee taken in the asset reduces what was
    received; a fee taken in dollars adds to what was paid or comes off what was got.
    A fee in a third asset is left out of the cost. Pairs between two coins are skipped."""
    parts = split_pair(pair)
    if parts is None or quantity <= 0:
        return None
    asset, _ = parts
    price = amount / quantity
    units, dollars, cost_of_fee = quantity, amount, 0.0
    if fee_asset == asset:
        cost_of_fee = fee * price
        units = quantity - fee if bought else quantity
        dollars = amount if bought else amount - cost_of_fee
    elif fee_asset in CASH:
        cost_of_fee = fee
        dollars = amount + fee if bought else amount - fee
    return Entry(
        at=at,
        asset=asset,
        kind="buy" if bought else "sell",
        units=units if bought else -units,
        dollars=dollars,
        fee=cost_of_fee,
    )


def from_conversion(
    at: datetime, from_asset: str, from_quantity: float, to_asset: str, to_quantity: float
) -> list[Entry]:
    """A swap. Dollars to a coin is a purchase and a coin to dollars a sale; a swap
    between two coins is one leaving and one arriving, to be priced at the market."""
    if from_asset in CASH and to_asset in CASH:
        return []
    if from_asset in CASH:
        return [Entry(at=at, asset=to_asset, kind="buy", units=to_quantity, dollars=from_quantity)]
    if to_asset in CASH:
        return [
            Entry(at=at, asset=from_asset, kind="sell", units=-from_quantity, dollars=to_quantity)
        ]
    return [
        Entry(at=at, asset=from_asset, kind="left", units=-from_quantity),
        Entry(at=at, asset=to_asset, kind="arrived", units=to_quantity),
    ]
