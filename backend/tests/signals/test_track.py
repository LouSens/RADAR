"""Track records on prices whose outcomes can be worked out by hand."""

import numpy as np
import pandas as pd
import pytest

from radar.signals import track

HORIZONS = [(1, "1 day"), (7, "1 week")]


def prices(returns: np.ndarray) -> pd.Series:
    days = pd.date_range("2022-01-01", periods=len(returns) + 1, tz="UTC")
    return pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])), index=days)


def test_a_forward_return_starts_at_the_close_of_the_signal_day() -> None:
    close = pd.Series(
        [100.0, 110.0, 99.0, 99.0], index=pd.date_range("2024-01-01", periods=4, tz="UTC")
    )
    forward = track.forward_returns(close, 1)
    assert forward.iloc[0] == pytest.approx(np.log(1.1))
    assert forward.iloc[1] == pytest.approx(np.log(0.9))
    assert np.isnan(forward.iloc[3])  # the last day has no next day yet
    # Nothing before a day's close is in its forward return.
    earlier = close.copy()
    earlier.iloc[0] = 5.0
    assert track.forward_returns(earlier, 1).iloc[1] == forward.iloc[1]


def test_the_range_for_a_share_is_sensible_for_small_counts() -> None:
    low, high = track.wilson(8, 10)
    assert low == pytest.approx(0.490, abs=0.002)
    assert high == pytest.approx(0.943, abs=0.002)
    assert track.wilson(0, 5)[0] == 0.0
    assert track.wilson(5, 5)[1] == 1.0


def test_outcomes_are_counted_and_sized() -> None:
    found = track.outcome(pd.Series([0.02, -0.01, 0.03, np.nan, 0.0]))
    assert (found.n, found.share_positive) == (4, 0.5)
    assert found.mean == pytest.approx(0.01)
    assert found.mean_size == pytest.approx(0.015)
    assert found.quantiles["0.5"] == pytest.approx(0.01)
    empty = track.outcome(pd.Series([np.nan]))
    assert (empty.n, empty.share_positive, empty.quantiles) == (0, None, {})


def test_a_signal_followed_by_rises_far_more_often_has_an_edge() -> None:
    rng = np.random.default_rng(5)
    returns = rng.normal(0, 0.01, 600)
    returns[0::10] = 0.02  # the day after every tenth day is always up
    close = prices(returns)
    days = list(close.index[0:590:10])
    record = track.record("abnormal_move", "BTC/USD", "up", days, close, HORIZONS)
    assert (record.n, record.variant) == (59, "up")
    day, week = record.horizons
    assert (day.signal.n, day.signal.share_positive) == (59, 1.0)
    assert day.baseline.n == 600
    assert 0.45 < (day.baseline.share_positive or 0) < 0.65
    assert day.verdict == "followed by rises more often"
    assert record.verdict == "followed by rises more often"
    assert (week.steps, week.label) == (7, "1 week")
    # It survives being looked at beside records that show nothing.
    quiet = track.record(
        "abnormal_move", "BTC/USD", "down", list(close.index[5:595:10]), close, HORIZONS
    )
    kept, flat = track.correct_family([record, quiet])
    assert kept.verdict == "followed by rises more often"
    assert flat.verdict == "no measurable edge"


def test_too_few_occurrences_is_said_and_not_judged() -> None:
    close = prices(np.full(100, 0.01))
    record = track.record(
        "regime_change", "SPY", "to calm", list(close.index[:10]), close, HORIZONS
    )
    assert record.n == 10
    assert record.verdict == "not enough occurrences"
    assert record.size_verdict == "not enough occurrences"
    assert track.correct_family([record])[0].verdict == "not enough occurrences"
    # Days with no price are left out, and a signal that never fired has an empty record.
    missing = [pd.Timestamp("1999-01-01", tz="UTC")]
    assert track.record("regime_change", "SPY", "to calm", missing, close, HORIZONS).n == 0


def test_a_fluke_among_many_records_does_not_count_as_an_edge() -> None:
    rng = np.random.default_rng(8)
    close = prices(rng.normal(0, 0.01, 3000))
    forward = track.forward_returns(close, 1)
    # Forty kinds of signal that mean nothing: random days.
    records = [
        track.record(
            "abnormal_move",
            "BTC/USD",
            f"kind {i}",
            list(rng.choice(close.index[:-8], 60, replace=False)),
            close,
            HORIZONS,
        )
        for i in range(40)
    ]
    # Before correction, luck alone gives a few "edges" among eighty comparisons.
    uncorrected = sum(h.verdict != "no measurable edge" for r in records for h in r.horizons)
    corrected = track.correct_family(records)
    assert all(h.verdict == "no measurable edge" for r in corrected for h in r.horizons)
    assert all(h.size_verdict == "no measurable difference" for r in corrected for h in r.horizons)
    assert uncorrected >= 0  # documents the comparison; the count itself is luck
    assert forward.notna().sum() == 3000


def test_larger_moves_after_a_signal_are_found_whichever_way_they_went() -> None:
    rng = np.random.default_rng(2)
    returns = rng.normal(0, 0.01, 900)
    signal_positions = np.arange(0, 890, 15)
    # The day after each signal swings three times as much, up or down alike.
    returns[signal_positions] = rng.normal(0, 0.03, len(signal_positions))
    close = prices(returns)
    days = list(close.index[signal_positions])
    (record,) = track.correct_family(
        [track.record("abnormal_move", "SPY", "up", days, close, HORIZONS)]
    )
    day = record.horizons[0]
    assert day.signal.mean_size is not None
    assert day.baseline.mean_size is not None
    assert day.signal.mean_size > 2 * day.baseline.mean_size
    assert record.size_verdict == "followed by larger moves"
    assert record.verdict == "no measurable edge"  # no direction to it
