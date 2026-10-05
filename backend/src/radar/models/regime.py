"""F1. Regime detector: a Gaussian hidden Markov model on daily return and volatility.

The model looks at two numbers per day, the log return and the log of realised
volatility smoothed over about five days (see `smoothed_log_volatility`), and learns a
small number of market states (calm, normal, turbulent) plus how likely each state is to
follow another.

No lookahead: `filtered_probabilities` gives, for each day, the probability of each state
using that day and earlier days only. That is what the app shows as "current" and what
every backtest uses. `smoothed_probabilities` also uses later days and is for a clearly
labelled hindsight view, nothing else.

States are ordered by their average volatility after every fit, so "calm" always means
the lowest-volatility state and labels cannot swap between refits.
"""

import warnings
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from pydantic import BaseModel
from scipy.special import logsumexp

MODEL_VERSION = "regime-hmm-1"
FEATURES = ("ret", "log_rv")
VOLATILITY_FEATURE = 1  # index of log_rv in FEATURES
CANDIDATE_STATES = (2, 3, 4)
# Fixed at three so calm, normal, and turbulent mean the same for every asset
# (docs/DECISIONS.md 025). BIC for the other counts is still reported.
DEFAULT_STATES = 3
LABELS: dict[int, tuple[str, ...]] = {
    2: ("calm", "turbulent"),
    3: ("calm", "normal", "turbulent"),
    4: ("calm", "normal", "elevated", "turbulent"),
}
MIN_OBSERVATIONS = 250


class RegimeModel(BaseModel):
    """A fitted model. Everything needed to score new days, as plain numbers."""

    version: str = MODEL_VERSION
    n_states: int
    labels: tuple[str, ...]
    # Standardisation, fitted on the training window only.
    feature_mean: list[float]
    feature_std: list[float]
    # Parameters in standardised units, states ordered from calm to turbulent.
    start_prob: list[float]
    transition: list[list[float]]
    means: list[list[float]]
    covariances: list[list[list[float]]]
    train_start: date
    train_end: date
    n_train: int
    log_likelihood: float
    bic: float
    bic_by_states: dict[int, float]

    def standardise(self, observations: pd.DataFrame) -> np.ndarray:
        values = observations[list(FEATURES)].to_numpy(dtype=float)
        scaled: np.ndarray = (values - np.array(self.feature_mean)) / np.array(self.feature_std)
        return scaled


def _n_parameters(n_states: int, n_features: int) -> int:
    transitions = n_states * (n_states - 1)
    start = n_states - 1
    means = n_states * n_features
    covariances = n_states * n_features * (n_features + 1) // 2
    return transitions + start + means + covariances


def _volatility_start(x: np.ndarray, n_states: int) -> dict[str, np.ndarray]:
    """A sensible starting point: split the days into bands by volatility.

    Each band seeds one state, and states start out sticky. Without this the fit often
    settles on a poor solution where two states cover the same days.
    """
    order = np.argsort(x[:, VOLATILITY_FEATURE])
    bands = np.array_split(order, n_states)
    floor = 1e-3 * np.eye(x.shape[1])
    stay = 0.9
    transition = np.full((n_states, n_states), (1 - stay) / (n_states - 1))
    np.fill_diagonal(transition, stay)
    return {
        "means": np.array([x[band].mean(axis=0) for band in bands]),
        "covars": np.array([np.cov(x[band].T) + floor for band in bands]),
        "transmat": transition,
        "startprob": np.full(n_states, 1.0 / n_states),
    }


def _fit_once(x: np.ndarray, n_states: int, seed: int, *, banded: bool) -> GaussianHMM | None:
    model = GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=500,
        tol=1e-4,
        random_state=seed,
        init_params="" if banded else "stmc",
    )
    if banded:
        start = _volatility_start(x, n_states)
        model.startprob_ = start["startprob"]
        model.transmat_ = start["transmat"]
        model.means_ = start["means"]
        model.covars_ = start["covars"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x)
    except ValueError:
        return None
    if not np.all(np.isfinite(model.transmat_)) or not np.allclose(model.transmat_.sum(axis=1), 1):
        return None
    return model


