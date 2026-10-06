"""Risk levels, other mixes, and the gap to a chosen target."""

import numpy as np
import pandas as pd
import pytest

from radar.features.panels import MixedPanel
from radar.models import allocation
from radar.models.holdings import Holding
from radar.pipelines import portfolio as job
from radar.pipelines import rebalance
from radar.universe import Universe


def asset(symbol: str, primary: bool = False) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": symbol,
        "name": symbol.title(),
        "asset_class": "stock",
        "bars_symbol": symbol,
        "history_start": "2021-01-04",
    }
    if primary:
        base |= {"is_primary": True, "news_symbols": [symbol], "news_start": "2021-01-04"}
    return base


UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Day"], "stock": ["1Day"]},
        "assets": [asset("SPY", primary=True), asset("WILD"), asset("CALM"), asset("NEW")],
    }
)
DAYS = 800


def panel() -> MixedPanel:
    """Stocks swing 1% a day. WILD swings three times that, CALM a third. NEW is a
    recent listing. The last 40 sessions are twice as rough as the rest for WILD."""
    rng = np.random.default_rng(21)
    closes = pd.bdate_range("2021-01-04", periods=DAYS, tz="UTC") + pd.Timedelta(hours=21)
    wild = rng.normal(0, 0.03, DAYS)
    wild[-40:] *= 2
    returns = pd.DataFrame(
        {
            "SPY": rng.normal(0, 0.01, DAYS),
            "WILD": wild,
            "CALM": rng.normal(0, 0.0033, DAYS),
            "NEW": rng.normal(0, 0.02, DAYS),
        },
        index=closes,
    )
    returns.loc[closes[: DAYS - 120], "NEW"] = np.nan
    levels = pd.DataFrame(100 * np.exp(returns.fillna(0).cumsum()), index=closes)
    return MixedPanel(
        prices=levels.where(returns.notna()),
        returns=returns,
        filled=pd.DataFrame(False, index=closes, columns=returns.columns),
        sessions=pd.DatetimeIndex(closes.tz_localize(None).normalize()),
    )


def plan_for(
    holdings: list[Holding],
    target: rebalance.Target | None = None,
    states: dict[str, str] | None = None,
) -> tuple[job.Analysis, rebalance.Plan]:
    data = panel()
    analysis = job.analyse(holdings, data, UNIVERSE)
    assert analysis.risk_level is not None
    plan = rebalance.build(
        analysis.xray,
        analysis.risk_level,
        [y.symbol for y in analysis.young],
        states or {},
        analysis.covered_value,
        data,
        target,
    )
    return analysis, plan


def held(wild: float = 1.0, calm: float = 1.0, cash: float = 0.0) -> list[Holding]:
    rows = [Holding(symbol="WILD", quantity=wild), Holding(symbol="CALM", quantity=calm)]
    return [*rows, Holding(symbol="USD", quantity=cash)] if cash else rows


def test_each_level_asks_for_less_cash_than_the_one_below_it() -> None:
    analysis, plan = plan_for(held(cash=100.0))
    assert [p.level for p in plan.levels] == ["low", "moderate", "high"]
    low, moderate, high = plan.levels
    assert low.cash_share > moderate.cash_share > high.cash_share
    assert [p.ratio for p in plan.levels if p.reachable] == pytest.approx(
        [p.aim for p in plan.levels if p.reachable]
    )
    # Cash scales the swings down in proportion, so the two figures tie together.
    cash = next(p.weight for p in analysis.positions if p.symbol == "USD")
    assert plan.ratio == pytest.approx(plan.invested_ratio * (1 - cash), rel=1e-6)
    assert plan.target is None
    assert plan.moves == []
    assert plan.signals == []
    assert plan.in_band is None


def test_swings_in_current_conditions_follow_recent_days() -> None:
    _, plan = plan_for(held())
    assert plan.now_ratio is not None
    # WILD's last forty sessions were twice as rough, so today reads above the long run.
    assert plan.now_ratio > plan.ratio * 1.3


def test_the_mixes_are_backtested_and_the_steadiest_swings_least() -> None:
    _, plan = plan_for(held(cash=50.0))
    assert [m.method for m in plan.mixes] == list(allocation.METHODS)
    by_method = {m.method: m for m in plan.mixes}
    assert by_method["min_variance"].daily_volatility < by_method["equal"].daily_volatility
    assert by_method["min_variance"].weights_now["CALM"] > 0.5
    for mix in plan.mixes:
        assert mix.n_days == DAYS - allocation.WINDOW
        assert sum(mix.weights_now.values()) == pytest.approx(1.0)
        assert max(mix.weights_now.values()) <= 0.6 + 1e-9 or mix.method == "current"
    assert plan.trust.grade == "fair"  # under three years of backtest
    # One holding has nothing to be split.
    _, single = plan_for([Holding(symbol="WILD", quantity=1.0)])
    assert single.mixes == []
    assert single.trust.grade == "rough"


