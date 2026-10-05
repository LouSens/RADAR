"""Correlation, risk transmission, weekend gaps, and macro drivers on made-up data."""

import numpy as np
import pandas as pd
import pytest

from radar.analytics import correlation, summary, transmission
from radar.models import drivers


def num(value: float | None) -> float:
    """A figure that must be present."""
    assert value is not None
    return value


def sessions(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n, tz="UTC") + pd.Timedelta(hours=21)


def linked(n: int = 800, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 0.02, n)
    return pd.DataFrame(
        {"A": a, "B": 0.6 * a + rng.normal(0, 0.01, n), "C": rng.normal(0, 0.01, n)},
        index=sessions(n),
    )


def estimate_rolling(frame: pd.DataFrame) -> pd.Series:
    return correlation.rolling(frame["A"], frame["B"], 90)


def estimate_weighted(frame: pd.DataFrame) -> pd.Series:
    return correlation.weighted(frame["A"], frame["B"])


# --- correlation -----------------------------------------------------------------------


def test_rolling_and_weighted_correlation_use_only_the_past() -> None:
    returns = linked()
    later = returns.copy()
    later.iloc[500:, 1] = -later.iloc[500:, 0]
    for estimate in (
        estimate_rolling,
        estimate_weighted,
    ):
        before, after = estimate(returns), estimate(later)
        pd.testing.assert_series_equal(before.iloc[:500], after.iloc[:500])
        assert before.iloc[-1] > 0.6
        assert after.iloc[-1] < -0.9
    assert correlation.rolling(returns["A"], returns["B"], 90).iloc[:89].isna().all()


def test_the_weighted_estimate_turns_sooner_than_the_rolling_one() -> None:
    returns = linked()
    returns.iloc[700:, 1] = -returns.iloc[700:, 0]
    slow = correlation.rolling(returns["A"], returns["B"], 90).iloc[720]
    fast = correlation.weighted(returns["A"], returns["B"]).iloc[720]
    assert fast < slow


def test_interval_narrows_with_more_days_and_stays_inside_bounds() -> None:
    wide = correlation.interval(0.3, 30)
    narrow = correlation.interval(0.3, 900)
    assert wide[0] < narrow[0] < 0.3 < narrow[1] < wide[1]
    assert wide[0] >= -1
    assert wide[1] <= 1
    assert correlation.interval(0.5, 3) == (-1.0, 1.0)


def test_correlation_by_regime_reports_sample_sizes_and_withholds_thin_ones() -> None:
    returns = linked()
    labels = pd.Series("calm", index=returns.index, dtype=object)
    labels.iloc[400:780] = "turbulent"
    labels.iloc[780:] = "normal"  # twenty days: too few
    rows = {r.label: r for r in correlation.by_regime(returns["A"], returns["B"], labels)}
    assert rows["calm"].n == 400
    assert rows["turbulent"].n == 380
    assert rows["calm"].correlation == pytest.approx(0.77, abs=0.08)
    assert num(rows["calm"].low) < num(rows["calm"].correlation) < num(rows["calm"].high)
    assert rows["normal"].n == 20
    assert rows["normal"].correlation is None


def test_grid_puts_markets_that_move_alike_next_to_each_other() -> None:
    rng = np.random.default_rng(3)
    x, y = rng.normal(0, 1, 400), rng.normal(0, 1, 400)
    frame = pd.DataFrame(
        {
            "X1": x,
            "Y1": y,
            "X2": x + rng.normal(0, 0.2, 400),
            "Y2": y + rng.normal(0, 0.2, 400),
        },
        index=sessions(400),
    )
    result = correlation.grid(frame)
    assert result is not None
    order = result.symbols
    assert abs(order.index("X1") - order.index("X2")) == 1
    assert abs(order.index("Y1") - order.index("Y2")) == 1
    assert result.n_days == 400
    assert [result.matrix[i][i] for i in range(4)] == pytest.approx([1, 1, 1, 1])
    assert correlation.grid(frame.iloc[:10]) is None


# --- risk transmission -----------------------------------------------------------------


