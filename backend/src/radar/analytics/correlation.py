"""How two markets move together, and how every market sits beside the others (spec F5).

Pure functions on the mixed panel: one row per New York session, with a weekend's
crypto move counted in Monday's row.

No lookahead: every value stamped at a session uses returns up to that session only.
"""

import math
from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform

WINDOWS = (30, 90)
# The fast estimate forgets half of a day's weight after this many sessions.
HALF_LIFE = 30
# Fewest days in a regime before a correlation is quoted for it.
MIN_REGIME_DAYS = 30
LEVEL_Z = 1.959963984540054  # two-sided 95%


def rolling(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Correlation over the trailing `window` sessions that both have a return for."""
    both = pd.concat([a, b], axis=1).dropna()
    out = both.iloc[:, 0].rolling(window).corr(both.iloc[:, 1])
    return pd.Series(out, index=both.index)


def weighted(a: pd.Series, b: pd.Series, half_life: int = HALF_LIFE) -> pd.Series:
    """Exponentially weighted correlation: recent sessions count more, so it turns sooner."""
    both = pd.concat([a, b], axis=1).dropna()
    x, y = both.iloc[:, 0], both.iloc[:, 1]
    out = x.ewm(halflife=half_life, min_periods=half_life).corr(y)
    return pd.Series(out, index=both.index)


def interval(correlation: float, n: int) -> tuple[float, float]:
    """95% range for a correlation measured on `n` days (Fisher's transformation)."""
    if n <= 3 or abs(correlation) >= 1:
        return (-1.0, 1.0) if n <= 3 else (correlation, correlation)
    centre = math.atanh(correlation)
    half = LEVEL_Z / math.sqrt(n - 3)
    return math.tanh(centre - half), math.tanh(centre + half)


class RegimeCorrelation(BaseModel):
    label: str
    n: int
    # Null when the regime has too few days to say.
    correlation: float | None
    low: float | None
    high: float | None


def by_regime(a: pd.Series, b: pd.Series, labels: pd.Series) -> list[RegimeCorrelation]:
    """Correlation of the two on the days each regime label applied.

    `labels` holds the label known at each session's close.
    """
    frame = pd.concat([a, b, labels], axis=1, keys=["a", "b", "label"]).dropna()
    rows = []
    for label, group in frame.groupby("label", sort=False):
        n = len(group)
        if n < MIN_REGIME_DAYS:
            rows.append(
                RegimeCorrelation(label=str(label), n=n, correlation=None, low=None, high=None)
            )
            continue
        value = float(np.corrcoef(group["a"].astype(float), group["b"].astype(float))[0, 1])
        low, high = interval(value, n)
        rows.append(RegimeCorrelation(label=str(label), n=n, correlation=value, low=low, high=high))
    return rows


class Grid(BaseModel):
    """Correlation between every pair, ordered so that markets that behave alike sit together."""

    symbols: list[str]
    matrix: list[list[float]]
    n_days: int
    first_day: date
    last_day: date


def grid(returns: pd.DataFrame) -> Grid | None:
    """Correlation of every pair on the sessions all of them have, in clustered order."""
    complete = returns.dropna()
    if len(complete) < MIN_REGIME_DAYS or complete.shape[1] < 2:
        return None
    matrix = np.corrcoef(complete.to_numpy(dtype=float), rowvar=False)
    order = list(range(len(matrix)))
    if len(matrix) > 2:
        distance = np.clip(1.0 - matrix, 0.0, 2.0)
        np.fill_diagonal(distance, 0.0)
        order = [
            int(i) for i in leaves_list(linkage(squareform(distance, checks=False), "average"))
        ]
    ordered = matrix[np.ix_(order, order)]
    days = pd.DatetimeIndex(complete.index)
    return Grid(
        symbols=[str(complete.columns[i]) for i in order],
        matrix=[[float(v) for v in row] for row in ordered],
        n_days=len(complete),
        first_day=days[0].date(),
        last_day=days[-1].date(),
    )