def _best_of(
    x: np.ndarray, n_states: int, n_init: int, seed: int
) -> tuple[GaussianHMM, float] | None:
    """Fit from the volatility-band start and from `n_init - 1` random starts; keep the best."""
    best: tuple[GaussianHMM, float] | None = None
    for attempt in range(max(n_init, 1)):
        fitted = _fit_once(x, n_states, seed + attempt, banded=attempt == 0)
        if fitted is None:
            continue
        score = float(fitted.score(x))
        if np.isfinite(score) and (best is None or score > best[1]):
            best = (fitted, score)
    return best


def fit(
    observations: pd.DataFrame,
    *,
    n_states: int | None = DEFAULT_STATES,
    compare: tuple[int, ...] = (),
    n_init: int = 5,
    seed: int = 7,
) -> RegimeModel:
    """Fit the model on `observations` (columns `ret` and `log_rv`, one row per day).

    Uses `n_states` states. State counts in `compare` are fitted as well so their BIC
    can be reported beside the chosen one. With `n_states=None` the count with the
    lowest BIC among `compare` is used. Everything, including the scaling, is fitted on
    the rows given: pass only the training window.
    """
    candidates = tuple(sorted({*compare, *([n_states] if n_states is not None else [])}))
    if not candidates:
        raise ValueError("Give n_states, or state counts to compare")
    clean = observations[list(FEATURES)].dropna()
    if len(clean) < MIN_OBSERVATIONS:
        raise ValueError(f"Need at least {MIN_OBSERVATIONS} days to fit; got {len(clean)}")
    values = clean.to_numpy(dtype=float)
    mean, std = values.mean(axis=0), values.std(axis=0)
    x = (values - mean) / std

    fits: dict[int, tuple[GaussianHMM, float, float]] = {}
    for count in candidates:
        best = _best_of(x, count, n_init, seed)
        if best is None:
            continue
        model, score = best
        bic = -2.0 * score + _n_parameters(count, x.shape[1]) * np.log(len(x))
        fits[count] = (model, score, float(bic))
    if n_states is None:
        if not fits:
            raise ValueError("The model did not converge for any number of states")
        n_states = min(fits, key=lambda k: fits[k][2])
    elif n_states not in fits:
        raise ValueError(f"The model did not converge with {n_states} states")
    model, score, bic = fits[n_states]
    order = np.argsort(model.means_[:, VOLATILITY_FEATURE])  # calm first
    index = pd.DatetimeIndex(clean.index)
    return RegimeModel(
        n_states=n_states,
        labels=LABELS[n_states],
        feature_mean=mean.tolist(),
        feature_std=std.tolist(),
        start_prob=model.startprob_[order].tolist(),
        transition=model.transmat_[np.ix_(order, order)].tolist(),
        means=model.means_[order].tolist(),
        covariances=model.covars_[order].tolist(),
        train_start=index[0].date(),
        train_end=index[-1].date(),
        n_train=len(clean),
        log_likelihood=score,
        bic=bic,
        bic_by_states={k: v[2] for k, v in fits.items()},
    )


def _log_emissions(model: RegimeModel, x: np.ndarray) -> np.ndarray:
    """Log density of each observation under each state. Shape (days, states)."""
    out = np.empty((len(x), model.n_states))
    for k in range(model.n_states):
        mean = np.array(model.means[k])
        cov = np.array(model.covariances[k])
        diff = x - mean
        solved = np.linalg.solve(cov, diff.T).T
        _, logdet = np.linalg.slogdet(cov)
        out[:, k] = -0.5 * (np.sum(diff * solved, axis=1) + logdet + x.shape[1] * np.log(2 * np.pi))
    return out