def test_episodes_start_when_the_label_turns_turbulent_and_do_not_overlap() -> None:
    labels = pd.Series(["calm"] * 40, dtype=object)
    labels.iloc[5:8] = "turbulent"
    labels.iloc[9:11] = "turbulent"  # within ten sessions of the first: not a new episode
    labels.iloc[30:33] = "turbulent"
    labels.iloc[0] = None
    assert transmission.episode_starts(labels).tolist() == [5, 30]
    # A series that begins turbulent has no known start.
    assert transmission.episode_starts(pd.Series(["turbulent"] * 5, dtype=object)).tolist() == []


def test_swings_after_a_day_use_only_later_days() -> None:
    returns = np.array([0.01, -0.02, 0.03, np.nan, 0.05, 0.01])
    out = transmission.swing_after(returns, 2)
    assert out[0] == pytest.approx(0.025)
    assert np.isnan(out[1])  # its window holds the missing day
    assert np.isnan(out[2])
    assert out[3] == pytest.approx(0.03)
    assert np.isnan(out[4:]).all()  # the future is incomplete


def spill_case(boost: float, episodes: int = 40) -> tuple[pd.Series, pd.Series]:
    n = episodes * 30 + 30
    rng = np.random.default_rng(5)
    labels = pd.Series("calm", index=sessions(n), dtype=object)
    target = rng.normal(0, 0.01, n)
    for k in range(episodes):
        start = 20 + k * 30
        labels.iloc[start : start + 3] = "turbulent"
        target[start + 1 : start + 6] *= boost
    return labels, pd.Series(target, index=labels.index)


def test_a_real_spillover_is_found_and_no_spillover_is_not_invented() -> None:
    labels, target = spill_case(boost=3.0)
    found = transmission.spillover("A", "B", labels, target, 5)
    assert found.episodes == 40
    assert num(found.ratio) == pytest.approx(3.0, rel=0.25)
    assert num(found.ratio_low) < num(found.ratio) < num(found.ratio_high)
    assert num(found.ratio_low) > 1.5
    assert num(found.p_value) < 0.01
    assert transmission.spill_verdict(found, found.p_value).verdict == "spills over"

    labels, target = spill_case(boost=1.0)
    none = transmission.spillover("A", "B", labels, target, 5)
    assert none.ratio == pytest.approx(1.0, abs=0.2)
    assert transmission.spill_verdict(none, none.p_value).verdict == "no measurable spillover"
    # A significant result is still judged after correction for the family.
    assert transmission.spill_verdict(found, 0.2).verdict == "no measurable spillover"


def test_too_few_episodes_gives_no_verdict() -> None:
    labels, target = spill_case(boost=3.0, episodes=10)
    row = transmission.spillover("A", "B", labels, target, 5)
    assert row.episodes == 10
    assert row.ratio is None
    assert transmission.spill_verdict(row, None).verdict == "not enough episodes"


# --- weekend gaps ----------------------------------------------------------------------


def test_weekend_gap_finds_a_link_and_reports_no_link_honestly() -> None:
    rng = np.random.default_rng(9)
    index = pd.date_range("2021-01-04", periods=200, freq="W-MON", tz="UTC")
    bitcoin = pd.Series(rng.normal(0, 0.04, 200), index=index)
    follows = pd.Series(0.1 * bitcoin + rng.normal(0, 0.003, 200), index=index)
    alone = pd.Series(np.random.default_rng(21).normal(0, 0.003, 200), index=index)

    linked_row = transmission.weekend_gap("SPY", bitcoin, follows)
    assert linked_row.weekends == 200
    assert linked_row.slope == pytest.approx(0.1, abs=0.02)
    assert num(linked_row.low) > 0
    assert linked_row.worst_count == 20
    assert num(linked_row.gap_after_worst) < num(linked_row.gap_usual)
    assert transmission.link_verdict(linked_row, linked_row.p_value).verdict == "moves with"

    unlinked = transmission.weekend_gap("GLD", bitcoin, alone)
    assert num(unlinked.low) < 0 < num(unlinked.high)
    assert transmission.link_verdict(unlinked, unlinked.p_value).verdict == "no measurable link"

    few = transmission.weekend_gap("GLD", bitcoin.iloc[:20], alone.iloc[:20])
    assert few.verdict == "not enough weekends"
    assert few.correlation is None


