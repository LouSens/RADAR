"""Does news help forecast the size of swings? (spec F9, decisions 028 and 044)

A walk-forward comparison of the volatility forecast with and without news inputs. Two
model families are each run both ways, so that any gain can be put down to the news and
not to a change of model:

- HAR: log volatility regressed on the swings of the last day, week, and month.
- Trees: gradient-boosted trees on the same inputs.

The news inputs for day `t` use articles published by the end of day `t` and nothing
later, and the surprise in volume is measured against the 22 days before `t`. Every
model is refitted on days before the block it forecasts, using only outcomes that were
complete by then.

The verdict follows a rule written down before the first run (decision 044).
"""

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from radar.models import volatility

MODEL_VERSION = "news-volatility-1"
NEWS_FEATURES = ("news_count", "news_surprise", "news_tone", "news_tone_size")
# Days the volume surprise is measured against.
BASELINE_DAYS = 22
# Each model with news is compared with the same model without it.
PAIRS = (("har_news", "har"), ("gbt_news", "gbt"))
MODELS = ("har", "har_news", "gbt", "gbt_news")
SIGNIFICANCE = 0.05

Verdict = Literal["news helps", "no measurable gain"]


def news_features(count: pd.Series, tone: pd.Series) -> pd.DataFrame:
    """The four news inputs, one row per day. Trailing only.

    `count` is the number of articles on each day and `tone` their average tone (-1 to
    +1, empty on a day with none). The surprise compares a day's volume with the average
    of the `BASELINE_DAYS` days before it, not including the day itself.
    """
    volume = pd.Series(np.log1p(count.fillna(0).to_numpy(dtype=float)), index=count.index)
    usual = volume.shift(1).rolling(BASELINE_DAYS, min_periods=BASELINE_DAYS).mean()
    neutral = tone.astype(float).fillna(0.0)
    return pd.DataFrame(
        {
            "news_count": volume,
            "news_surprise": volume - usual,
            "news_tone": neutral,
            "news_tone_size": neutral.abs(),
        },
        index=count.index,
    )


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    design = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ beta
    spare = max(len(y) - design.shape[1], 1)
    return beta, float(residual @ residual) / spare


def _linear(train_x: np.ndarray, train_y: np.ndarray, block_x: np.ndarray) -> np.ndarray:
    beta, variance = _ols(train_x, train_y)
    log_forecast = beta[0] + block_x @ beta[1:]
    return np.asarray(np.exp(log_forecast + 0.5 * variance), dtype=float)


def walk_forward(
    rv: pd.Series,
    news: pd.DataFrame,
    steps: int,
    *,
    min_train: int = 250,
    refit_every: int = 21,
    seed: int = 7,
) -> pd.DataFrame:
    """Forecasts of all four models for every day after the first `min_train`.

    `rv` is daily realised volatility and `news` the frame from `news_features`, on the
    same days. Returns a column per model plus `realised`, which is empty until the days
    a forecast covers have ended.
    """
    har = volatility.har_features(rv)
    inputs = pd.concat([har, news.reindex(rv.index)], axis=1)
    usable_rows = inputs.notna().all(axis=1).to_numpy()
    plain = inputs[list(volatility.HAR_FEATURES)].to_numpy(dtype=float)
    with_news = inputs[[*volatility.HAR_FEATURES, *NEWS_FEATURES]].to_numpy(dtype=float)
    outcome = volatility.target(rv, steps).to_numpy(dtype=float)
    n = len(rv)
    first = int(np.argmax(usable_rows)) if usable_rows.any() else n
    start_at = first + min_train
    if start_at >= n:
        raise ValueError("Not enough history for a walk-forward comparison")

    columns: dict[str, list[np.ndarray]] = {m: [] for m in MODELS}
    for start in range(start_at, n, refit_every):
        end = min(start + refit_every, n)
        # Days before the block whose outcome was complete before the block began.
        known = start - steps
        train = usable_rows[:known] & ~np.isnan(outcome[:known])
        y = np.log(outcome[:known][train])
        block_ok = usable_rows[start:end]
        for name, features in (("har", plain), ("har_news", with_news)):
            forecast = np.full(end - start, np.nan)
            forecast[block_ok] = _linear(features[:known][train], y, features[start:end][block_ok])
            columns[name].append(forecast)
        for name, features in (("gbt", plain), ("gbt_news", with_news)):
            forecast = np.full(end - start, np.nan)
            trees = volatility._fit_trees(features[:known][train], y, seed)
            forecast[block_ok] = np.exp(
                trees.predict(features[start:end][block_ok])  # type: ignore[attr-defined]
            )
            columns[name].append(forecast)

    frame = pd.DataFrame({m: np.concatenate(columns[m]) for m in MODELS}, index=rv.index[start_at:])
    frame["realised"] = outcome[start_at:]
    return frame


class PairResult(BaseModel):
    """One model with news against the same model without it."""

    family: Literal["har", "gbt"]
    qlike_without: float
    qlike_with: float
    # Share by which news lowered the loss; negative when it raised it.
    improvement: float
    dm_statistic: float | None
    dm_p_value: float | None
    # The p-value corrected for every comparison made together.
    dm_p_adjusted: float | None = None
    verdict: Verdict = "no measurable gain"


class HorizonResult(BaseModel):
    steps: int
    horizon_days: int
    n: int
    first_day: date
    last_day: date
    pairs: list[PairResult]


def evaluate(frame: pd.DataFrame, steps: int, horizon_days: int) -> HorizonResult:
    """Score each pair on the days all four forecasts and the outcome are known."""
    known = frame.dropna()
    if len(known) < 30:
        raise ValueError("Too few scored days to compare the models")
    realised = known["realised"].to_numpy()
    losses = {m: volatility.qlike(realised, known[m].to_numpy()) for m in MODELS}
    pairs = []
    for with_news, without in PAIRS:
        statistic, p_value = volatility.diebold_mariano(losses[with_news], losses[without], steps)
        mean_without = float(losses[without].mean())
        mean_with = float(losses[with_news].mean())
        pairs.append(
            PairResult(
                family="har" if without == "har" else "gbt",
                qlike_without=mean_without,
                qlike_with=mean_with,
                improvement=(mean_without - mean_with) / mean_without if mean_without else 0.0,
                dm_statistic=None if np.isnan(statistic) else statistic,
                dm_p_value=None if np.isnan(p_value) else p_value,
            )
        )
    index = pd.DatetimeIndex(known.index)
    return HorizonResult(
        steps=steps,
        horizon_days=horizon_days,
        n=len(known),
        first_day=index[0].date(),
        last_day=index[-1].date(),
        pairs=pairs,
    )


def judge(pair: PairResult, p_adjusted: float | None) -> PairResult:
    """The rule of decision 044: lower loss with news, and unlikely to be chance after
    correcting for every comparison made together."""
    helps = (
        pair.qlike_with < pair.qlike_without
        and p_adjusted is not None
        and p_adjusted < SIGNIFICANCE
    )
    return pair.model_copy(
        update={
            "dm_p_adjusted": p_adjusted,
            "verdict": "news helps" if helps else "no measurable gain",
        }
    )
