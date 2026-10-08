"""Why it moved (spec F13): a day's move of a holding, split into what its wider market
did and what was its own, with how unusual the day's size was.

This is arithmetic on known prices, not a forecast. The market part is the holding's
sensitivity to its wider market, measured on the sessions before the day, times the
market's move on the day. The holding's own part is the rest, so the two always sum to
the move.

No lookahead. Everything said about day `t` uses the sensitivity and the ranking window
of the sessions before `t`; day `t` itself is never in its own yardstick.

Whether the market part means anything for a holding is measured, not assumed
(`evidence`), against the bars written down in `docs/DECISIONS.md` 095.
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

# Sessions before the day that the sensitivity is measured on.
SENSITIVITY_WINDOW = 90
# Sessions before the day whose spread is the holding's "usual size".
USUAL_WINDOW = 30
# Sessions before the day that its size is ranked among, and the fewest that will do.
RANK_WINDOW = 250
MIN_RANK_SESSIONS = 60
# A day counts as large when it is this many usual sizes or more.
LARGE = 2.0
# Shared sessions needed before the link to the wider market is judged at all.
MIN_SESSIONS = 150

# The bars of decision 095.
SHARE_BAR = 0.50
SIGN_BAR = 0.80
MIN_LARGE_DAYS = 20
TOP = 0.05
TOP_RANGE = (0.03, 0.08)


def split(own: pd.Series, market: pd.Series, window: int = SENSITIVITY_WINDOW) -> pd.DataFrame:
    """Each day's return of a holding as a market part and its own part.

    `own` and `market` are daily returns indexed by session. The result is indexed by the
    sessions both have and holds `move`, `sensitivity`, `market` and `own`. Days without
    a full window before them have no split and are left out.
    """
    both = pd.concat([own.rename("move"), market.rename("reference")], axis=1).dropna()
    # The slope of the holding on the market over the window, then moved one session on,
    # so that a day is never part of what it is measured by.
    covariance = both["move"].rolling(window).cov(both["reference"])
    variance = both["reference"].rolling(window).var()
    sensitivity = (covariance / variance).shift(1)
    out = pd.DataFrame({"move": both["move"], "sensitivity": sensitivity})
    out["market"] = sensitivity * both["reference"]
    out["own"] = out["move"] - out["market"]
    return out.dropna()


def usual_size(returns: pd.Series, window: int = USUAL_WINDOW) -> pd.Series:
    """The spread of the sessions before each day: what a usual day has been lately."""
    return returns.rolling(window).std().shift(1)


def size_rank(
    returns: pd.Series, window: int = RANK_WINDOW, min_sessions: int = MIN_RANK_SESSIONS
) -> pd.Series:
    """How each day's size ranks among the sessions before it, from 0 to 1: 0.97 is
    "larger than 97 of the last 100 days". A count, with no model in it."""
    size = returns.abs().to_numpy(dtype=float)
    rank = np.full(size.shape, np.nan)
    for i in range(len(size)):
        earlier = size[max(0, i - window) : i]
        earlier = earlier[~np.isnan(earlier)]
        if len(earlier) >= min_sessions and not np.isnan(size[i]):
            rank[i] = float((earlier < size[i]).mean())
    return pd.Series(rank, index=returns.index)


class Slice(BaseModel):
    """The link to the wider market over one stretch of days."""

    n_days: int
    # One less the squared error of the market part over the squared size of the moves.
    share_explained: float
    n_large: int
    # Of the large days, the share on which the market part had the move's sign.
    sign_agreement: float | None


class Evidence(BaseModel):
    """Whether a holding's market part may be shown, and what that rests on."""

    n_days: int
    first_day: str | None
    last_day: str | None
    whole: Slice | None
    halves: list[Slice]
    passed: bool
    # Why not, in plain words, when it did not pass.
    reason: str | None


def _slice(parts: pd.DataFrame, usual: pd.Series) -> Slice:
    move = parts["move"].to_numpy(dtype=float)
    market = parts["market"].to_numpy(dtype=float)
    total = float((move**2).sum())
    share = float("nan") if total == 0 else 1.0 - float(((move - market) ** 2).sum()) / total
    size = usual.reindex(parts.index).to_numpy(dtype=float)
    large = np.abs(move) >= LARGE * size
    n_large = int(large.sum())
    agree = float((np.sign(move[large]) == np.sign(market[large])).mean()) if n_large else None
    return Slice(n_days=len(parts), share_explained=share, n_large=n_large, sign_agreement=agree)


def _clears(piece: Slice, min_large: int) -> bool:
    return (
        piece.share_explained >= SHARE_BAR
        and piece.sign_agreement is not None
        and piece.n_large >= min_large
        and piece.sign_agreement >= SIGN_BAR
    )


def evidence(own: pd.Series, market: pd.Series) -> Evidence:
    """Judge the market part of a holding against the bars of decision 095: at least half
    of the moves explained on unseen days, and the right sign on at least four large days
    in five, overall and in each half of the record."""
    parts = split(own, market)
    if len(parts) < MIN_SESSIONS:
        return Evidence(
            n_days=len(parts),
            first_day=None,
            last_day=None,
            whole=None,
            halves=[],
            passed=False,
            reason=f"only {len(parts)} days to judge it on; {MIN_SESSIONS} are needed",
        )
    usual = usual_size(parts["move"])
    judged = parts[usual.reindex(parts.index).notna()]
    whole = _slice(judged, usual)
    middle = len(judged) // 2
    halves = [_slice(judged.iloc[:middle], usual), _slice(judged.iloc[middle:], usual)]
    # The count of large days is asked of the whole record; each half needs half of it.
    passed = _clears(whole, MIN_LARGE_DAYS) and all(_clears(h, MIN_LARGE_DAYS // 2) for h in halves)
    reason = None
    if not passed:
        if whole.share_explained < SHARE_BAR:
            reason = "the wider market explains under half of its moves"
        elif whole.n_large < MIN_LARGE_DAYS:
            reason = "too few large days to judge it on"
        elif whole.sign_agreement is not None and whole.sign_agreement < SIGN_BAR:
            reason = "on its large days it often went the other way from the wider market"
        else:
            reason = "the link held in only one half of its record"
    return Evidence(
        n_days=len(judged),
        first_day=str(judged.index[0])[:10],
        last_day=str(judged.index[-1])[:10],
        whole=whole,
        halves=halves,
        passed=passed,
        reason=reason,
    )


def top_share(returns: pd.Series, top: float = TOP) -> tuple[float, int]:
    """How often a day ranks in the top `top` of the sessions before it, and on how many
    days that could be judged. If the ranking is honest this is close to `top`."""
    rank = size_rank(returns).dropna()
    if rank.empty:
        return float("nan"), 0
    return float((rank >= 1.0 - top).mean()), len(rank)