# --- macro drivers ---------------------------------------------------------------------


def driver_panel(n: int = 700) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    stocks = rng.normal(0, 0.01, n)
    dollar = rng.normal(0, 0.004, n)
    noise = rng.normal(0, 0.004, n)
    return pd.DataFrame(
        {
            "Y": 1.2 * stocks - 0.8 * dollar + rng.normal(0, 0.006, n),
            "STOCKS": stocks,
            "DOLLAR": dollar,
            "NOISE": noise,
        },
        index=sessions(n),
    )


def test_drivers_recover_direction_and_say_no_link_for_noise() -> None:
    result = drivers.analyse(
        driver_panel(), "Y", ["STOCKS", "DOLLAR", "NOISE"], "STOCKS", 250, bootstraps=200
    )
    assert result is not None
    by_symbol = {d.symbol: d for d in result.drivers}
    assert by_symbol["STOCKS"].verdict == "moves with"
    assert by_symbol["DOLLAR"].verdict == "moves against"
    assert by_symbol["NOISE"].verdict == "no measurable link"
    for reading in result.drivers:
        assert reading.low <= reading.coefficient <= reading.high
    assert result.strongest == "STOCKS"
    assert 0.6 < result.r_squared < 0.95
    score = result.out_of_sample
    assert score is not None
    assert score.n_days == 450
    # Both drivers matter, so the full model beats stocks alone on unseen days.
    assert score.r_squared > score.baseline_r_squared > 0
    assert len(result.history) == 91
    assert result.history[-1].day == result.last_day


def test_drivers_never_look_ahead() -> None:
    panel = driver_panel()
    changed = panel.copy()
    changed.iloc[600:] *= 7
    args = ("Y", ["STOCKS", "DOLLAR", "NOISE"], "STOCKS", 250)
    before = drivers.analyse(panel.iloc[:600], *args, bootstraps=50)
    again = drivers.analyse(changed.iloc[:600], *args, bootstraps=50)
    assert before == again
    # Out-of-sample predictions for early days are untouched by later days.
    y, x = panel["Y"].to_numpy(), panel[["STOCKS", "DOLLAR", "NOISE"]].to_numpy()
    y2, x2 = changed["Y"].to_numpy(), changed[["STOCKS", "DOLLAR", "NOISE"]].to_numpy()
    p1, m1, _ = drivers.walk_forward(y, x, x[:, [0]], 250)
    p2, m2, _ = drivers.walk_forward(y2, x2, x2[:, [0]], 250)
    early = p1 < 590
    np.testing.assert_array_equal(p1, p2)
    np.testing.assert_allclose(m1[early], m2[early])


def test_too_little_history_gives_no_driver_result() -> None:
    assert drivers.analyse(driver_panel(200), "Y", ["STOCKS", "DOLLAR"], "STOCKS", 250) is None


# --- trust grades ----------------------------------------------------------------------


def test_trust_grades_follow_their_rules() -> None:
    assert summary.grade_relationship(1443).grade == "solid"
    assert summary.grade_relationship(300).grade == "fair"
    assert summary.grade_spillovers([40, 35]).grade == "solid"
    assert summary.grade_spillovers([40, 16]).grade == "fair"
    assert summary.grade_spillovers([40, 9]).grade == "rough"
    assert "9 past episodes" in summary.grade_spillovers([40, 9]).reason
    assert summary.grade_weekends([299, 299]).grade == "solid"
    assert summary.grade_weekends([40]).grade == "fair"
    assert summary.grade_weekends([]).grade == "rough"
    solid = summary.grade_drivers({"n_days": 2452, "r_squared": 0.2, "baseline_r_squared": -0.01})
    assert solid.grade == "solid"
    assert "20%" in solid.reason
    assert "0%" in solid.reason
    tie = summary.grade_drivers({"n_days": 1193, "r_squared": 0.176, "baseline_r_squared": 0.176})
    assert tie.grade == "fair"
    assert (
        summary.grade_drivers({"n_days": 900, "r_squared": -0.1, "baseline_r_squared": 0}).grade
        == "rough"
    )
    assert summary.grade_drivers(None).grade == "rough"
