"""Technical indicators, price levels, sizing rules and direction models, as tested in
decision 060.

Three kinds of thing, all on daily bars:

- rules that set how much to hold (a weight between nothing and everything);
- patterns and levels, each returning the days a case occurred;
- a walk-forward loop for models that forecast whether the next week ends higher.

Pure functions. No lookahead: a weight for day `t` uses day `t` and earlier days only,
and `backtest` holds it over day `t + 1`. A case is dated on the day it could first be
seen. A model that forecasts from day `t` is fitted only on days whose outcome was
already known by then.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd

MODEL_VERSION = "technical-1"
COST = 0.001
WARM_UP = 252
RSI_LOW, RSI_HIGH = 30.0, 70.0
MIN_TRAIN = 750
REFIT_EVERY = 63
FEATURES = (
    "ret_1",
    "ret_5",
    "ret_20",
    "ret_60",
    "ret_252",
    "rsi",
    "from_sma_50",
    "from_sma_200",
    "swing_20",
    "swing_20_over_60",
    "volume_ratio",
    "from_high_252",
    "from_low_252",
    "days_to_event",
)


# ---------- Indicators -----------------------------------------------------------------


def sma(close: pd.Series, window: int) -> pd.Series:
    """The average close of the last `window` days, the day itself included."""
    return close.rolling(window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's relative strength index: 100 when every recent day rose, 0 when every one
    fell."""
    change = close.diff()
    gain = change.clip(lower=0.0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-change.clip(upper=0.0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return (100 - 100 / (1 + gain / loss)).where(loss > 0, 100.0).where(gain.notna())


def swing(returns: pd.Series, window: int = 20) -> pd.Series:
    """The spread of the last `window` daily returns."""
    return returns.rolling(window).std()


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k: int = 5, slowing: int = 3, d: int = 3
) -> tuple[pd.Series, pd.Series]:
    """The stochastic oscillator: where the close sits in the last `k` days' range (0 at
    the low, 100 at the high), averaged over `slowing` days, and that line's own
    `d`-day average. Returns the fast line and the slow line."""
    lowest, highest = low.rolling(k).min(), high.rolling(k).max()
    span = (highest - lowest).where(highest > lowest)
    fast = (100 * (close - lowest) / span).rolling(slowing).mean()
    return fast, fast.rolling(d).mean()


# ---------- Rules that set how much to hold --------------------------------------------


def hold_by_swings(returns: pd.Series, window: int = 20) -> pd.Series:
    """Hold less when swings are larger than usual: min(1, usual / current), where usual
    is the median of the current reading over every day so far."""
    current = swing(returns, window)
    usual = current.expanding().median()
    return (usual / current).clip(upper=1.0)


def hold_above_average(close: pd.Series, window: int = 200) -> pd.Series:
    """Everything while the close is above its average, nothing while below."""
    average = sma(close, window)
    return (close > average).astype(float).where(average.notna())


def hold_on_cross(close: pd.Series, fast: int = 50, slow: int = 200) -> pd.Series:
    """Everything while the fast average is above the slow one."""
    slow_average = sma(close, slow)
    return (sma(close, fast) > slow_average).astype(float).where(slow_average.notna())


def hold_on_direction(close: pd.Series, window: int = 252) -> pd.Series:
    """Everything while the close is above the close `window` days earlier."""
    earlier = close.shift(window)
    return (close > earlier).astype(float).where(earlier.notna())


def event_days(index: pd.DatetimeIndex, dates: list[date]) -> np.ndarray:
    """Row of each event's day in `index`; a date that is not a day in it is left out."""
    lookup = {stamp.date(): i for i, stamp in enumerate(index)}
    found: np.ndarray = np.array(sorted({lookup[d] for d in dates if d in lookup}), dtype=int)
    return found


def hold_through_events(index: pd.DatetimeIndex, dates: list[date]) -> pd.Series:
    """Half on the day before and the day of a scheduled event, everything otherwise.

    The schedule is published in advance, so knowing tomorrow is an event day is not
    lookahead. The weight at day `t` is the one to hold over day `t + 1`.
    """
    held = np.ones(len(index))
    rows = event_days(index, dates)
    held[rows] = 0.5
    held[rows[rows > 0] - 1] = 0.5
    return pd.Series(held, index=index).shift(-1).fillna(1.0)


def hold_with_reentry(core: pd.Series, triggers: list[pd.Timestamp], days: int = 5) -> pd.Series:
    """The core share, except that a trigger on a day when the core share is below
    everything means holding everything for that day and the `days - 1` after it.

    The trigger is known at its day's close, like the core share, so the result is also
    a share decided at the close and held over the next day.
    """
    fired = pd.Series(0.0, index=core.index)
    fired.loc[[d for d in triggers if d in core.index]] = 1.0
    fired = fired.where(core < 1.0, 0.0)
    active = fired.rolling(days, min_periods=1).max() > 0
    return core.where(~active, 1.0).where(core.notna())


def backtest(returns: pd.Series, weight: pd.Series, cost: float = COST) -> pd.Series:
    """Daily return, after costs, of holding yesterday's weight through today.

    `returns` are simple daily returns. Changing the weight costs `cost` times the amount
    traded. The first day is left out: there is no weight from the day before it.
    """
    held = weight.shift(1)
    traded = held.diff().abs().fillna(held.abs())
    return (held * returns - cost * traded).dropna()


def sharpe(returns: pd.Series, periods: int) -> float:
    """Return per unit of risk, by the year."""
    spread = float(returns.std())
    return float(returns.mean() / spread * np.sqrt(periods)) if spread > 0 else 0.0


def deepest_fall(returns: pd.Series) -> float:
    """The largest fall from a high, as a negative share."""
    value = (1 + returns).cumprod()
    return float((value / value.cummax() - 1).min())


def sharpe_difference(
    rule: pd.Series,
    held: pd.Series,
    periods: int,
    block: int = 20,
    draws: int = 5000,
    seed: int = 7,
) -> tuple[float, float]:
    """The rule's Sharpe ratio minus holding throughout, and a two-sided p-value.

    Blocks of consecutive days are redrawn from both series together, so the link
    between the two and the clustering of rough days are both kept.
    """
    both = pd.concat([rule, held], axis=1, join="inner").dropna().to_numpy(dtype=float)
    n = len(both)
    observed = _sharpe_gap(both, periods)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block))))
    rows = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(draws, -1)[:, :n] % n
    gaps = np.array([_sharpe_gap(both[r], periods) for r in rows])
    centred = gaps - gaps.mean()
    p_value = float((np.abs(centred) >= abs(observed)).mean())
    return observed, p_value