def _forward(model: RegimeModel, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The forward algorithm.

    Returns the filtered log probabilities (days, states) and, for each day, the log
    density of that day's observation given all earlier days.
    """
    emissions = _log_emissions(model, x)
    with np.errstate(divide="ignore"):  # a zero probability is a valid -inf in log space
        log_transition = np.log(np.array(model.transition))
        prior = np.log(np.array(model.start_prob))
    filtered = np.empty_like(emissions)
    step = np.empty(len(x))
    for t in range(len(x)):
        joint = prior + emissions[t]
        step[t] = logsumexp(joint)
        filtered[t] = joint - step[t]
        prior = logsumexp(filtered[t][:, None] + log_transition, axis=0)
    return filtered, step


def filtered_probabilities(model: RegimeModel, observations: pd.DataFrame) -> pd.DataFrame:
    """Probability of each state on each day, using that day and earlier days only."""
    clean = observations[list(FEATURES)].dropna()
    filtered, _ = _forward(model, model.standardise(clean))
    return pd.DataFrame(np.exp(filtered), index=clean.index, columns=list(model.labels))


def predictive_log_density(model: RegimeModel, observations: pd.DataFrame) -> pd.Series:
    """Log density of each day's observation given all earlier days (one-step-ahead)."""
    clean = observations[list(FEATURES)].dropna()
    _, step = _forward(model, model.standardise(clean))
    # Report in the original units of the observations, not standardised units.
    return pd.Series(step - float(np.sum(np.log(model.feature_std))), index=clean.index)


def smoothed_probabilities(model: RegimeModel, observations: pd.DataFrame) -> pd.DataFrame:
    """Hindsight view: probability of each state on each day using the whole series.

    Uses later days. Never use this for a current state or in a backtest.
    """
    clean = observations[list(FEATURES)].dropna()
    x = model.standardise(clean)
    emissions = _log_emissions(model, x)
    with np.errstate(divide="ignore"):
        log_transition = np.log(np.array(model.transition))
    filtered, _ = _forward(model, x)
    backward = np.zeros_like(filtered)
    for t in range(len(x) - 2, -1, -1):
        backward[t] = logsumexp(log_transition + emissions[t + 1] + backward[t + 1], axis=1)
    joint = filtered + backward
    joint -= logsumexp(joint, axis=1, keepdims=True)
    return pd.DataFrame(np.exp(joint), index=clean.index, columns=list(model.labels))


def predict(model: RegimeModel, observations: pd.DataFrame) -> pd.Series:
    """The most probable state on each day, from filtered probabilities."""
    return filtered_probabilities(model, observations).idxmax(axis=1)


class StateSummary(BaseModel):
    label: str
    # Average length of an unbroken stay in this state, in days.
    typical_duration_days: float
    # Probability of each other state being next, once this one ends.
    next_states: dict[str, float]
    mean_daily_return: float
    typical_daily_volatility: float


def transition_summary(model: RegimeModel) -> list[StateSummary]:
    """Turn the transition matrix into "how long it lasts" and "what usually comes next"."""
    transition = np.array(model.transition)
    mean = np.array(model.means) * np.array(model.feature_std) + np.array(model.feature_mean)
    summaries = []
    for i, label in enumerate(model.labels):
        stay = transition[i, i]
        leaving = 1.0 - stay
        next_states = {
            other: float(transition[i, j] / leaving) if leaving > 0 else 0.0
            for j, other in enumerate(model.labels)
            if j != i
        }
        summaries.append(
            StateSummary(
                label=label,
                typical_duration_days=float(1.0 / leaving) if leaving > 0 else float("inf"),
                next_states=next_states,
                mean_daily_return=float(mean[i, 0]),
                typical_daily_volatility=float(np.exp(mean[i, VOLATILITY_FEATURE])),
            )
        )
    return summaries


def save(model: RegimeModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=1), encoding="utf-8", newline="\n")


def load(path: Path) -> RegimeModel:
    return RegimeModel.model_validate_json(path.read_text(encoding="utf-8"))


# --- evaluation ------------------------------------------------------------------------


class RegimeEvaluation(BaseModel):
    """Walk-forward results. Every number is out of sample."""

    n_days: int
    n_refits: int
    first_test_day: date
    last_test_day: date
    # Average one-step-ahead log density per day: higher is better.
    model_log_density: float
    baseline_log_density: float
    # Average realised volatility on the day after each predicted state.
    next_day_volatility: dict[str, float]
    days_per_state: dict[str, int]
    volatility_is_ordered: bool
    # Average length of an unbroken run of one predicted state, in days.
    average_run_length: float


