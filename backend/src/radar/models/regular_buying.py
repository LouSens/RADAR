"""Regular buying (dollar-cost averaging): where a plan of equal purchases might end up.

The same block bootstrap as the portfolio's range ahead: a simulated future joins runs
of real past days, taken for every asset at once. Along each future the plan buys a
fixed amount at a fixed interval and never sells. The same total put in all at once on
the first day is run through the very same futures, so the two can be compared fairly.

No lookahead: a simulation may only be given returns from days it could have known.
`backtest` checks past plans that way, each one simulated from the days before it began.
"""

import numpy as np
from pydantic import BaseModel

from radar.models import simulator
from radar.models.portfolio_simulation import BLOCK, Coverage, sample_days

MODEL_VERSION = "regular-buying-1"
DEFAULT_PATHS = 10_000
BACKTEST_PATHS = 1_000
# Sessions of joint history needed, and the longest plan that may be simulated.
MIN_DAYS = 250
MAX_SESSIONS = 504
QUANTILES = simulator.QUANTILES


def purchase_days(every: int, purchases: int) -> np.ndarray:
    """The session each purchase is made at the start of: 0, every, 2 x every, ..."""
    days: np.ndarray = np.arange(purchases) * every
    return days


def run_plan(
    daily: np.ndarray, weights: np.ndarray, amount: float, every: int, purchases: int
) -> tuple[np.ndarray, np.ndarray]:
    """Value at the end of each session for the plan and for the same total put in at once.

    `daily` holds log returns shaped (paths, sessions, assets); `weights` split each
    purchase among the assets and sum to one. Returns two arrays shaped (paths, sessions).
    """
    n_paths, sessions, _ = daily.shape
    buying = set(purchase_days(every, purchases).tolist())
    held = np.zeros((n_paths, len(weights)))
    at_once = np.tile(amount * purchases * weights, (n_paths, 1))
    plan = np.empty((n_paths, sessions))
    lump = np.empty((n_paths, sessions))
    for day in range(sessions):
        if day in buying:
            held = held + amount * weights
        growth = np.exp(daily[:, day, :])
        held = held * growth
        at_once = at_once * growth
        plan[:, day] = held.sum(axis=1)
        lump[:, day] = at_once.sum(axis=1)
    return plan, lump


def simulate(
    returns: np.ndarray,
    weights: np.ndarray,
    amount: float,
    every: int,
    purchases: int,
    n_paths: int = DEFAULT_PATHS,
    block: int = BLOCK,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """The plan and the all-at-once alternative through bootstrapped futures.

    `returns` holds past daily log returns, one row per day and one column per asset.
    The plan runs for `every * purchases` sessions: the last purchase is held for one
    full interval.
    """
    sessions = every * purchases
    rng = np.random.default_rng(seed)
    days = sample_days(len(returns), sessions, n_paths, block, rng)
    return run_plan(returns[days], weights, amount, every, purchases)


class Spread(BaseModel):
    """Where one way of investing ended up, in money."""

    quantiles: dict[str, float]
    # Share of futures that ended below the total paid in.
    below_paid_in: float


def spread(final: np.ndarray, paid_in: float) -> Spread:
    return Spread(
        quantiles={f"{q:g}": float(np.quantile(final, q)) for q in QUANTILES},
        below_paid_in=float((final < paid_in).mean()),
    )


class PastPlan(BaseModel):
    """One plan simulated in the past from earlier days only, and how it then went."""

    origin: int
    # Final value as a multiple of the total paid in.
    realised: float
    bounds: dict[str, tuple[float, float]]


def backtest(
    returns: np.ndarray,
    weights: np.ndarray,
    every: int,
    purchases: int,
    *,
    min_days: int = MIN_DAYS,
    n_paths: int = BACKTEST_PATHS,
    block: int = BLOCK,
    seed: int = 0,
) -> list[PastPlan]:
    """Simulate the plan at each past start from the days before it, then run the real
    plan through the days that followed. Starts are a full plan apart, so no two share
    a day."""
    sessions = every * purchases
    records = []
    for origin in range(min_days, len(returns) - sessions + 1, sessions):
        plan, _ = simulate(
            returns[:origin], weights, 1.0, every, purchases, n_paths, block, seed + origin
        )
        final = plan[:, -1] / purchases
        actual, _ = run_plan(
            returns[origin : origin + sessions][None, :, :], weights, 1.0, every, purchases
        )
        records.append(
            PastPlan(
                origin=origin,
                realised=float(actual[0, -1] / purchases),
                bounds={
                    f"{level:g}": simulator.interval_bounds(final, level)
                    for level in simulator.INTERVALS
                },
            )
        )
    return records


def coverage(records: list[PastPlan]) -> list[Coverage]:
    result = []
    for level in simulator.INTERVALS:
        key = f"{level:g}"
        inside = sum(1 for r in records if r.bounds[key][0] <= r.realised <= r.bounds[key][1])
        result.append(Coverage(level=level, n=len(records), inside=inside))
    return result


class Result(BaseModel):
    model_version: str
    n_paths: int
    block: int
    # Past sessions the futures were drawn from, and how many separate stretches of the
    # plan's length fit in them: the honest size of the evidence.
    n_days: int
    separate_periods: int
    amount: float
    every: int
    purchases: int
    sessions: int
    paid_in: float
    plan: Spread
    at_once: Spread
    # Share of futures in which the plan ended with more than putting it all in at once.
    plan_ahead: float
    # Value quantiles at the end of each session, and the total paid in by then.
    fan: dict[str, list[float]]
    paid_in_path: list[float]
    coverage: list[Coverage]


def run(
    returns: np.ndarray,
    weights: np.ndarray,
    amount: float,
    every: int,
    purchases: int,
    *,
    n_paths: int = DEFAULT_PATHS,
    block: int = BLOCK,
    seed: int = 0,
) -> Result:
    """The full result for one plan. Raises ValueError when it cannot be simulated."""
    sessions = every * purchases
    if len(returns) < MIN_DAYS:
        raise ValueError(
            f"These assets share {len(returns)} days of prices; {MIN_DAYS} are needed."
        )
    if sessions > MAX_SESSIONS:
        raise ValueError(f"The plan is longer than {MAX_SESSIONS} trading days.")
    plan, lump = simulate(returns, weights, amount, every, purchases, n_paths, block, seed)
    paid_in = amount * purchases
    paid_path = amount * (np.arange(sessions) // every + 1)
    return Result(
        model_version=MODEL_VERSION,
        n_paths=n_paths,
        block=block,
        n_days=len(returns),
        separate_periods=len(returns) // sessions,
        amount=amount,
        every=every,
        purchases=purchases,
        sessions=sessions,
        paid_in=paid_in,
        plan=spread(plan[:, -1], paid_in),
        at_once=spread(lump[:, -1], paid_in),
        plan_ahead=float((plan[:, -1] > lump[:, -1]).mean()),
        fan={f"{q:g}": [float(v) for v in np.quantile(plan, q, axis=0)] for q in QUANTILES},
        paid_in_path=[float(v) for v in paid_path],
        coverage=coverage(backtest(returns, weights, every, purchases, block=block, seed=seed)),
    )
