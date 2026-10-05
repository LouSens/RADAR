"""F9. Volatility forecast: how large the daily price swings are likely to be next.

Two models and two simple rivals forecast the realised volatility of the next `steps`
days, expressed per day (the square root of the average daily variance over those days).

- HAR: a regression of the log of that figure on the log volatility of the last day, the
  last week, and the last month. The standard, hard-to-beat model for this job.
- Gradient-boosted trees on the same three inputs plus the regime probabilities.
- Rival 1: yesterday's volatility carried forward.
- Rival 2: the average volatility seen before in the current regime.

No lookahead: every input of day `t` uses day `t` and earlier days only, and a model that
forecasts from day `t` is fitted only on days whose outcome was already known.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy import stats

from radar.models import regime

MODEL_VERSION = "volatility-har-1"
WEEK = 5
MONTH = 22
HAR_FEATURES = ("log_day", "log_week", "log_month")
MODELS = ("har", "gbt", "carry", "regime")
# Fewer past days than this in a regime and its average is not trusted on its own.
MIN_REGIME_DAYS = 20
SIGNIFICANCE = 0.05


def har_features(rv: pd.Series) -> pd.DataFrame:
    """Log volatility of the last day, week, and month. Trailing windows only."""
    variance = rv.astype(float) ** 2
    return pd.DataFrame(
        {
            "log_day": np.log(rv.astype(float)),
            "log_week": 0.5 * np.log(variance.rolling(WEEK, min_periods=WEEK).mean()),
            "log_month": 0.5 * np.log(variance.rolling(MONTH, min_periods=MONTH).mean()),
        },
        index=rv.index,
    )


def target(rv: pd.Series, steps: int) -> pd.Series:
    """Per-day realised volatility over the `steps` days after each day.

    The value on day `t` covers days `t+1` to `t+steps`, so it is only known once day
    `t+steps` has ended. Days whose future is not complete are empty.
    """
    variance = rv.astype(float) ** 2
    ahead = variance.rolling(steps, min_periods=steps).mean().shift(-steps)
    return pd.Series(np.sqrt(ahead.to_numpy()), index=rv.index, name="target")


class HarModel(BaseModel):
    """A fitted HAR model for one horizon, as plain numbers."""

    version: str = MODEL_VERSION
    steps: int
    intercept: float
    coefficients: dict[str, float]
    # Variance of the fit's errors in log units; used to undo the log without bias.
    residual_variance: float
    train_start: date
    train_end: date
    n_train: int


def fit(rv: pd.Series, steps: int) -> HarModel:
    """Fit HAR on every day of `rv` whose outcome lies inside `rv`. Pass training days only."""
    frame = har_features(rv).assign(target=np.log(target(rv, steps))).dropna()
    if len(frame) < 60:
        raise ValueError(f"Need at least 60 usable days to fit; got {len(frame)}")
    x = np.column_stack([np.ones(len(frame)), frame[list(HAR_FEATURES)].to_numpy()])
    y = frame["target"].to_numpy()
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ beta
    index = pd.DatetimeIndex(frame.index)
    return HarModel(
        steps=steps,
        intercept=float(beta[0]),
        coefficients={name: float(b) for name, b in zip(HAR_FEATURES, beta[1:], strict=True)},
        residual_variance=float(residual.var(ddof=x.shape[1])),
        train_start=index[0].date(),
        train_end=index[-1].date(),
        n_train=len(frame),
    )


def predict(model: HarModel, rv: pd.Series) -> pd.Series:
    """Forecast per-day volatility over the next `model.steps` days, from each day of `rv`."""
    features = har_features(rv)
    weights = np.array([model.coefficients[name] for name in HAR_FEATURES])
    log_forecast = model.intercept + features[list(HAR_FEATURES)].to_numpy() @ weights
    return pd.Series(
        np.exp(log_forecast + 0.5 * model.residual_variance), index=rv.index, name="har"
    )


def save(model: HarModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=1), encoding="utf-8", newline="\n")


def load(path: Path) -> HarModel:
    return HarModel.model_validate_json(path.read_text(encoding="utf-8"))


# --- walk-forward ----------------------------------------------------------------------


@dataclass
class WalkForward:
    """Forecasts for every day after the training window, for one horizon."""

    steps: int
    # One row per forecast day: a column per model in MODELS, plus `realised` (empty
    # until the outcome is known).
    forecasts: pd.DataFrame
    # The HAR model behind the latest forecasts.
    latest: HarModel


def _fit_trees(x: np.ndarray, y: np.ndarray, seed: int) -> object:
    from sklearn.ensemble import HistGradientBoostingRegressor

    model = HistGradientBoostingRegressor(
        max_depth=3, max_iter=150, learning_rate=0.05, min_samples_leaf=20, random_state=seed
    )
    return model.fit(x, y)


def walk_forward(
    observations: pd.DataFrame,
    steps: tuple[int, ...],
    *,
    min_train: int = 500,
    refit_every: int = 63,
    seed: int = 7,
    n_init: int = 2,
) -> dict[int, WalkForward]:
    """Forecast from every day after the first `min_train`, refitting every `refit_every` days.

    `observations` has columns `ret`, `log_rv`, and `rv`, one row per day. At each refit
    the models see only days before the block they forecast, and only outcomes that were
    complete by then.
    """
    clean = observations.dropna(subset=[*regime.FEATURES, "rv"])
    n = len(clean)
    if n <= min_train:
        raise ValueError("Not enough history for a walk-forward forecast")
    rv = clean["rv"]
    har = har_features(rv)
    outcomes = {s: target(rv, s) for s in steps}
    columns: dict[int, dict[str, list[np.ndarray]]] = {s: {m: [] for m in MODELS} for s in steps}
    latest: dict[int, HarModel] = {}

    for start in range(min_train, n, refit_every):
        end = min(start + refit_every, n)
        block = slice(start, end)
        regime_model = regime.fit(clean.iloc[:start], n_init=n_init, seed=seed)
        # Filtered, so each day's probabilities use that day and earlier days only.
        probabilities = regime.filtered_probabilities(regime_model, clean.iloc[:end])
        labels = probabilities.to_numpy().argmax(axis=1)
        tree_inputs = np.column_stack([har.to_numpy()[:end], probabilities.to_numpy()])
        for s in steps:
            # Days before the block whose outcome was complete before the block began.
            known = start - s
            model = fit(rv.iloc[:start], s)
            latest[s] = model
            columns[s]["har"].append(predict(model, rv.iloc[:end]).to_numpy()[block])
            columns[s]["carry"].append(rv.to_numpy()[block])

            outcome = outcomes[s].to_numpy()[:known]
            usable = ~np.isnan(tree_inputs[:known]).any(axis=1) & ~np.isnan(outcome)
            trees = _fit_trees(tree_inputs[:known][usable], np.log(outcome[usable]), seed)
            block_inputs = np.nan_to_num(tree_inputs[block], nan=0.0)
            columns[s]["gbt"].append(np.exp(trees.predict(block_inputs)))  # type: ignore[attr-defined]

            overall = float(np.sqrt(np.nanmean(outcome**2)))
            by_regime = np.full(regime_model.n_states, overall)
            for k in range(regime_model.n_states):
                seen = outcome[(labels[:known] == k) & ~np.isnan(outcome)]
                if len(seen) >= MIN_REGIME_DAYS:
                    by_regime[k] = float(np.sqrt(np.mean(seen**2)))
            columns[s]["regime"].append(by_regime[labels[block]])

    index = clean.index[min_train:]
    result = {}
    for s in steps:
        frame = pd.DataFrame({m: np.concatenate(columns[s][m]) for m in MODELS}, index=index)
        frame["realised"] = outcomes[s].to_numpy()[min_train:]
        result[s] = WalkForward(steps=s, forecasts=frame, latest=latest[s])
    return result


# --- evaluation ------------------------------------------------------------------------


def qlike(realised: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    """QLIKE loss per day, on variances. Zero for a perfect forecast; lower is better."""
    ratio = (realised / forecast) ** 2
    loss: np.ndarray = ratio - np.log(ratio) - 1.0
    return loss


def squared_error(realised: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    error: np.ndarray = (realised - forecast) ** 2
    return error


def diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, steps: int = 1) -> tuple[float, float]:
    """Test whether two forecasts' losses differ. Returns (statistic, two-sided p-value).

    A negative statistic means `a` had the lower loss. Forecasts `steps` days ahead have
    overlapping errors, so the variance allows for autocorrelation up to `steps - 1` days
    (Newey-West), with the Harvey-Leybourne-Newbold small-sample correction.
    """
    d = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    n = len(d)
    if n < 10:
        return float("nan"), float("nan")
    centred = d - d.mean()
    variance = float(centred @ centred) / n
    for lag in range(1, steps):
        weight = 1.0 - lag / steps
        variance += 2.0 * weight * float(centred[lag:] @ centred[:-lag]) / n
    if variance <= 0:
        return float("nan"), float("nan")
    statistic = d.mean() / np.sqrt(variance / n)
    correction = np.sqrt(max((n + 1 - 2 * steps + steps * (steps - 1) / n) / n, 1e-12))
    statistic *= correction
    p_value = 2.0 * float(stats.t.sf(abs(statistic), df=n - 1))
    return float(statistic), p_value


class ModelScore(BaseModel):
    model: str
    qlike: float
    mse: float
    # Against HAR: the test statistic and p-value on QLIKE. Empty for HAR itself.
    dm_statistic_vs_har: float | None = None
    dm_p_value_vs_har: float | None = None


class HorizonEvaluation(BaseModel):
    """Walk-forward results for one horizon. Every number is out of sample."""

    steps: int
    n: int
    first_day: date
    last_day: date
    scores: list[ModelScore]
    # The model whose forecast is displayed, and why.
    shown: str
    reason: str


def evaluate(walk: WalkForward) -> HorizonEvaluation:
    """Score every model on the days whose outcome is known, and pick the one to show.

    The trees are shown only if their QLIKE is lower than HAR's and the Diebold-Mariano
    test says the gap is unlikely to be chance (p below 0.05). Otherwise HAR is shown.
    """
    known = walk.forecasts.dropna()
    if known.empty:
        raise ValueError("No forecast has a known outcome yet")
    realised = known["realised"].to_numpy()
    losses = {m: qlike(realised, known[m].to_numpy()) for m in MODELS}
    scores = []
    for name in MODELS:
        score = ModelScore(
            model=name,
            qlike=float(losses[name].mean()),
            mse=float(squared_error(realised, known[name].to_numpy()).mean()),
        )
        if name != "har":
            statistic, p_value = diebold_mariano(losses[name], losses["har"], walk.steps)
            score.dm_statistic_vs_har = None if np.isnan(statistic) else statistic
            score.dm_p_value_vs_har = None if np.isnan(p_value) else p_value
        scores.append(score)
    by_name = {s.model: s for s in scores}
    trees, har = by_name["gbt"], by_name["har"]
    trees_win = (
        trees.qlike < har.qlike
        and trees.dm_p_value_vs_har is not None
        and trees.dm_p_value_vs_har < SIGNIFICANCE
    )
    index = pd.DatetimeIndex(known.index)
    return HorizonEvaluation(
        steps=walk.steps,
        n=len(known),
        first_day=index[0].date(),
        last_day=index[-1].date(),
        scores=scores,
        shown="gbt" if trees_win else "har",
        reason="trees_beat_har" if trees_win else "trees_did_not_beat_har",
    )
