"""What to do now: where spare cash goes, at what prices, and why (decision 077).

Read from the stored portfolio and the plan the user chose. When there is more cash than
the plan allows, the cash over is shared among the holdings that are short of their
share, and each purchase is split into a ladder: a part at today's price and parts
lower, a usual weekly swing apart. A holding well above its share is listed to trim.

Nothing here forecasts. The ladder's steps come from how much the price usually moves,
and each step carries what the same ladder paid in past months, so the cost of waiting
for a lower price is shown beside it. Everything is arithmetic against the user's own
plan, and the user places every trade.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel

from radar.analytics import buying
from radar.models.holdings import CASH
from radar.pipelines import portfolio as portfolio_job

VERSION = "steps-1"
# Cash over the plan is acted on from this share of the account, or this many dollars.
SPARE_SHARE = 0.02
SPARE_DOLLARS = 5.0
# The smallest purchase worth listing, and so the smallest part of a ladder.
SMALLEST = 5.0
# A holding short of its plan by less than the smallest order, but by at least this
# share of the order, is still bought, as one smallest order. Dropping it would leave a
# target the user set with nothing to do about it.
NOTICED = 0.5
# A holding is listed to trim when it is this far above its share of the account.
TRIM_ABOVE = 0.05
QUARTER = 63
MONTH = 21
SWING_DAYS = 20
DEADLINE = timedelta(days=30)


class Past(BaseModel):
    """What this ladder paid in past months, against buying everything on the first day."""

    months: int
    # Negative when the ladder paid more on average.
    average_saving: float
    cheaper_share: float
    worst: float


class Step(BaseModel):
    symbol: str
    name: str
    kind: str  # "buy" or "trim"
    amount: float
    share_now: float
    share_plan: float
    price: float
    # When that was the price: the latest trade or stored hour, not the last daily close.
    priced_at: AwareDatetime | None = None
    # Where the price sits between the lowest and highest close of the last three
    # months, 0 to 1, and how far it is below that high.
    place: float | None = None
    below_high: float | None = None
    weekly_swing: float | None = None
    rungs: list[buying.Rung] = []
    past: Past | None = None


class Steps(BaseModel):
    as_of: AwareDatetime
    model_version: str
    has_plan: bool
    value: float
    cash: float
    cash_plan: float
    # Cash above what the plan keeps. Negative when there is less than planned.
    spare: float
    steps: list[Step]
    # Parts not bought by this date are bought then, so cash does not wait for ever.
    by: AwareDatetime
    # When the holdings behind this were last read from where they are kept.
    checked_at: AwareDatetime | None = None


def _past(close: pd.Series, parts: int) -> Past | None:
    """The ladder replayed on closes. A lower part counts as bought on the first later
    day that closed at or under it."""
    frame = pd.DataFrame({"high": close, "low": close, "close": close})
    starts = buying.month_starts(len(frame), warm_up=SWING_DAYS + 1)
    replay = buying.ladder_replay(frame, starts, steps=tuple(float(i) for i in range(parts)))
    if len(replay) < 12:
        return None
    return Past(
        months=len(replay),
        average_saving=float(replay["saving"].mean()),
        cheaper_share=float((replay["saving"] > 0).mean()),
        worst=float(replay["saving"].min()),
    )


def _reading(close: pd.Series, price: float) -> tuple[float | None, float | None, float | None]:
    """Place of `price` in the last three months of closes, its distance below their
    high, and the weekly swing."""
    if len(close) < QUARTER:
        return None, None, None
    recent = close.iloc[-QUARTER:]
    last = price
    top, bottom = max(float(recent.max()), price), min(float(recent.min()), price)
    swing = float(close.pct_change().rolling(SWING_DAYS).std().iloc[-1] * np.sqrt(5))
    place = (last - bottom) / (top - bottom) if top > bottom else 0.5
    return place, last / top - 1, swing if np.isfinite(swing) else None


def build(
    analysis: portfolio_job.Analysis,
    weights: dict[str, float] | None,
    closes: dict[str, pd.Series],
    now: datetime,
    latest: dict[str, tuple[float, datetime]] | None = None,
) -> Steps:
    """The steps for an analysed portfolio and the plan's shares (cash is the rest).

    `latest` is each asset's newest price and when it was the price. Where it is given
    the prices to buy at are worked out from it; the daily closes only say how much the
    price usually moves and where it has been.
    """
    latest = latest or {}
    value = analysis.value
    held = {p.symbol: p for p in analysis.positions}
    cash = held[CASH].value if CASH in held else 0.0
    if not weights or value <= 0:
        return Steps(
            as_of=now,
            model_version=VERSION,
            has_plan=False,
            value=value,
            cash=cash,
            cash_plan=cash,
            spare=0.0,
            steps=[],
            by=now + DEADLINE,
        )
    cash_plan = max(1.0 - sum(weights.values()), 0.0) * value
    spare = cash - cash_plan
    short = {
        symbol: share * value - (held[symbol].value if symbol in held else 0.0)
        for symbol, share in weights.items()
    }
    short = {symbol: gap for symbol, gap in short.items() if gap >= NOTICED * SMALLEST}
    steps: list[Step] = []
    if short and spare >= max(SPARE_DOLLARS, SPARE_SHARE * value):
        scale = min(1.0, spare / sum(short.values()))
        amounts = {symbol: gap * scale for symbol, gap in short.items()}
        # A part too small to place as an order is raised to the smallest order, and
        # the largest part gives up the difference, so the total is never more than
        # the cash that is over.
        for symbol in amounts:
            if NOTICED * SMALLEST <= amounts[symbol] < SMALLEST:
                largest = max(amounts, key=lambda name: amounts[name])
                raised = SMALLEST - amounts[symbol]
                if largest != symbol and amounts[largest] - raised >= SMALLEST:
                    amounts[largest] -= raised
                    amounts[symbol] = SMALLEST
        for symbol, amount in sorted(amounts.items(), key=lambda item: -item[1]):
            close = closes.get(symbol)
            if amount < SMALLEST or close is None or close.empty:
                continue
            price, priced_at = latest.get(symbol, (float(close.iloc[-1]), None))
            place, below_high, swing = _reading(close, price)
            parts = int(min(3, amount // SMALLEST)) if swing else 1
            steps.append(
                Step(
                    symbol=symbol,
                    name=held[symbol].name if symbol in held else symbol,
                    kind="buy",
                    amount=amount,
                    share_now=(held[symbol].value if symbol in held else 0.0) / value,
                    share_plan=weights[symbol],
                    price=price,
                    priced_at=priced_at,
                    place=place,
                    below_high=below_high,
                    weekly_swing=swing,
                    rungs=buying.ladder(
                        price, swing or 0.0, amount, tuple(float(i) for i in range(parts))
                    ),
                    past=_past(close, parts) if parts > 1 else None,
                )
            )
    for symbol, position in held.items():
        if symbol == CASH:
            continue
        share_plan = weights.get(symbol, 0.0)
        over = position.weight - share_plan
        if over >= TRIM_ABOVE and over * value >= SMALLEST:
            steps.append(
                Step(
                    symbol=symbol,
                    name=position.name,
                    kind="trim",
                    amount=over * value,
                    share_now=position.weight,
                    share_plan=share_plan,
                    price=latest.get(symbol, (position.price, None))[0],
                    priced_at=latest.get(symbol, (position.price, None))[1],
                )
            )
    return Steps(
        as_of=now,
        model_version=VERSION,
        has_plan=True,
        value=value,
        cash=cash,
        cash_plan=cash_plan,
        spare=spare,
        steps=steps,
        by=now + DEADLINE,
    )
