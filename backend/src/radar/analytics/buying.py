"""A ladder of purchases (decision 077): split a payment into parts at lower prices.

Pure functions. A month's ladder is set from the closes up to its first day only.
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

MODEL_VERSION = "buying-1"
EVERY = 21


def month_starts(days: int, every: int = EVERY, warm_up: int = 0) -> np.ndarray:
    """The first row of each full block of `every` days after `warm_up`."""
    starts: np.ndarray = np.arange(warm_up, days - every + 1, every)
    return starts


class Rung(BaseModel):
    """One part of a purchase: buy `amount` dollars at `price` or lower."""

    price: float
    amount: float
    # How far below today's price, as a fraction.
    below: float


def ladder(
    price: float, weekly_swing: float, amount: float, steps: tuple[float, ...] = (0.0, 1.0, 2.0)
) -> list[Rung]:
    """Split a purchase into equal parts: one at today's price and the others lower, each
    a number of usual weekly swings below it. `weekly_swing` is a fraction (0.03 is 3%)."""
    part = amount / len(steps)
    return [
        Rung(price=price * (1 - step * weekly_swing), amount=part, below=step * weekly_swing)
        for step in steps
    ]


def ladder_replay(
    frame: pd.DataFrame,
    starts: np.ndarray,
    every: int = EVERY,
    steps: tuple[float, ...] = (0.0, 1.0, 2.0),
    window: int = 20,
) -> pd.DataFrame:
    """What a ladder paid in each past month, against buying everything on the first day.

    The ladder is set at the first day's close from the swing of the `window` days
    before it. A lower rung is bought on the first later day whose low reaches it, at
    the rung's price. Whatever is not bought by the month's last day is bought at that
    day's close. `saving` is one minus the average price paid over the first day's
    close; `filled` is how many of the lower rungs were reached.
    """
    high = frame["high"].to_numpy(dtype=float)
    low, close = frame["low"].to_numpy(dtype=float), frame["close"].to_numpy(dtype=float)
    daily = pd.Series(close).pct_change().rolling(window).std().to_numpy()
    rows = []
    for start in starts:
        swing = daily[start] * np.sqrt(5)
        if not np.isfinite(swing) or start + every > len(close):
            continue
        first = close[start]
        units = 0.0
        filled = 0
        for step in steps:
            level = first * (1 - step * swing)
            if step == 0:
                units += 1 / first
                continue
            reached = np.flatnonzero(low[start + 1 : start + every] <= level)
            if len(reached):
                day = start + 1 + int(reached[0])
                units += 1 / min(level, high[day])
                filled += 1
            else:
                units += 1 / close[start + every - 1]
        paid = len(steps) / units
        rows.append({"start": frame.index[start], "saving": 1 - paid / first, "filled": filled})
    return pd.DataFrame(rows, columns=["start", "saving", "filled"])
