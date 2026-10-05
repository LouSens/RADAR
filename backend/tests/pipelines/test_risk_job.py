"""Tail-risk estimates against the real test database."""

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, RiskMetric
from radar.pipelines import risk as job
from radar.pipelines import volatility as volatility_job
from tests.pipelines.test_regime_job import ASSET, DAY, DAYS, START, seed

SETTINGS = {"min_train": 260, "refit_every": 30, "n_paths": 200, "min_window": 20}


def test_estimates_are_stored_once_with_their_backtest(engine: Engine, session: Session) -> None:
    seed(session)
    volatility_job.forecast(engine, ASSET, min_train=260, refit_every=30)
    changed = job.assess(engine, ASSET, **SETTINGS)
    assert changed == session.scalar(select(func.count()).select_from(RiskMetric))
    assert job.assess(engine, ASSET, **SETTINGS) == 0  # nothing new: no work, no rows

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
    job.assess(engine, ASSET, **SETTINGS)
    methods = set(session.scalars(select(RiskMetric.method).distinct()))
    assert methods == {"historical", "simulator"}
    registered = session.scalars(select(ModelRegistry)).one()
    assert {b["method"] for b in registered.metrics["horizons"]["7"]["backtests"]} == methods
