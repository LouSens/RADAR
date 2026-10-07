"""An ensemble for two questions about paying in (decision 070).

- Is today's close below the average close of the days left in the month? If that could
  be told, waiting for the right day would get a lower price.
- Will there be a close at least 5% lower within the next month? That is a forecast of
  risk, not of direction.

Four different kinds of model are trained on every market at once, each is turned into a
calibrated chance on a validation year, and the chances are averaged (soft voting).

Pure functions. No lookahead: every input for a day uses that day and earlier days only;
an answer is only ever used to fit a model once the days it depends on have passed, with
a gap between fitting, validation and test; nothing is shuffled in time.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from radar.analytics import technical as ta

MODEL_VERSION = "payin-1"
MONTH = 21
DROP = 0.05
GAP_DAYS = 35
VALIDATION_DAYS = 365
CAP = 20.0
GROUPS = ("stocks", "bonds", "commodities", "crypto")
CONTEXT = ("stocks_ret_20", "stocks_swing_20", "bonds_ret_20", "credit_20")
INPUTS = (
    "ret_1",
    "ret_5",
    "ret_20",
    "ret_60",
    "rsi",
    "stoch_fast",
    "stoch_slow",
    "from_ema_9",
    "from_ema_13",
    "from_ema_50",
    "from_ema_200",
    "place_in_range_20",
    "from_high_60",
    "from_fib",
    "since_gap",
    "since_block",
    "swing_20",
    "swing_20_over_60",
    "day_range",
    "volume_ratio",
    "falling_run",
    "days_to_event",
    *CONTEXT,
    *(f"is_{group}" for group in GROUPS),
)
PLANTED_HIGH, PLANTED_LOW = 0.70, 0.45
THRESHOLDS = (0.50, 0.55, 0.60, 0.65, 0.70)


# ---------- Inputs ----------------------------------------------------------------------


def context(
    stocks: pd.Series, bonds: pd.Series, high_yield: pd.Series, treasuries: pd.Series
) -> pd.DataFrame:
    """What the wider markets have been doing, from four funds' closes: the stock
    fund's 20-day return and swing, the long bond fund's 20-day return, and high-yield
    bonds against Treasuries over 20 days (falling when lenders are worried)."""
    credit = high_yield / treasuries
    return pd.DataFrame(
        {
            "stocks_ret_20": stocks.pct_change(20),
            "stocks_swing_20": stocks.pct_change().rolling(20).std(),
            "bonds_ret_20": bonds.pct_change(20),
            "credit_20": credit.pct_change(20),
        }
    )


def _since(index: pd.Index, cases: list[pd.Timestamp], cap: float = CAP) -> np.ndarray:
    """Days since the latest case, the day of a case counting as 0, at most `cap`."""
    on = ta.flags(index, cases)
    result, last = np.full(len(on), cap), -1
    for i, hit in enumerate(on):
        if hit:
            last = i
        if last >= 0:
            result[i] = min(float(i - last), cap)
    return result


def _falling_run(close: pd.Series, cap: float = 10.0) -> np.ndarray:
    """How many closes in a row have been lower than the one before."""
    falls = (close.diff() < 0).to_numpy()
    result, run = np.zeros(len(falls)), 0
    for i, fell in enumerate(falls):
        run = run + 1 if fell else 0
        result[i] = min(float(run), cap)
    return result


def inputs(frame: pd.DataFrame, dates: list[date], wider: pd.DataFrame, group: str) -> pd.DataFrame:
    """What a model may know at each day's close. `frame` has open, high, low, close,
    volume; `wider` is `context(...)`; `group` is one of `GROUPS`.

    Returns and gaps are divided by the market's own usual daily swing (60 days), so a
    2% day in a bond fund and a 2% day in a coin are not read as the same thing.
    """
    high, low, close = frame["high"], frame["low"], frame["close"]
    index = pd.DatetimeIndex(frame.index)
    returns = close.pct_change()
    usual = returns.rolling(60).std()
    fast, slow = ta.stochastic(high, low, close)
    highest, lowest = high.rolling(20).max(), low.rolling(20).min()
    levels = ta.fibonacci_level(high, low)
    table = pd.DataFrame(
        {
            "ret_1": returns / usual,
            "ret_5": close.pct_change(5) / (usual * np.sqrt(5)),
            "ret_20": close.pct_change(20) / (usual * np.sqrt(20)),
            "ret_60": close.pct_change(60) / (usual * np.sqrt(60)),
            "rsi": ta.rsi(close) / 100,
            "stoch_fast": fast / 100,
            "stoch_slow": slow / 100,
            "from_ema_9": (close / ta.ema(close, 9) - 1) / usual,
            "from_ema_13": (close / ta.ema(close, 13) - 1) / usual,
            "from_ema_50": (close / ta.ema(close, 50) - 1) / usual,
            "from_ema_200": (close / ta.ema(close, 200) - 1) / usual,
            "place_in_range_20": (close - lowest) / (highest - lowest).where(highest > lowest),
            "from_high_60": (close / high.rolling(60).max() - 1) / usual,
            "from_fib": (close / levels["level"] - 1) / usual,
            "since_gap": _since(index, ta.fair_value_gap_cases(high, low, up=True)),
            "since_block": _since(index, ta.order_block_cases(frame, up=True)),
            "swing_20": returns.rolling(20).std(),
            "swing_20_over_60": returns.rolling(20).std() / usual,
            "day_range": (high - low) / close / usual,
            "volume_ratio": np.log(
                (frame["volume"] / frame["volume"].rolling(20).mean()).clip(lower=1e-3)
            ),
            "falling_run": _falling_run(close),
            "days_to_event": ta.days_to_event(index, dates),
        },
        index=frame.index,
    )
    # A market that trades at weekends carries the funds' last close forward.
    carried = wider.reindex(wider.index.union(frame.index)).ffill().reindex(frame.index)
    for name in CONTEXT:
        table[name] = carried[name]
    for other in GROUPS:
        table[f"is_{other}"] = float(other == group)
    scaled = [c for c in table.columns if c.startswith(("ret_", "from_")) or c == "day_range"]
    table[scaled] = table[scaled].clip(-CAP, CAP)
    return table[list(INPUTS)]


# ---------- Answers ---------------------------------------------------------------------


def days_left(days: int, starts: np.ndarray, every: int = MONTH) -> np.ndarray:
    """For each row, the days left in its month after it; missing outside the months."""
    left = np.full(days, np.nan)
    for start in starts:
        left[start : start + every] = np.arange(every - 1, -1, -1)
    return left


def cheaper_than_rest(close: pd.Series, starts: np.ndarray, every: int = MONTH) -> pd.Series:
    """1 where the day's close is below the average close of the days left in its
    month, 0 where it is not; missing on a month's last day and outside the months."""
    prices = close.to_numpy(dtype=float)
    answer = np.full(len(prices), np.nan)
    for start in starts:
        for offset in range(every - 1):
            rest = prices[start + offset + 1 : start + every]
            answer[start + offset] = float(prices[start + offset] < rest.mean())
    return pd.Series(answer, index=close.index)


