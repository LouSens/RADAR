"""The core and satellite report on a mix whose answers can be worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.models import sleeves
from radar.models.portfolio import HoldingRisk

DAYS = pd.bdate_range("2024-01-01", periods=4, tz="UTC")
RETURNS = pd.DataFrame(
    {
        # Simple returns of +10%, -10%, +10%, 0%: they add up to +10%.
        "STEADY": np.log([1.10, 0.90, 1.10, 1.00]),
        # +50% on each of the last two days only: a newer holding.
        "WILD": [np.nan, np.nan, np.log(1.5), np.log(1.5)],
        "PLAIN": np.log([1.01, 1.01, 1.01, 1.01]),
    },
    index=DAYS,
)
HOLDINGS = [
    HoldingRisk(symbol="STEADY", weight=0.5, daily_volatility=0.01, risk_share=0.3),
    HoldingRisk(symbol="WILD", weight=0.1, daily_volatility=0.05, risk_share=0.6),
    HoldingRisk(symbol="PLAIN", weight=0.1, daily_volatility=0.01, risk_share=0.1),
    HoldingRisk(symbol="USD", weight=0.3, daily_volatility=0.0, risk_share=0.0),
]


def test_nothing_tagged_means_no_report() -> None:
    assert sleeves.report(HOLDINGS, {}, RETURNS, "USD") is None
    assert sleeves.report(HOLDINGS, {"GONE": "core"}, RETURNS, "USD") is None


def test_each_group_is_weighed_against_the_risk_it_carries() -> None:
    report = sleeves.report(HOLDINGS, {"STEADY": "core", "WILD": "satellite"}, RETURNS, "USD")
    assert report is not None
    found = {s.group: s for s in report.sleeves}
    assert list(found) == ["core", "satellite", "untagged", "cash"]
    assert (found["core"].symbols, found["core"].weight, found["core"].risk_share) == (
        ["STEADY"],
        0.5,
        0.3,
    )
    # A tenth of the money, six tenths of the risk.
    assert (found["satellite"].weight, found["satellite"].risk_share) == (0.1, 0.6)
    assert (found["cash"].weight, found["cash"].risk_share) == (0.3, 0.0)
    assert sum(s.weight for s in report.sleeves) == pytest.approx(1.0)
    assert sum(s.risk_share for s in report.sleeves) == pytest.approx(1.0)


def test_contributions_are_weight_times_return_and_add_up_to_the_whole() -> None:
    report = sleeves.report(HOLDINGS, {"STEADY": "core", "WILD": "satellite"}, RETURNS, "USD")
    assert report is not None
    found = {s.group: s.contribution for s in report.sleeves}
    assert found["core"] == pytest.approx(0.5 * 0.10)
    assert found["satellite"] == pytest.approx(0.1 * 1.0)  # two days of +50%
    assert found["untagged"] == pytest.approx(0.1 * 0.04)
    assert found["cash"] == 0.0
    assert report.total_return == pytest.approx(sum(found.values()))
    # The whole is the sum of the mix's daily returns at these weights.
    simple = np.expm1(RETURNS.fillna(0.0)) @ np.array([0.5, 0.1, 0.1])
    assert report.total_return == pytest.approx(float(simple.sum()))
    assert (report.n_days, report.first_day, report.last_day) == (
        4,
        DAYS[0].date(),
        DAYS[-1].date(),
    )
    # The newer holding's part covers only the days it has, and the report says so.
    assert report.short == ["WILD"]


def test_only_the_latest_window_is_added_up() -> None:
    report = sleeves.report(HOLDINGS, {"STEADY": "core"}, RETURNS, "USD", window=2)
    assert report is not None
    assert report.n_days == 2
    core = next(s for s in report.sleeves if s.group == "core")
    assert core.contribution == pytest.approx(0.5 * 0.10)  # +10% then 0%
    assert report.short == []
