"""Why it moved: the split sums to the move, nothing looks ahead, and the link to the
wider market is judged honestly (decision 095)."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import moves
from radar.pipelines.moves import reference_for
from radar.universe import Universe

DAYS = pd.date_range("2023-01-02", periods=700, freq="D")


def market(seed: int = 1) -> pd.Series:
    return pd.Series(np.random.default_rng(seed).normal(0, 0.03, len(DAYS)), index=DAYS)


def follower(of: pd.Series, slope: float, own: float, seed: int = 2) -> pd.Series:
    """A holding that takes `slope` of the market's move and adds noise of its own."""
    noise = np.random.default_rng(seed).normal(0, own, len(of))
    return of * slope + noise


def test_the_parts_sum_to_the_move() -> None:
    wider = market()
    parts = moves.split(follower(wider, 1.3, 0.01), wider)
    assert len(parts) == len(DAYS) - moves.SENSITIVITY_WINDOW
    assert np.allclose(parts["market"] + parts["own"], parts["move"])


def test_a_day_is_not_part_of_its_own_yardstick() -> None:
    wider = market()
    own = follower(wider, 1.3, 0.01)
    day = DAYS[400]
    before = moves.split(own, wider).loc[day, "sensitivity"]
    # Change the day itself and everything after it, in both series.
    own_changed, wider_changed = own.copy(), wider.copy()
    own_changed.loc[day:] = 0.5
    wider_changed.loc[day:] = -0.5
    after = moves.split(own_changed, wider_changed).loc[day, "sensitivity"]
    assert after == pytest.approx(before)


def test_the_size_rank_uses_only_earlier_days() -> None:
    returns = market()
    day = DAYS[300]
    before = moves.size_rank(returns).loc[day]
    changed = returns.copy()
    changed.iloc[301:] = 9.0
    assert moves.size_rank(changed).loc[day] == before
    # The largest move so far ranks above every day before it.
    spiked = returns.copy()
    spiked.iloc[300] = 0.9
    assert moves.size_rank(spiked).loc[day] == 1.0
    # Too few earlier days: no ranking.
    assert np.isnan(moves.size_rank(returns).iloc[moves.MIN_RANK_SESSIONS - 1])


def test_usual_size_leaves_the_day_out() -> None:
    returns = market()
    spiked = returns.copy()
    spiked.iloc[100] = 5.0
    assert moves.usual_size(spiked).iloc[100] == pytest.approx(moves.usual_size(returns).iloc[100])


def test_a_planted_link_is_found_and_passes() -> None:
    wider = market()
    judged = moves.evidence(follower(wider, 1.3, 0.012), wider)
    assert judged.passed
    assert judged.reason is None
    assert judged.whole is not None
    assert judged.whole.share_explained > 0.8
    assert judged.whole.sign_agreement is not None
    assert judged.whole.sign_agreement > 0.95
    assert len(judged.halves) == 2


def test_no_link_does_not_pass() -> None:
    judged = moves.evidence(market(seed=5), market(seed=6))
    assert not judged.passed
    assert judged.whole is not None
    assert judged.whole.share_explained < 0.1
    assert judged.reason == "the wider market explains under half of its moves"


def test_a_weak_link_does_not_pass() -> None:
    # The market is there, but most of each move is the holding's own.
    wider = market()
    judged = moves.evidence(follower(wider, 0.5, 0.03), wider)
    assert not judged.passed
    assert judged.whole is not None
    assert 0.0 < judged.whole.share_explained < moves.SHARE_BAR


def test_a_link_in_one_half_only_does_not_pass() -> None:
    wider = market()
    own = follower(wider, 1.3, 0.004)
    middle = len(DAYS) // 2
    own.iloc[middle:] = np.random.default_rng(9).normal(0, 0.02, len(DAYS) - middle)
    judged = moves.evidence(own, wider)
    assert not judged.passed
    assert judged.halves[0].share_explained > moves.SHARE_BAR > judged.halves[1].share_explained


def test_too_short_a_record_is_not_judged() -> None:
    wider = market().iloc[:200]
    judged = moves.evidence(follower(wider, 1.3, 0.01), wider)
    assert not judged.passed
    assert judged.whole is None
    assert judged.reason is not None
    assert "150 are needed" in judged.reason


def test_the_top_of_the_ranking_comes_up_as_often_as_it_says() -> None:
    share, n = moves.top_share(market(seed=3))
    assert n == len(DAYS) - moves.MIN_RANK_SESSIONS
    assert moves.TOP_RANGE[0] <= share <= moves.TOP_RANGE[1]


def _asset(symbol: str, kind: str, role: str | None = None) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": symbol,
        "name": symbol,
        "asset_class": kind,
        "bars_symbol": symbol,
        "history_start": "2022-01-01",
    }
    if role:
        base |= {
            "kind": role,
            "is_primary": True,
            "news_symbols": [symbol.replace("/", "")],
            "news_start": "2022-01-01",
        }
    return base


def test_each_holding_is_set_against_its_own_wider_market() -> None:
    universe = Universe.model_validate(
        {
            "crypto_location": "us-1",
            "timeframes": {"crypto": ["1Hour", "1Day"], "stock": ["1Day"]},
            "assets": [
                _asset("BTC/USD", "crypto", "bitcoin"),
                _asset("PAXG/USD", "crypto", "gold"),
                _asset("SPY", "stock", "stocks"),
                _asset("ETH/USD", "crypto"),
                _asset("PURR", "stock"),
            ],
        }
    )
    against = {a.symbol: reference_for(universe, a) for a in universe.assets}
    assert against["ETH/USD"] is not None
    assert against["ETH/USD"].symbol == "BTC/USD"
    assert against["PURR"] is not None
    assert against["PURR"].symbol == "SPY"
    # The three reference markets are not measured against anything.
    assert against["BTC/USD"] is None
    assert against["PAXG/USD"] is None
    assert against["SPY"] is None