def _sharpe_gap(both: np.ndarray, periods: int) -> float:
    spread = both.std(axis=0, ddof=1)
    if (spread <= 0).any():
        return 0.0
    ratios = both.mean(axis=0) / spread * np.sqrt(periods)
    return float(ratios[0] - ratios[1])


# ---------- Patterns and levels --------------------------------------------------------


def _days(index: pd.Index, rows: set[int] | np.ndarray) -> list[pd.Timestamp]:
    return [index[i] for i in sorted({int(r) for r in rows})]


def rsi_cases(close: pd.Series, below: bool, window: int = 14) -> list[pd.Timestamp]:
    """Days the index closed under 30 (`below`) or over 70."""
    reading = rsi(close, window)
    hit = reading < RSI_LOW if below else reading > RSI_HIGH
    return _days(close.index, np.flatnonzero(hit.to_numpy()))


def stochastic_cases(
    high: pd.Series, low: pd.Series, close: pd.Series, under: float = 20.0
) -> list[pd.Timestamp]:
    """Days the stochastic's fast line crossed above its slow line with both under
    `under` the day before: the textbook "oversold" turn."""
    fast, slow = stochastic(high, low, close)
    crossed = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    low_enough = (fast.shift(1) < under) & (slow.shift(1) < under)
    return _days(close.index, np.flatnonzero((crossed & low_enough).to_numpy()))


