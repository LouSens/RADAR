"""Outlier flagging. A flagged bar is kept and marked for review, never deleted."""

import numpy as np
import pandas as pd

DEFAULT_THRESHOLD = 10.0
# Scales the median absolute deviation to a standard deviation for normal data.
MAD_TO_SIGMA = 1.4826


def flag_outliers(
    close: pd.Series, threshold: float = DEFAULT_THRESHOLD, step: pd.Timedelta | None = None
) -> pd.Series:
    """Flag bars whose log return sits more than `threshold` robust deviations from the median.

    `close` is one series of closing prices in time order. The median and the deviation
    are taken over the whole series, so this is a data-quality screen and must not be
    used as a model feature.
    With `step`, only returns between bars exactly one step apart are considered.
    """
    returns = np.log(close).diff()
    if step is not None:
        # A return across a break (overnight, a weekend, a missing bar) is not comparable
        # with one-step returns, so it is neither measured nor flagged.
        elapsed = close.index.to_series().diff()
        returns = returns.where(elapsed == step)
    median = returns.median()
    mad = (returns - median).abs().median()
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(False, index=close.index)
    score = (returns - median).abs() / (MAD_TO_SIGMA * mad)
    flags: pd.Series = (score > threshold).fillna(False)
    return flags


# A wick is suspect when it is this many robust deviations beyond typical and also at
# least this large in absolute terms.
WICK_THRESHOLD = 30.0
WICK_MINIMUM = 0.10


def flag_wicks(
    bars: pd.DataFrame, threshold: float = WICK_THRESHOLD, minimum: float = WICK_MINIMUM
) -> pd.Series:
    """Flag bars whose high or low sits implausibly far from their open and close.

    A single bad print can put a bar's low at a tenth of its price while open and close
    look normal. `bars` has columns `open`, `high`, `low`, `close`. The wick is the
    larger log distance from the body to the high or the low.
    """
    top = bars[["open", "close"]].max(axis=1)
    bottom = bars[["open", "close"]].min(axis=1)
    upper = np.log(bars["high"].to_numpy(dtype=float) / top.to_numpy(dtype=float))
    lower = np.log(bottom.to_numpy(dtype=float) / bars["low"].to_numpy(dtype=float))
    wick = pd.Series(np.maximum(upper, lower), index=bars.index)
    median = wick.median()
    mad = (wick - median).abs().median()
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(False, index=bars.index)
    score = (wick - median) / (MAD_TO_SIGMA * mad)
    flags: pd.Series = (score > threshold) & (wick > minimum)
    return flags
