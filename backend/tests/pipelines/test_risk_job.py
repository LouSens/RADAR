"""Tail-risk estimates against the real test database."""

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, RiskMetric
from radar.pipelines import risk as job
from radar.pipelines import volatility as volatility_job
from tests.pipelines.test_regime_job import ASSET, DAY, DAYS, START, seed


def assess(engine: Engine) -> int:
    return job.assess(engine, ASSET, min_train=260, refit_every=30, n_paths=200, min_window=20)


def test_estimates_are_stored_once_with_their_backtest(engine: Engine, session: Session) -> None:
    seed(session)
    volatility_job.forecast(engine, ASSET, min_train=260, refit_every=30)
    changed = assess(engine)
    assert changed == session.scalar(select(func.count()).select_from(RiskMetric))
    assert assess(engine) == 0  # nothing new: no work, no rows

    latest = session.execute(
        select(RiskMetric).where(RiskMetric.ts == START + DAYS * DAY)
    ).scalars()
    by_key = {(r.horizon_days, r.level, r.method): r for r in latest}
    assert set(by_key) == {
        (h, level, m)
        for h in (1, 7)
        for level in (0.95, 0.99)
        for m in ("historical", "filtered", "simulator")
    }
    for row in by_key.values():
        assert 0 < row.var <= row.expected_shortfall < 1
        assert row.realised_loss is None  # the days it covers have not happened yet
    # A wider horizon and a higher level both mean a larger limit.
    assert by_key[(7, 0.95, "historical")].var > by_key[(1, 0.95, "historical")].var
    assert by_key[(1, 0.99, "simulator")].var > by_key[(1, 0.95, "simulator")].var

    registered = session.scalars(
        select(ModelRegistry).where(ModelRegistry.name == "tail_risk")
    ).one()
    day = registered.metrics["horizons"]["1"]
    assert day["shown"] in {"historical", "filtered", "simulator"}
    assert len(day["backtests"]) == 6
    assert all(b["n"] > 0 and 0 <= b["breach_rate"] <= 1 for b in day["backtests"])
    assert registered.metrics["drawdowns"][0]["depth"] < 0


def test_without_volatility_forecasts_the_filtered_method_is_left_out(
    engine: Engine, session: Session
) -> None:
    seed(session)
    assess(engine)
    methods = set(session.scalars(select(RiskMetric.method).distinct()))
    assert methods == {"historical", "simulator"}
    registered = session.scalars(select(ModelRegistry)).one()
    assert {b["method"] for b in registered.metrics["horizons"]["7"]["backtests"]} == methods


def test_limits_are_judged_together_and_a_forced_run_changes_no_rows(
    engine: Engine, session: Session
) -> None:
    seed(session)
    assess(engine)
    stored = session.scalars(select(ModelRegistry)).one().metrics["horizons"]
    tests = [b for horizon in stored.values() for b in horizon["backtests"]]
    assert len(tests) == 8  # two methods, two levels, two horizons: one family
    for test in tests:
        if test["kupiec_p_value"] is not None:
            assert test["kupiec_p_adjusted"] >= test["kupiec_p_value"]
            assert test["reliable"] == (test["kupiec_p_adjusted"] >= 0.05)
    # Forcing a rerun recomputes the backtest but the estimates themselves are unchanged.
    assert (
        job.assess(
            engine, ASSET, min_train=260, refit_every=30, n_paths=200, min_window=20, force=True
        )
        == 0
    )
