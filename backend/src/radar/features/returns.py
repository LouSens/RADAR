"""Returns and trailing statistics. Pure functions.

No lookahead: every trailing statistic at time `t` uses observations strictly before
`t`, so today's value is always compared with a past it could not have influenced.
"""

import numpy as np
import pandas as pd


def log_series(values: pd.Series) -> pd.Series:
    return pd.Series(np.log(values.to_numpy(dtype=float)), index=values.index, name=values.name)


def log_frame(values: pd.DataFrame) -> pd.DataFrame:
    logged = np.log(values.to_numpy(dtype=float))
    return pd.DataFrame(logged, index=values.index, columns=values.columns)


def log_returns(prices: pd.Series, step: pd.Timedelta | None = None) -> pd.Series:
    """Log return from the previous observation.

    With `step`, a return is kept only when the previous observation is exactly one
    step earlier; a return across a missing bar is left empty, not stretched.
    """
    returns = log_series(prices).diff()
    if step is not None:
        elapsed = prices.index.to_series().diff()
        returns = returns.where(elapsed == step)
    return returns


def daily_range(high: pd.Series, low: pd.Series) -> pd.Series:
    """Log of the day's high over its low."""
    return log_series(high / low)


def trailing_mean(values: pd.Series, window: int) -> pd.Series:
    """Mean of the `window` observations before each point (the point itself excluded)."""
    return values.shift(1).rolling(window, min_periods=window).mean()


def trailing_std(values: pd.Series, window: int) -> pd.Series:
    """Standard deviation of the `window` observations before each point."""
    return values.shift(1).rolling(window, min_periods=window).std()


def trailing_zscore(values: pd.Series, window: int) -> pd.Series:
    """How unusual each value is against the `window` observations before it."""
    spread = trailing_std(values, window)
    return (values - trailing_mean(values, window)) / spread.where(spread > 0)
