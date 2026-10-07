"""Three ways of behaving while paying in regularly (decision 066, part B).

A person pays in the same amount every few weeks. They can invest each payment at once;
sell out when a gain has turned into a loss and buy back later; or keep payments in cash
until the price has dropped. Each function replays one of these on a price series and
returns, day by day, what the person has and what they paid.

Pure functions. Every decision on a day uses that day's close and earlier closes only,
and trades at that close.

The last part asks a narrower question (decision 070): a payment goes in this month
whatever happens, so does waiting for a reading get a lower price than the scheduled day?
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

MODEL_VERSION = "buying-1"
EVERY = 21
COST = 0.001
ARMED_AT = 0.05
BUY_BACK_WINDOW = 20
DIP = 0.10
DIP_WINDOW = 60


class Outcome(BaseModel):
    """How one way of behaving ended."""

    end: float  # value over total paid in, at the end
    worst: float  # the lowest that ratio reached, minus one
    cash_share: float  # average share of the money that sat in cash
    trades: int  # times everything was sold or a waiting pile was invested


def _frame(
    index: pd.Index, value: list[float], paid: list[float], cash: list[float]
) -> pd.DataFrame:
    return pd.DataFrame({"value": value, "paid": paid, "cash": cash}, index=index)


def on_schedule(
    close: pd.Series, every: int = EVERY, cost: float = COST, cash_share: float = 0.0
) -> pd.DataFrame:
    """Invest each payment the day it is made. With `cash_share`, that part of every
    payment is kept in cash instead, for comparing against behaviours that hold cash."""
    units = cash = paid = 0.0
    value, paid_in, in_cash = [], [], []
    for i, price in enumerate(close.to_numpy(dtype=float)):
        if i % every == 0:
            paid += 1.0
            cash += cash_share
            units += (1.0 - cash_share) * (1 - cost) / price
        value.append(units * price + cash)
        paid_in.append(paid)
        in_cash.append(cash)
    return _frame(close.index, value, paid_in, in_cash)


def cut_at_break_even(
    close: pd.Series,
    every: int = EVERY,
    cost: float = COST,
    armed_at: float = ARMED_AT,
    window: int = BUY_BACK_WINDOW,
) -> tuple[pd.DataFrame, int]:
    """Sell everything when a gain has turned into a loss; buy back on a new high.

    Once the holding has been worth `armed_at` more than was paid for it, the first close
    at which it is worth less than was paid for it sells everything. Payments wait in
    cash while out. Everything is bought back at the first close above the highest close
    of the `window` days before.
    """
    prices = close.to_numpy(dtype=float)
    units = cash = paid = basis = 0.0
    holding, armed, trades = True, False, 0
    value, paid_in, in_cash = [], [], []
    for i, price in enumerate(prices):
        if i % every == 0:
            paid += 1.0
            if holding:
                units += (1 - cost) / price
                basis += 1.0
            else:
                cash += 1.0
        if holding and units > 0:
            worth = units * price
            if worth >= basis * (1 + armed_at):
                armed = True
            if armed and worth < basis:
                cash += worth * (1 - cost)
                units, basis, holding, armed = 0.0, 0.0, False, False
                trades += 1
        elif not holding and i >= window and price > prices[i - window : i].max():
            units, basis = cash * (1 - cost) / price, cash
            cash, holding = 0.0, True
            trades += 1
        value.append(units * price + cash)
        paid_in.append(paid)
        in_cash.append(cash)
    return _frame(close.index, value, paid_in, in_cash), trades


def wait_for_dips(
    close: pd.Series,
    every: int = EVERY,
    cost: float = COST,
    dip: float = DIP,
    window: int = DIP_WINDOW,
) -> tuple[pd.DataFrame, int]:
    """Keep payments in cash and invest all of it at the first close `dip` or more below
    the highest close of the `window` days before."""
    prices = close.to_numpy(dtype=float)
    units = cash = paid = 0.0
    trades = 0
    value, paid_in, in_cash = [], [], []
    for i, price in enumerate(prices):
        if i % every == 0:
            paid += 1.0
            cash += 1.0
        if cash > 0 and i >= window and price <= (1 - dip) * prices[i - window : i].max():
            units += cash * (1 - cost) / price
            cash = 0.0
            trades += 1
        value.append(units * price + cash)
        paid_in.append(paid)
        in_cash.append(cash)
    return _frame(close.index, value, paid_in, in_cash), trades


def outcome(replay: pd.DataFrame, trades: int = 0) -> Outcome:
    ratio = replay["value"] / replay["paid"]
    return Outcome(
        end=float(ratio.iloc[-1]),
        worst=float(ratio.min() - 1),
        cash_share=float(np.mean(replay["cash"] / replay["value"])),
        trades=trades,
    )


# ---------- When in the month to pay (decision 070) -------------------------------------


def month_starts(days: int, every: int = EVERY, warm_up: int = 0) -> np.ndarray:
    """The first row of each full block of `every` days after `warm_up`."""
    starts: np.ndarray = np.arange(warm_up, days - every + 1, every)
    return starts


def day_paid(on: np.ndarray, starts: np.ndarray, every: int = EVERY) -> np.ndarray:
    """For each month, how many days after its first the payment goes in: the first day
    the reading is on, or the last day when it never is."""
    waits = np.full(len(starts), every - 1)
    for i, start in enumerate(starts):
        hit = np.flatnonzero(on[start : start + every])
        if len(hit):
            waits[i] = int(hit[0])
    return waits


def saving_table(close: np.ndarray, starts: np.ndarray, every: int = EVERY) -> np.ndarray:
    """For each month and each day of it, one minus that day's close over the first
    day's: what paying that day saved against paying on schedule. Shape (months, every)."""
    block = close[starts[:, None] + np.arange(every)[None, :]]
    table: np.ndarray = 1 - block / block[:, :1]
    return table


def savings(table: np.ndarray, waits: np.ndarray) -> np.ndarray:
    """What each month's payment saved, given the day it went in."""
    result: np.ndarray = table[np.arange(len(waits)), waits]
    return result


def shuffled_waits(
    table: np.ndarray, waits: np.ndarray, draws: int = 2000, seed: int = 7
) -> np.ndarray:
    """Total saving when the same waits are put on the wrong months, once per draw.

    A rule that waits gets a different price just by waiting. Keeping its waits and
    shuffling which month each belongs to shows what waiting alone was worth; the rule
    picked its days only if it did better than these.
    """
    rng = np.random.default_rng(seed)
    rows = np.arange(len(waits))
    totals: np.ndarray = np.array([table[rows, rng.permutation(waits)].sum() for _ in range(draws)])
    return totals