def fair_value_gap_cases(
    high: pd.Series, low: pd.Series, up: bool, wait: int = 20
) -> list[pd.Timestamp]:
    """First return to a three-day gap.

    Up: a day's low is above the high two days before; the gap lies between them, and
    the case is the first of the next `wait` days whose low reaches into it. Down is the
    mirror. The gap is known at its third day's close, and the case is dated on the day
    of the return.
    """
    highs, lows = high.to_numpy(dtype=float), low.to_numpy(dtype=float)
    cases: set[int] = set()
    for t in range(2, len(highs)):
        if up and lows[t] > highs[t - 2]:
            later = np.flatnonzero(lows[t + 1 : t + 1 + wait] <= lows[t])
        elif not up and highs[t] < lows[t - 2]:
            later = np.flatnonzero(highs[t + 1 : t + 1 + wait] >= highs[t])
        else:
            continue
        if len(later):
            cases.add(t + 1 + int(later[0]))
    return _days(high.index, cases)


def order_block_cases(
    frame: pd.DataFrame, up: bool, lookback: int = 20, search: int = 5, wait: int = 60
) -> list[pd.Timestamp]:
    """First return to an order block. `frame` has open, high, low, close.

    Up: a close above the highest high of the `lookback` days before marks a break. The
    block is the last falling day among the `search` days before the break, from its low
    to its high. The case is the first of the next `wait` days whose low reaches the
    block. Down is the mirror. A block is used once, at its first break.
    """
    opens, highs = frame["open"].to_numpy(dtype=float), frame["high"].to_numpy(dtype=float)
    lows, closes = frame["low"].to_numpy(dtype=float), frame["close"].to_numpy(dtype=float)
    cases: set[int] = set()
    used: set[int] = set()
    for t in range(lookback, len(closes)):
        if up:
            broke = closes[t] > highs[t - lookback : t].max()
        else:
            broke = closes[t] < lows[t - lookback : t].min()
        if not broke:
            continue
        before = np.arange(max(t - search, 0), t)
        against = closes[before] < opens[before] if up else closes[before] > opens[before]
        if not against.any():
            continue
        block = int(before[against][-1])
        if block in used:
            continue
        used.add(block)
        if up:
            later = np.flatnonzero(lows[t + 1 : t + 1 + wait] <= highs[block])
        else:
            later = np.flatnonzero(highs[t + 1 : t + 1 + wait] >= lows[block])
        if len(later):
            cases.add(t + 1 + int(later[0]))
    return _days(frame.index, cases)


def support_cases(low: pd.Series, window: int = 60, near: float = 0.005) -> list[pd.Timestamp]:
    """Days whose low came within `near` of the lowest low of the `window` days before,
    or went under it."""
    floor = low.shift(1).rolling(window).min()
    return _days(low.index, np.flatnonzero((low <= floor * (1 + near)).to_numpy()))


def resistance_cases(high: pd.Series, window: int = 60, near: float = 0.005) -> list[pd.Timestamp]:
    """Days whose high came within `near` of the highest high of the `window` days
    before, or went over it."""
    ceiling = high.shift(1).rolling(window).max()
    return _days(high.index, np.flatnonzero((high >= ceiling * (1 - near)).to_numpy()))


def new_high_cases(close: pd.Series, window: int = 252) -> list[pd.Timestamp]:
    """Days that closed above every close of the `window` days before."""
    ceiling = close.shift(1).rolling(window).max()
    return _days(close.index, np.flatnonzero((close > ceiling).to_numpy()))


def high_volume_cases(
    close: pd.Series, volume: pd.Series, rising: bool, window: int = 20, multiple: float = 2.0
) -> list[pd.Timestamp]:
    """Days with more than `multiple` times the average volume of the `window` days
    before, on a day that rose (`rising`) or fell."""
    usual = volume.shift(1).rolling(window).mean()
    change = close.diff()
    way = change > 0 if rising else change < 0
    return _days(close.index, np.flatnonzero(((volume > multiple * usual) & way).to_numpy()))


# ---------- Direction models -----------------------------------------------------------


def days_to_event(index: pd.DatetimeIndex, dates: list[date], cap: int = 10) -> pd.Series:
    """Calendar days from each day to the next scheduled event, at most `cap`. The
    schedule is published ahead, so this is known on the day."""
    if not dates:
        return pd.Series(float(cap), index=index)
    ordinals = np.array(sorted(d.toordinal() for d in dates))
    today = np.array([stamp.date().toordinal() for stamp in index])
    nxt = np.searchsorted(ordinals, today, side="left")
    gap = np.where(nxt < len(ordinals), ordinals[np.minimum(nxt, len(ordinals) - 1)] - today, cap)
    return pd.Series(np.minimum(gap, cap).astype(float), index=index)