def test_a_target_gives_each_holding_a_gap_in_shares_and_money() -> None:
    target = rebalance.Target(level="low")
    analysis, plan = plan_for(held(), target)
    assert plan.target_plan is not None
    assert plan.target_plan.level == "low"
    gaps = {m.symbol: m for m in plan.moves}
    assert set(gaps) == {"WILD", "CALM", "USD"}
    # Nothing is added or taken out: the gaps cancel.
    assert sum(m.change_value for m in plan.moves) == pytest.approx(0.0, abs=1e-6)
    assert gaps["USD"].current_weight == 0.0
    assert gaps["USD"].target_weight == pytest.approx(plan.target_plan.cash_share)
    assert gaps["USD"].change_value == pytest.approx(
        plan.target_plan.cash_share * analysis.covered_value
    )
    # The holdings keep their proportions to each other under the "current" split.
    ratio_now = gaps["WILD"].current_weight / gaps["CALM"].current_weight
    ratio_target = gaps["WILD"].target_weight / gaps["CALM"].target_weight
    assert ratio_target == pytest.approx(ratio_now)

    # Fully invested in something this wild sits far above a low level, and far from it.
    assert plan.in_band is False
    kinds = {s.kind: s for s in plan.signals}
    assert set(kinds) == {"risk_above_target", "drift"}
    assert kinds["risk_above_target"].value >= kinds["risk_above_target"].against == 0.5
    assert set(kinds["drift"].symbols) == {"WILD", "CALM", "USD"}
    assert kinds["drift"].against == allocation.DRIFT_THRESHOLD


def test_inside_the_band_and_close_to_target_raises_nothing() -> None:
    # Find the cash that puts this mix on a moderate level, then hold exactly that.
    analysis, first = plan_for(held(), rebalance.Target(level="moderate"))
    moderate = next(p for p in first.levels if p.level == "moderate")
    invested = analysis.covered_value
    cash = invested * moderate.cash_share / (1 - moderate.cash_share)
    _, plan = plan_for(held(cash=cash), rebalance.Target(level="moderate"))
    assert all(not m.drifted for m in plan.moves)
    assert [s.kind for s in plan.signals if s.kind == "drift"] == []
    # The long-run figure is on target; current conditions decide the band reading.
    assert plan.ratio == pytest.approx(0.75, rel=0.02)
    assert plan.in_band is (0.5 <= (plan.now_ratio or plan.ratio) < 1.0)


def test_a_level_these_holdings_cannot_reach_is_said_not_forced() -> None:
    _, plan = plan_for([Holding(symbol="CALM", quantity=1.0)], rebalance.Target(level="high"))
    assert plan.target_plan is not None
    assert not plan.target_plan.reachable
    assert plan.target_plan.cash_share == 0.0
    kinds = [s.kind for s in plan.signals]
    assert kinds == ["risk_below_target"]


def test_money_in_a_turbulent_market_is_flagged_with_its_share() -> None:
    _, plan = plan_for(held(cash=100.0), rebalance.Target(level="high"), {"WILD": "turbulent"})
    signal = next(s for s in plan.signals if s.kind == "turbulent")
    assert signal.symbols == ["WILD"]
    assert 0 < signal.value < 1
    _, calm = plan_for(held(cash=100.0), rebalance.Target(level="high"), {"WILD": "calm"})
    assert [s for s in calm.signals if s.kind == "turbulent"] == []


def share(plan: rebalance.Plan, symbol: str) -> float:
    """A holding's target share of the invested part."""
    own = next(m.target_weight for m in plan.moves if m.symbol == symbol)
    return own / sum(m.target_weight for m in plan.moves if m.symbol != "USD")


def test_another_split_moves_established_holdings_and_leaves_a_newer_one_alone() -> None:
    holdings = [*held(), Holding(symbol="NEW", quantity=1.0)]
    _, kept = plan_for(holdings, rebalance.Target(level="high", split="current"))
    _, steadier = plan_for(holdings, rebalance.Target(level="high", split="min_variance"))
    # The newer holding keeps its share of the invested part under either split.
    assert share(steadier, "NEW") == pytest.approx(share(kept, "NEW"))
    assert share(steadier, "CALM") > share(kept, "CALM")
    assert share(steadier, "WILD") < share(kept, "WILD")
    # The steadier split swings less when fully invested, so it needs less cash.
    assert steadier.levels[0].cash_share < kept.levels[0].cash_share


def test_a_mix_of_the_users_own_is_compared_holding_by_holding() -> None:
    analysis, plan = plan_for(
        held(cash=100.0), rebalance.Target(weights={"WILD": 0.1, "CALM": 0.5, "NEW": 0.1})
    )
    gaps = {m.symbol: m for m in plan.moves}
    assert set(gaps) == {"WILD", "CALM", "NEW", "USD"}
    assert gaps["USD"].target_weight == pytest.approx(0.3)  # what the shares leave over
    assert gaps["NEW"].current_weight == 0.0  # in the target, not held yet
    assert gaps["NEW"].change_value == pytest.approx(0.1 * analysis.covered_value)
    assert sum(m.change_value for m in plan.moves) == pytest.approx(0.0, abs=1e-6)
    assert sum(m.target_weight for m in plan.moves) == pytest.approx(1.0)
    # A mix has no band to be inside or outside of: only drift is judged.
    assert plan.target_plan is None
    assert plan.in_band is None
    assert {s.kind for s in plan.signals} <= {"drift", "turbulent"}
    assert any(s.kind == "drift" for s in plan.signals)

    # Holding exactly the target raises nothing.
    weights = {p.symbol: p.weight for p in analysis.positions if p.symbol != "USD"}
    _, same = plan_for(held(cash=100.0), rebalance.Target(weights=weights))
    assert same.signals == []
    assert all(not m.drifted for m in same.moves)