def dips(close: pd.Series, drop: float = DROP, days: int = MONTH) -> pd.Series:
    """1 where some close in the next `days` days is at least `drop` below the day's,
    0 where none is; missing for the last `days` days, whose answer is not known yet."""
    prices = close.to_numpy(dtype=float)
    answer = np.full(len(prices), np.nan)
    for t in range(len(prices) - days):
        answer[t] = float(prices[t + 1 : t + 1 + days].min() <= (1 - drop) * prices[t])
    return pd.Series(answer, index=close.index)


def own_share_so_far(answers: pd.Series, days: int = MONTH) -> pd.Series:
    """The share of earlier days whose answer was 1, using only answers already known:
    the answer for a day is known `days` days after it. The first baseline."""
    known = answers.shift(days + 1)
    return known.expanding(min_periods=60).mean()


def planted_answers(table: pd.DataFrame, seed: int) -> pd.Series:
    """Made-up answers with a known rule in two inputs: 1 with a 70% chance when the
    stochastic is under 0.3 and the 20-day return is negative, 45% otherwise. For
    checking that a model can learn at all."""
    rng = np.random.default_rng(seed)
    chance = planted_chance(table)
    made_up = (rng.random(len(table)) < chance).astype(float)
    return pd.Series(made_up, index=table.index)


def planted_chance(table: pd.DataFrame) -> np.ndarray:
    marked = (table["stoch_fast"] < 0.3) & (table["ret_20"] < 0)
    result: np.ndarray = np.where(marked, PLANTED_HIGH, PLANTED_LOW)
    return result


# ---------- Time order ------------------------------------------------------------------


@dataclass(frozen=True)
class Fold:
    year: int
    fit: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def by_year(
    days: np.ndarray,
    first_year: int,
    last_year: int,
    gap_days: int = GAP_DAYS,
    validation_days: int = VALIDATION_DAYS,
) -> list[Fold]:
    """One fold per test year. `days` holds each row's date (datetime64).

    Test: the year. Validation: the `validation_days` ending `gap_days` before the year
    starts. Fit: everything ending `gap_days` before validation starts. The gaps are
    longer than the month an answer looks ahead, so no answer used earlier depends on a
    day used later.
    """
    days = days.astype("datetime64[D]")
    gap, span = np.timedelta64(gap_days, "D"), np.timedelta64(validation_days, "D")
    folds = []
    for year in range(first_year, last_year + 1):
        start, end = np.datetime64(f"{year}-01-01"), np.datetime64(f"{year + 1}-01-01")
        validation_end = start - gap
        validation_start = validation_end - span
        folds.append(
            Fold(
                year=year,
                fit=np.flatnonzero(days < validation_start - gap),
                validation=np.flatnonzero((days >= validation_start) & (days < validation_end)),
                test=np.flatnonzero((days >= start) & (days < end)),
            )
        )
    return folds