def _baseline_log_density(train: pd.DataFrame, test: pd.DataFrame, window: int = 30) -> pd.Series:
    """Rule-based rival: three regimes from trailing 30-day volatility terciles.

    A day's regime comes from the average log volatility of the `window` days before it.
    The tercile cut-offs and one Gaussian per regime are fitted on the training window.
    """
    full = pd.concat([train, test])
    trailing = full["log_rv"].shift(1).rolling(window, min_periods=window).mean()
    cuts = trailing.loc[train.index].dropna().quantile([1 / 3, 2 / 3]).to_numpy()
    regime = pd.Series(np.digitize(trailing.to_numpy(), cuts), index=full.index).where(
        trailing.notna()
    )
    values = full[list(FEATURES)].to_numpy(dtype=float)
    density = pd.Series(np.nan, index=full.index)
    for k in range(3):
        rows = train.index[(regime.loc[train.index] == k).to_numpy()]
        if len(rows) < 10:
            continue
        sample = train.loc[rows, list(FEATURES)].to_numpy(dtype=float)
        mean, cov = sample.mean(axis=0), np.cov(sample.T)
        mask = (regime == k).to_numpy()
        diff = values[mask] - mean
        solved = np.linalg.solve(cov, diff.T).T
        _, logdet = np.linalg.slogdet(cov)
        density[mask] = -0.5 * (np.sum(diff * solved, axis=1) + logdet + 2 * np.log(2 * np.pi))
    return density.loc[test.index]


def evaluate(
    observations: pd.DataFrame,
    *,
    min_train: int = 500,
    step: int = 21,
    n_init: int = 3,
    seed: int = 7,
    n_states: int = DEFAULT_STATES,
) -> RegimeEvaluation:
    """Walk-forward evaluation with an expanding window.

    Every `step` days the model is refitted on all earlier days, then scores the next
    `step` days it has never seen.

    If `observations` has a column `rv` (the raw realised volatility of each day), the
    next-day volatility table uses it; otherwise it uses `exp(log_rv)`.
    """
    clean = observations.dropna(subset=list(FEATURES))
    if len(clean) < min_train + step:
        raise ValueError("Not enough history for a walk-forward evaluation")
    model_density: list[pd.Series] = []
    baseline_density: list[pd.Series] = []
    predicted: list[pd.Series] = []
    refits = 0
    for start in range(min_train, len(clean), step):
        train = clean.iloc[:start]
        test = clean.iloc[start : start + step]
        model = fit(train, n_states=n_states, n_init=n_init, seed=seed)
        refits += 1
        # Filter over history up to each test day with parameters fitted before it.
        seen = clean.iloc[: start + len(test)]
        model_density.append(predictive_log_density(model, seen).loc[test.index])
        predicted.append(predict(model, seen).loc[test.index])
        baseline_density.append(_baseline_log_density(train, test))

    states = pd.concat(predicted)
    density = pd.concat(model_density)
    baseline = pd.concat(baseline_density)
    both = density.notna() & baseline.notna()

    # Realised volatility on the day after each prediction.
    realised = clean["rv"] if "rv" in clean.columns else np.exp(clean["log_rv"])
    next_rv = realised.shift(-1).loc[states.index]
    by_state = next_rv.groupby(states).mean()
    labels = [label for label in LABELS[n_states] if label in by_state.index]
    ordered = by_state.loc[labels].to_numpy()
    runs = (states != states.shift()).cumsum()
    index = pd.DatetimeIndex(states.index)
    return RegimeEvaluation(
        n_days=len(states),
        n_refits=refits,
        first_test_day=index[0].date(),
        last_test_day=index[-1].date(),
        model_log_density=float(density[both].mean()),
        baseline_log_density=float(baseline[both].mean()),
        next_day_volatility={label: float(by_state[label]) for label in labels},
        days_per_state={label: int((states == label).sum()) for label in labels},
        volatility_is_ordered=bool(np.all(np.diff(ordered) > 0)) and len(labels) > 1,
        average_run_length=float(states.groupby(runs).size().mean()),
    )


def to_registry_metrics(model: RegimeModel, evaluation: RegimeEvaluation | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "n_states": model.n_states,
        "bic": model.bic,
        "bic_by_states": model.bic_by_states,
        "log_likelihood": model.log_likelihood,
        "states": [s.model_dump() for s in transition_summary(model)],
    }
    if evaluation is not None:
        metrics["walk_forward"] = evaluation.model_dump(mode="json")
    return metrics
