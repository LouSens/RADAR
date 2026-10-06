"""Portfolio risk (spec F6 and the portfolio part of F10). Pure functions.

Everything works on the mixed panel: one row per New York session, every asset priced
at that session's close, so a weekend's crypto move sits in Monday's row beside the
stock move it belongs with.

Three questions are answered for a set of weights:

- X-ray: how much does the mix swing, and which holdings does that come from?
- Loss limits: Value at Risk and expected shortfall for the mix, backtested walk-forward.
- Stress: what would this mix have done through named past episodes?

No lookahead. A loss limit for day `t` uses returns up to `t` only; the recent-swings
estimate that scales it is an exponentially weighted average of past squared returns.
The X-ray describes the stored history as a whole and is not a forecast.
"""

from datetime import date

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sklearn.covariance import LedoitWolf

from radar.models import tail_risk

MODEL_VERSION = "portfolio-risk-1"
# Fewest shared sessions before anything is estimated (spec F6).
MIN_HISTORY = 250
# A newer holding (a recent listing, say) is estimated on what history it has, down to
# this many sessions. Below it there is too little to say anything.
MIN_YOUNG = 30
# Days of the calendar to sessions, as everywhere else on the mixed panel.
HORIZONS: dict[int, int] = {1: 1, 7: 5}
# Weight of yesterday's estimate in the recent-swings average (the RiskMetrics value).
DECAY = 0.94
WARM_UP = 20


class NotEnoughHistoryError(ValueError):
    """The holdings share too few sessions of price history to estimate anything."""


# --- X-ray -----------------------------------------------------------------------------


def covariance(returns: pd.DataFrame) -> np.ndarray:
    """Covariance of daily returns with Ledoit-Wolf shrinkage, on sessions every asset has."""
    complete = returns.dropna()
    if len(complete) < MIN_HISTORY:
        raise NotEnoughHistoryError(
            f"Only {len(complete)} shared sessions; {MIN_HISTORY} are needed."
        )
    fitted = LedoitWolf().fit(complete.to_numpy(dtype=float))
    return np.asarray(fitted.covariance_, dtype=float)


def covariance_with_young(established: pd.DataFrame, young: pd.DataFrame) -> np.ndarray:
    """Covariance of established holdings and newer ones together, established first.

    The established block is the shrunk estimate on their long shared history. A newer
    holding's own swings, and how it moves with each other holding, are measured on the
    sessions it has. The pieces are then made into one consistent matrix. Two holdings
    with fewer than `MIN_YOUNG` sessions in common are taken as unrelated.
    """
    base = covariance(established)
    k = base.shape[0]
    frame = pd.concat([established, young], axis=1)
    n = frame.shape[1]
    spread = np.concatenate(
        [np.sqrt(np.diag(base)), [float(young[c].dropna().std()) for c in young.columns]]
    )
    corr = np.eye(n)
    corr[:k, :k] = base / np.outer(spread[:k], spread[:k])
    for j in range(k, n):
        for i in range(j):
            pair = frame.iloc[:, [i, j]].dropna()
            value = (
                float(np.corrcoef(pair.iloc[:, 0], pair.iloc[:, 1])[0, 1])
                if len(pair) >= MIN_YOUNG
                else 0.0
            )
            corr[i, j] = corr[j, i] = 0.0 if np.isnan(value) else value
    # Pieces measured on different windows need not fit together: take the nearest
    # matrix that is a valid set of correlations.
    values, vectors = np.linalg.eigh(corr)
    fixed = (vectors * np.clip(values, 1e-8, None)) @ vectors.T
    scale = np.sqrt(np.diag(fixed))
    corr = fixed / np.outer(scale, scale)
    return np.asarray(np.outer(spread, spread) * corr, dtype=float)