# ---------- The ensemble ----------------------------------------------------------------


def members(seed: int = 0) -> dict[str, Any]:
    """Four different kinds of model, unfitted. Settings were chosen on the planted
    pattern only (decision 070)."""
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)),
        "forest": RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=100,
            max_features="sqrt",
            n_jobs=-1,
            random_state=seed,
        ),
        "boosted": HistGradientBoostingClassifier(
            max_depth=4,
            max_iter=300,
            learning_rate=0.03,
            min_samples_leaf=100,
            l2_regularization=1.0,
            early_stopping=False,
            random_state=seed,
        ),
        "network": make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(32, 16),
                alpha=1.0,
                max_iter=200,
                early_stopping=False,
                random_state=seed,
            ),
        ),
    }


def _logit(chance: np.ndarray) -> np.ndarray:
    clipped = np.clip(chance, 1e-4, 1 - 1e-4)
    result: np.ndarray = np.log(clipped / (1 - clipped))
    return result


@dataclass
class Vote:
    """Fitted members, each with the line that turns its raw output into a chance."""

    models: dict[str, Any]
    lines: dict[str, Any]

    def chances(self, x: np.ndarray) -> dict[str, np.ndarray]:
        """Each member's calibrated chance of a 1, and their average under "vote"."""
        result: dict[str, np.ndarray] = {}
        for name, model in self.models.items():
            raw = _logit(model.predict_proba(x)[:, 1]).reshape(-1, 1)
            result[name] = self.lines[name].predict_proba(raw)[:, 1]
        result["vote"] = np.mean([result[name] for name in self.models], axis=0)
        return result


def fit_vote(
    x: np.ndarray,
    y: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    seed: int = 0,
    only: tuple[str, ...] | None = None,
) -> Vote:
    """Fit each member on `x`, then fit its calibration line on the validation rows,
    which come later and were not used to fit it."""
    from sklearn.linear_model import LogisticRegression

    models, lines = {}, {}
    for name, model in members(seed).items():
        if only is not None and name not in only:
            continue
        models[name] = model.fit(x, y)
        raw = _logit(model.predict_proba(x_validation)[:, 1]).reshape(-1, 1)
        lines[name] = LogisticRegression(C=1e6, max_iter=1000).fit(raw, y_validation)
    return Vote(models=models, lines=lines)


# ---------- Scoring ---------------------------------------------------------------------


def brier(chance: np.ndarray, answers: np.ndarray) -> float:
    """The average squared gap between the stated chance and what happened: 0 is
    perfect, 0.25 is what always saying 50% scores."""
    return float(np.mean((chance - answers) ** 2))


def month_keys(days: np.ndarray) -> np.ndarray:
    """Each row's calendar month, as a number that orders them."""
    result: np.ndarray = days.astype("datetime64[M]").astype(int)
    return result


def resampled_gain(
    keys: np.ndarray, loss: np.ndarray, base: np.ndarray, draws: int = 2000, seed: int = 7
) -> tuple[float, float]:
    """How much smaller the model's total loss is than the baseline's, as a share, and
    the share of resamples in which it is not smaller.

    Whole calendar months are resampled, every market's rows in a month together,
    because markets fall on the same days and answers a few days apart overlap.
    """
    months, position = np.unique(keys, return_inverse=True)
    model_by_month = np.bincount(position, weights=loss, minlength=len(months))
    base_by_month = np.bincount(position, weights=base, minlength=len(months))
    gain = 1 - model_by_month.sum() / base_by_month.sum()
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(months), size=(draws, len(months)))
    gains = 1 - model_by_month[picks].sum(axis=1) / base_by_month[picks].sum(axis=1)
    return float(gain), float(np.mean(gains <= 0))


def reliability(chance: np.ndarray, answers: np.ndarray, bands: int = 10) -> pd.DataFrame:
    """In each band of stated chance: how many days, the average chance stated, and how
    often it happened."""
    edges = np.linspace(0, 1, bands + 1)
    place = np.minimum(np.digitize(chance, edges[1:-1]), bands - 1)
    rows = []
    for band in range(bands):
        inside = place == band
        if inside.any():
            rows.append(
                {
                    "from": edges[band],
                    "to": edges[band + 1],
                    "days": int(inside.sum()),
                    "stated": float(chance[inside].mean()),
                    "happened": float(answers[inside].mean()),
                }
            )
    return pd.DataFrame(rows)


def calibrated(table: pd.DataFrame, least: int = 200, within: float = 0.05) -> bool:
    """Whether, in every band with at least `least` days, what happened is within
    `within` of what was stated."""
    judged = table[table["days"] >= least]
    return bool(((judged["stated"] - judged["happened"]).abs() <= within).all())
