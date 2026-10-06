"""Scheduled events on prices whose answers can be worked out by hand."""

from datetime import UTC, date, datetime, time

import numpy as np
import pandas as pd
import pytest

from radar.analytics import events


def test_the_committed_dates_file_loads_and_is_in_order() -> None:
    kinds = {k.key: k for k in events.load_events()}
    assert set(kinds) == {"fed", "jobs", "inflation"}
    for kind in kinds.values():
        assert kind.dates == sorted(set(kind.dates))
        assert kind.dates[0].year == 2016
        assert kind.source
    assert (len(kinds["fed"].dates), len(kinds["jobs"].dates)) == (95, 131)
    # The cancelled March 2020 meeting and the emergency ones are not scheduled events.
    assert date(2020, 3, 18) not in kinds["fed"].dates
    assert date(2020, 3, 15) not in kinds["fed"].dates
    assert kinds["fed"].time_eastern == time(14, 0)


KIND = events.EventKind(
    key="fed",
    name="Fed interest rate decision",
    time_eastern=time(14, 0),
    source="test",
    dates=[date(2024, 1, 31), date(2024, 3, 20), date(2024, 7, 31)],
)


def test_an_announcement_time_is_converted_from_eastern_with_daylight_saving() -> None:
    assert KIND.at(date(2024, 1, 31)) == datetime(2024, 1, 31, 19, 0, tzinfo=UTC)  # winter
    assert KIND.at(date(2024, 7, 31)) == datetime(2024, 7, 31, 18, 0, tzinfo=UTC)  # summer


def test_what_is_coming_up_is_soonest_first_and_excludes_what_has_been_announced() -> None:
    morning = datetime(2024, 3, 20, 12, 0, tzinfo=UTC)
    found = events.upcoming([KIND], morning)
    assert [(e.at.date(), e.days_until) for e in found] == [
        (date(2024, 3, 20), 0),
        (date(2024, 7, 31), 133),
    ]
    evening = datetime(2024, 3, 20, 19, 0, tzinfo=UTC)
    assert [e.at.date() for e in events.upcoming([KIND], evening)] == [date(2024, 7, 31)]


def prices(returns: np.ndarray) -> pd.Series:
    days = pd.bdate_range("2020-01-01", periods=len(returns) + 1, tz="UTC")
    return pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])), index=days)


def test_an_event_on_a_day_the_market_was_shut_is_left_out() -> None:
    close = prices(np.zeros(20))
    days = pd.DatetimeIndex(close.index)
    saturday = date(2020, 1, 4)
    found = events.positions(days, [days[3].date(), saturday, days[10].date()])
    assert found.tolist() == [3, 10]


def test_the_five_questions_are_answered_from_the_days_around_each_event() -> None:
    # Every tenth day is an event. Quiet days move 0.1%; event days move 3%, always up;
    # the day before is always down; the day after always goes on up.
    n = 600
    returns = np.where(np.arange(n) % 2 == 0, 0.001, -0.001)
    event_rows = np.arange(10, n - 10, 10)  # row t of prices is the return returns[t-1]
    returns[event_rows - 1] = 0.03
    returns[event_rows - 2] = -0.004
    returns[event_rows] = 0.006
    close = prices(returns)
    dates = [stamp.date() for stamp in close.index[event_rows]]
    result = events.measure("X", close, dates, week=5)
    assert result.n_events == len(event_rows)
    assert (result.first_day, result.last_day) == (dates[0], dates[-1])
    assert result.size.on_event == pytest.approx(0.03)
    assert result.size.other_days is not None
    assert result.size.other_days < 0.003
    assert result.day_before.share == 0.0
    assert result.event_day.share == 1.0
    assert result.next_day.share == 1.0
    assert result.next_week.share == 1.0  # 0.6% up then small moves that cancel out

    (judged,) = events.judge([events.EventResult(key="k", name="K", markets=[result])])
    (market,) = judged.markets
    assert market.size.verdict == "moves more on these days"
    assert market.day_before.verdict == "leans down"
    assert market.event_day.verdict == "leans up"
    assert market.next_day.verdict == "tends to carry on"
    assert market.next_week.verdict == "tends to carry on"
    assert events.comparisons([judged]) == (4, 1)


def test_events_that_mean_nothing_are_said_to_show_no_pattern() -> None:
    rng = np.random.default_rng(3)
    close = prices(rng.normal(0, 0.01, 2500))
    results = []
    for kind in range(6):
        rows = np.sort(rng.choice(np.arange(5, 2480), 80, replace=False))
        dates = [stamp.date() for stamp in close.index[rows]]
        results.append(
            events.EventResult(
                key=f"k{kind}", name="K", markets=[events.measure("X", close, dates, week=5)]
            )
        )
    for result in events.judge(results):
        (market,) = result.markets
        assert market.size.verdict == "no measurable difference"
        for share in (market.day_before, market.event_day, market.next_day, market.next_week):
            assert share.verdict == "no measurable pattern"
            assert share.low is not None
            assert share.high is not None
            assert share.low <= (share.share or 0) <= share.high


def test_too_few_events_are_not_judged() -> None:
    close = prices(np.full(200, 0.01))
    dates = [stamp.date() for stamp in close.index[10:30]]
    (judged,) = events.judge(
        [events.EventResult(key="k", name="K", markets=[events.measure("X", close, dates, 5)])]
    )
    (market,) = judged.markets
    assert market.n_events == 20
    assert market.size.verdict == "not enough events"
    assert market.event_day.verdict == "not enough events"
    assert events.comparisons([judged]) == (0, 0)
    # No events at all in the stored prices: empty, and still not an error.
    empty = events.measure("X", close, [date(1999, 1, 4)], 5)
    assert (empty.n_events, empty.first_day, empty.size.on_event) == (0, None, None)