def risk_shares(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Each holding's share of the portfolio's variance. The shares sum to one."""
    marginal = cov @ weights
    total = float(weights @ marginal)
    if total <= 0:
        raise ValueError("The portfolio has no variance to share out.")
    return np.asarray(weights * marginal / total, dtype=float)


def mix_returns(returns: pd.DataFrame, weights: np.ndarray) -> pd.Series:
    """Daily log return of a mix held at fixed weights, on sessions every asset has."""
    complete = returns.dropna()
    simple = np.expm1(complete.to_numpy(dtype=float)) @ weights
    return pd.Series(np.log1p(simple), index=complete.index)


class Fall(BaseModel):
    depth: float  # negative fraction
    peak_day: date
    trough_day: date


def deepest_fall(log_returns: pd.Series) -> Fall:
    """The largest peak-to-trough fall of a return series."""
    level = np.exp(np.concatenate([[0.0], np.cumsum(log_returns.to_numpy(dtype=float))]))
    peak = np.maximum.accumulate(level)
    depth = level / peak - 1.0
    trough = int(np.argmin(depth))
    top = int(np.argmax(level[: trough + 1]))
    days = pd.DatetimeIndex(log_returns.index)
    # Position 0 is the level before the first return.
    return Fall(
        depth=float(depth[trough]),
        peak_day=days[max(top - 1, 0)].date(),
        trough_day=days[max(trough - 1, 0)].date(),
    )


class HoldingRisk(BaseModel):
    symbol: str
    weight: float
    # Standard deviation of the holding's own daily return.
    daily_volatility: float
    # Its share of the portfolio's variance; all shares sum to one.
    risk_share: float


class Xray(BaseModel):
    holdings: list[HoldingRisk]
    # Standard deviation of the mix's daily return.
    daily_volatility: float
    # What it would be if the holdings always moved together: the weighted average.
    undiversified_volatility: float
    symbols: list[str]
    correlation: list[list[float]]
    n_days: int
    first_day: date
    last_day: date
    deepest_fall: Fall
    # Daily swings of the established holdings alone, at their weights. The loss
    # limits are measured on these and scaled up for newer holdings.
    established_volatility: float = 0.0


def xray(
    returns: pd.DataFrame,
    weights: np.ndarray,
    young: pd.DataFrame | None = None,
    young_weights: np.ndarray | None = None,
) -> Xray:
    """Where the mix's swings come from. `returns` has one column per established
    holding; `young` one per newer holding, which is estimated on the history it has.
    The deepest fall is for the established holdings, the only ones with a long record.
    """
    complete = returns.dropna()
    established_weights = weights
    if young is not None and young_weights is not None and young.shape[1] > 0:
        cov = covariance_with_young(returns, young)
        base = cov[: len(weights), : len(weights)]
        weights = np.concatenate([weights, young_weights])
        columns = [*returns.columns, *young.columns]
    else:
        cov = covariance(returns)
        base = cov
        columns = list(returns.columns)
    spread = np.sqrt(np.diag(cov))
    shares = risk_shares(weights, cov)
    correlation = cov / np.outer(spread, spread)
    days = pd.DatetimeIndex(complete.index)
    return Xray(
        holdings=[
            HoldingRisk(
                symbol=str(symbol),
                weight=float(weights[i]),
                daily_volatility=float(spread[i]),
                risk_share=float(shares[i]),
            )
            for i, symbol in enumerate(columns)
        ],
        daily_volatility=float(np.sqrt(weights @ cov @ weights)),
        undiversified_volatility=float(weights @ spread),
        symbols=[str(c) for c in columns],
        correlation=[[float(v) for v in row] for row in correlation],
        n_days=len(complete),
        first_day=days[0].date(),
        last_day=days[-1].date(),
        deepest_fall=deepest_fall(mix_returns(returns, established_weights)),
        established_volatility=float(np.sqrt(established_weights @ base @ established_weights)),
    )


# --- risk level ------------------------------------------------------------------------

# The mix's daily swings as a multiple of the US stock market's, and the word for it.
RISK_BANDS: tuple[tuple[float, str], ...] = (
    (0.5, "low"),
    (1.0, "moderate"),
    (2.0, "high"),
)


class RiskLevel(BaseModel):
    """How much the mix swings, set against things an investor already knows."""

    # "low", "moderate", "high", or "very high".
    label: str
    # Daily swings of the mix divided by those of US stocks over the same sessions.
    ratio: float
    # The same multiple for other reference points, lowest first. Cash is zero.
    references: dict[str, float]


def risk_level(mix: pd.Series, references: pd.DataFrame, stocks: str) -> RiskLevel | None:
    """Where the mix sits between cash and the riskiest reference.

    `references` holds daily returns of reference markets, one of which is `stocks`.
    Everything is measured on the sessions the mix has.
    """
    both = pd.concat([mix.rename("mix"), references], axis=1).dropna()
    if len(both) < MIN_HISTORY or stocks not in both:
        return None
    spread = both.std()
    base = float(spread[stocks])
    if base <= 0:
        return None
    ratio = float(spread["mix"]) / base
    label = next((name for limit, name in RISK_BANDS if ratio < limit), "very high")
    return RiskLevel(
        label=label,
        ratio=ratio,
        references={str(c): float(spread[c]) / base for c in references.columns},
    )


def scale_level(level: RiskLevel, factor: float) -> RiskLevel:
    """The same reading with the mix's swings multiplied by `factor`."""
    ratio = level.ratio * factor
    label = next((name for limit, name in RISK_BANDS if ratio < limit), "very high")
    return level.model_copy(update={"ratio": ratio, "label": label})


def scale_limits(limits: list["LimitHorizon"], factor: float) -> list["LimitHorizon"]:
    """Loss limits measured on part of the mix, scaled to the swings of all of it.

    The backtest stays that of the part it was measured on.
    """
    return [
        horizon.model_copy(
            update={
                "levels": [
                    level.model_copy(
                        update={
                            "methods": [
                                m.model_copy(
                                    update={
                                        "var": min(m.var * factor, 0.99),
                                        "expected_shortfall": min(
                                            m.expected_shortfall * factor, 0.99
                                        ),
                                    }
                                )
                                for m in level.methods
                            ]
                        }
                    )
                    for level in horizon.levels
                ]
            }
        )
        for horizon in limits
    ]


# --- loss limits -----------------------------------------------------------------------


def recent_volatility(returns: np.ndarray, decay: float = DECAY) -> np.ndarray:
    """Exponentially weighted daily volatility known at the end of each day.

    Entry `t` uses returns up to and including `t`. The first `WARM_UP` entries are NaN.
    """
    out = np.full(len(returns), np.nan)
    variance = float("nan")
    for t, value in enumerate(returns):
        squared = float(value) ** 2
        variance = squared if np.isnan(variance) else decay * variance + (1 - decay) * squared
        if t >= WARM_UP:
            out[t] = np.sqrt(variance)
    return out


class Limit(BaseModel):
    """One method's current limit at one level, and how its past limits held."""

    method: str
    var: float
    expected_shortfall: float
    backtest: tail_risk.Backtest


class LimitLevel(BaseModel):
    level: float
    methods: list[Limit]


class LimitHorizon(BaseModel):
    horizon_days: int
    steps: int
    shown: str
    levels: list[LimitLevel]


def loss_limits(
    mix: pd.Series, *, window: int = tail_risk.WINDOW, min_window: int = tail_risk.MIN_WINDOW
) -> list[LimitHorizon]:
    """Current VaR and expected shortfall of the mix, with a walk-forward backtest.

    Two methods: `historical` (the past returns of this mix as they were) and `filtered`
    (the same returns rescaled to how much the mix has been swinging lately). The method
    shown for a horizon is the one whose past limits held closest to their stated rates.
    """
    values = mix.to_numpy(dtype=float)
    index = pd.DatetimeIndex(mix.index)
    inputs = tail_risk.RiskInputs(
        returns=values,
        volatility_forecast=recent_volatility(values),
        simulated_days=np.array([], dtype=int),
        simulated=np.empty((0, 0)),
    )
    estimates = {
        days: tail_risk.estimate(inputs, steps, window=window, min_window=min_window)
        for days, steps in HORIZONS.items()
    }
    tested = {days: tail_risk.backtest(est, index) for days, est in estimates.items()}
    # Every limit of the portfolio is one family when judging reliability.
    flat = tail_risk.correct_family([row for rows in tested.values() for row in rows])
    position = 0
    out: list[LimitHorizon] = []
    for days, steps in HORIZONS.items():
        rows = flat[position : position + len(tested[days])]
        position += len(tested[days])
        shown = tail_risk.choose(rows)
        if shown is None:
            continue
        est = estimates[days]
        levels = []
        for level in tail_risk.LEVELS:
            methods = [
                Limit(
                    method=row.method,
                    var=float(est.var[(row.method, level)][-1]),
                    expected_shortfall=float(est.es[(row.method, level)][-1]),
                    backtest=row,
                )
                for row in rows
                if row.level == level and not np.isnan(est.var[(row.method, level)][-1])
            ]
            levels.append(LimitLevel(level=level, methods=methods))
        out.append(LimitHorizon(horizon_days=days, steps=steps, shown=shown, levels=levels))
    return out


# --- stress scenarios ------------------------------------------------------------------


class Episode(BaseModel):
    name: str
    start: date
    end: date


class StressPart(BaseModel):
    symbol: str
    # The holding's own change over the episode.
    change: float
    # Its part of the portfolio's change: weight at the start times its change.
    contribution: float


class StressResult(BaseModel):
    name: str
    start: date
    end: date
    # False when no holding has prices for the episode.
    available: bool
    # Change in the value of the covered holdings from first day to last.
    change: float | None = None
    deepest_fall: float | None = None
    worst_day: date | None = None
    worst_day_change: float | None = None
    parts: list[StressPart] = []
    # Holdings with no prices for the episode. Nothing is substituted for them.
    missing: list[str] = []
    # Share of today's portfolio value the covered holdings make up.
    covered_weight: float = 0.0


def stress(
    prices: pd.DataFrame, weights: np.ndarray, episodes: list[Episode]
) -> list[StressResult]:
    """Replay today's mix through each episode.

    `prices` has one column per held asset, indexed by session close. A holding counts
    as covered when it has a price on the first and last session of the episode. The
    covered holdings keep their proportions to each other; the missing ones are named.
    """
    sessions = pd.DatetimeIndex(prices.index).tz_convert("America/New_York").date
    results: list[StressResult] = []
    for episode in episodes:
        inside = (sessions >= episode.start) & (sessions <= episode.end)
        window = prices.loc[inside]
        ends = window.iloc[[0, -1]].to_numpy(dtype=float) if len(window) >= 2 else None
        covered = (
            [] if ends is None else [int(i) for i in np.flatnonzero(~np.isnan(ends).any(axis=0))]
        )
        missing = [str(c) for i, c in enumerate(prices.columns) if i not in covered]
        base = StressResult(
            name=episode.name, start=episode.start, end=episode.end, available=False
        )
        if not covered:
            results.append(base.model_copy(update={"missing": missing}))
            continue
        covered_weight = float(weights[covered].sum())
        share = weights[covered] / covered_weight
        paths = window.iloc[:, covered].ffill()
        relative = paths.to_numpy(dtype=float) / paths.iloc[0].to_numpy(dtype=float)
        value = relative @ share
        daily = value[1:] / value[:-1] - 1.0
        worst = int(np.argmin(daily))
        own = relative[-1] - 1.0
        days = sessions[inside]
        results.append(
            base.model_copy(
                update={
                    "available": True,
                    "change": float(value[-1] - 1.0),
                    "deepest_fall": float((value / np.maximum.accumulate(value) - 1.0).min()),
                    "worst_day": days[worst + 1],
                    "worst_day_change": float(daily[worst]),
                    "parts": [
                        StressPart(
                            symbol=str(prices.columns[i]),
                            change=float(own[k]),
                            contribution=float(share[k] * own[k]),
                        )
                        for k, i in enumerate(covered)
                    ],
                    "missing": missing,
                    "covered_weight": covered_weight,
                }
            )
        )
    return results