def features(frame: pd.DataFrame, dates: list[date]) -> pd.DataFrame:
    """What a model may know at each day's close. `frame` has high, low, close, volume."""
    close = frame["close"]
    returns = close.pct_change()
    index = pd.DatetimeIndex(frame.index)
    table = pd.DataFrame(
        {
            "ret_1": returns,
            "ret_5": close.pct_change(5),
            "ret_20": close.pct_change(20),
            "ret_60": close.pct_change(60),
            "ret_252": close.pct_change(252),
            "rsi": rsi(close),
            "from_sma_50": close / sma(close, 50) - 1,
            "from_sma_200": close / sma(close, 200) - 1,
            "swing_20": swing(returns, 20),
            "swing_20_over_60": swing(returns, 20) / swing(returns, 60),
            "volume_ratio": frame["volume"] / frame["volume"].rolling(20).mean(),
            "from_high_252": close / frame["high"].rolling(252).max() - 1,
            "from_low_252": close / frame["low"].rolling(252).min() - 1,
            "days_to_event": days_to_event(index, dates),
        },
        index=frame.index,
    )
    return table[list(FEATURES)]


def rises(close: pd.Series, steps: int) -> pd.Series:
    """1 where the close `steps` days later is higher, 0 where it is not, and missing
    where that day has not happened yet."""
    later = close.shift(-steps)
    return (later > close).astype(float).where(later.notna())


Fit = Callable[[np.ndarray, np.ndarray], Callable[[np.ndarray], np.ndarray]]


def fit_trees(x: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """Gradient-boosted trees: the chance that the next week ends higher.

    Kept small on purpose: few, shallow trees with large leaves. These settings were
    chosen on a planted pattern only (decision 061), never on real outcomes: they
    recover it, where the first settings (`fit_trees_heavy`) did not.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(
        max_depth=2,
        max_iter=60,
        learning_rate=0.05,
        min_samples_leaf=50,
        l2_regularization=1.0,
        random_state=0,
    ).fit(x, y)
    return lambda rows: np.asarray(model.predict_proba(rows)[:, 1], dtype=float)


def fit_trees_heavy(x: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """The first settings tried. With a few thousand days they fit noise and miss even a
    planted pattern; kept so the notebook can show that."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(
        max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=20, random_state=0
    ).fit(x, y)
    return lambda rows: np.asarray(model.predict_proba(rows)[:, 1], dtype=float)


def fit_network(x: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """A small neural network on inputs scaled by the training days only."""
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(16, 8), alpha=0.01, max_iter=500, random_state=0),
    ).fit(x, y)
    return lambda rows: np.asarray(model.predict_proba(rows)[:, 1], dtype=float)


def walk_forward(
    table: pd.DataFrame,
    target: pd.Series,
    steps: int,
    fit: Fit,
    min_train: int = MIN_TRAIN,
    refit_every: int = REFIT_EVERY,
) -> pd.Series:
    """The model's chance of a rise for each day from row `min_train` on.

    The model is refitted every `refit_every` days. At a fit on row `f` it sees only
    rows `i` with `i + steps <= f`: days whose outcome had already happened. Rows with a
    missing input (the warm-up) are never trained on or forecast.
    """
    complete = table.notna().all(axis=1).to_numpy()
    x, y = table.to_numpy(dtype=float), target.to_numpy(dtype=float)
    chance = np.full(len(table), np.nan)
    for start in range(min_train, len(table), refit_every):
        known = np.arange(len(table)) + steps <= start
        train = complete & known & ~np.isnan(y)
        if train.sum() < 100 or len(np.unique(y[train])) < 2:
            continue
        predict = fit(x[train], y[train])
        rows = np.arange(start, min(start + refit_every, len(table)))
        rows = rows[complete[rows]]
        if len(rows):
            chance[rows] = predict(x[rows])
    return pd.Series(chance, index=table.index, name="chance")
