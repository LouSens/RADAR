from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from radar.providers import schemas
from radar.quality.gaps import (
    expected_crypto,
    expected_stock_days,
    expected_stock_hours,
    find_gaps,
)
from radar.quality.news import clean_text, find_duplicates
from radar.quality.outliers import flag_outliers, flag_wicks
from radar.quality.schemas import split_valid_bars

T0 = datetime(2024, 1, 1, tzinfo=UTC)
HOUR = timedelta(hours=1)


def bar(ts: datetime, **fields: float) -> schemas.Bar:
    base = {"t": ts, "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.5, "v": 1.0, "n": 1, "vw": 10.2}
    return schemas.Bar.model_validate({**base, **fields})


def ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


# --- schema ----------------------------------------------------------------------------


def test_valid_bars_all_pass() -> None:
    bars = [bar(T0 + i * HOUR) for i in range(5)]
    valid, rejected = split_valid_bars(bars)
    assert valid == bars
    assert rejected == []
    assert split_valid_bars([]) == ([], [])


def test_each_broken_rule_rejects_only_its_bar() -> None:
    bars = [
        bar(T0),
        bar(T0 + 1 * HOUR, h=10.2),  # high below close
        bar(T0 + 2 * HOUR, l=10.4),  # low above open
        bar(T0 + 3 * HOUR, c=-1.0, l=-2.0),  # negative price
        bar(T0 + 4 * HOUR, v=-5.0),  # negative volume
        bar(T0 + 5 * HOUR, v=0.0),  # quote-only bar: valid
    ]
    valid, rejected = split_valid_bars(bars)
    assert [b.timestamp for b in valid] == [T0, T0 + 5 * HOUR]
    by_hour = {datetime.fromisoformat(r["ts"]).hour: r["checks"] for r in rejected}
    assert set(by_hour) == {1, 2, 3, 4}
    assert "high_at_least_open_and_close" in by_hour[1]
    assert "low_at_most_open_and_close" in by_hour[2]
    assert any("greater_than" in check for check in by_hour[3])
    assert any("greater_than_or_equal_to" in check for check in by_hour[4])


def test_duplicate_timestamps_are_rejected() -> None:
    valid, rejected = split_valid_bars([bar(T0), bar(T0), bar(T0 + HOUR)])
    assert [b.timestamp for b in valid] == [T0 + HOUR]
    assert len(rejected) == 2


# --- gaps ------------------------------------------------------------------------------


def test_crypto_gap_runs_are_grouped() -> None:
    expected = expected_crypto(ts("2024-01-01"), ts("2024-01-02"), "1Hour")
    assert len(expected) == 25
    actual = expected.delete([3, 4, 5, 10])
    report = find_gaps(expected, actual)
    assert (report.expected, report.present, report.missing) == (25, 21, 4)
    assert [(g.start.hour, g.end.hour, g.missing) for g in report.gaps] == [(3, 5, 3), (10, 10, 1)]
    assert report.missing_share == 4 / 25


def test_no_gaps_and_bars_outside_the_calendar() -> None:
    expected = expected_crypto(ts("2024-01-01"), ts("2024-01-05"), "1Day")
    extra = expected.append(pd.DatetimeIndex([ts("2024-01-03 12:00")]))
    report = find_gaps(expected, pd.DatetimeIndex(extra))
    assert report.missing == 0
    assert report.gaps == []
    assert report.outside_calendar == 1


def test_stock_days_skip_weekends_and_holidays_and_follow_daylight_saving() -> None:
    # 2024-01-12 is a Friday; Monday 2024-01-15 is Martin Luther King Jr. Day.
    days = expected_stock_days(ts("2024-01-12"), ts("2024-01-17 05:00"))
    assert [d.strftime("%Y-%m-%d %H:%M") for d in days] == [
        "2024-01-12 05:00",
        "2024-01-16 05:00",
        "2024-01-17 05:00",
    ]
    summer = expected_stock_days(ts("2024-07-01"), ts("2024-07-02 04:00"))
    assert [d.hour for d in summer] == [4, 4]  # midnight New York is 04:00 UTC in summer


def test_stock_hours_cover_the_regular_session_and_early_closes() -> None:
    regular = expected_stock_hours(ts("2024-01-16"), ts("2024-01-17"))
    assert [h.hour for h in regular] == [14, 15, 16, 17, 18, 19, 20]  # 09:30 to 16:00 New York
    # 2024-07-03 closed early at 13:00 New York, which is 17:00 UTC.
    early = expected_stock_hours(ts("2024-07-03"), ts("2024-07-04"))
    assert [h.hour for h in early] == [13, 14, 15, 16]
    # Independence Day itself has no session.
    assert len(expected_stock_hours(ts("2024-07-04"), ts("2024-07-05"))) == 0


# --- outliers --------------------------------------------------------------------------


def test_a_single_wild_bar_is_flagged_and_kept() -> None:
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 500)))
    prices[250:] *= 2.0  # one bar doubles; later bars continue from the new level
    close = pd.Series(prices, index=pd.date_range("2024-01-01", periods=500, freq="h", tz="UTC"))
    flags = flag_outliers(close)
    assert flags.sum() == 1
    assert flags.iloc[250]
    assert len(flags) == len(close)


def test_quiet_and_constant_series_have_no_outliers() -> None:
    index = pd.date_range("2024-01-01", periods=50, freq="h", tz="UTC")
    assert not flag_outliers(pd.Series(100.0, index=index)).any()
    rng = np.random.default_rng(1)
    calm = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 50))), index=index)
    assert not flag_outliers(calm).any()


# --- news ------------------------------------------------------------------------------


def test_clean_text_strips_markup_and_whitespace() -> None:
    assert clean_text("<p>Bitcoin &amp; gold\n\n rally</p>") == "Bitcoin & gold rally"
    assert clean_text("  plain   text ") == "plain text"
    assert clean_text("&lt;b&gt;bold&lt;/b&gt; move") == "bold move"
    assert clean_text(None) == ""
    assert clean_text(clean_text("a <i>b</i>  c")) == clean_text("a <i>b</i>  c")


def test_duplicates_need_same_symbol_same_headline_and_a_short_gap() -> None:
    def row(i: int, symbol: str, when: str, headline: str) -> dict[str, object]:
        return {"id": i, "symbol": symbol, "created_at": ts(when), "headline": headline}

    articles = pd.DataFrame(
        [
            row(1, "BTC/USD", "2024-01-01 00:00", "Bitcoin falls"),
            row(2, "BTC/USD", "2024-01-01 06:00", "bitcoin falls "),  # repeat, different case
            row(3, "BTC/USD", "2024-01-03 00:00", "Bitcoin falls"),  # same words, days later
            row(4, "GLD", "2024-01-01 01:00", "Bitcoin falls"),  # another asset
            row(5, "BTC/USD", "2024-01-01 02:00", "Bitcoin rises"),
            row(6, "BTC/USD", "2024-01-03 05:00", "Bitcoin falls"),  # repeats article 3
        ]
    )
    assert find_duplicates(articles) == {2: 1, 6: 3}
    assert find_duplicates(articles.iloc[:1]) == {}


def test_returns_across_a_break_are_not_flagged_when_a_step_is_given() -> None:
    rng = np.random.default_rng(2)
    index = pd.date_range("2024-01-01", periods=300, freq="h", tz="UTC")
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, 300)))
    prices[150:] *= 1.05  # an overnight-style jump
    close = pd.Series(prices, index=index).drop(index[140:150])  # the jump follows a break
    assert flag_outliers(close).sum() == 1
    assert flag_outliers(close, step=pd.Timedelta(hours=1)).sum() == 0


def test_a_bad_print_in_the_low_is_flagged_but_normal_wicks_are_not() -> None:
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    body_top, body_bottom = np.maximum(open_, close), np.minimum(open_, close)
    lows = body_bottom * (1 - rng.uniform(0, 0.01, 300))
    lows[120] = close[120] / 10  # a slipped decimal point
    lows[200] = body_bottom[200] * 0.97  # a large but believable wick
    highs = body_top * (1 + rng.uniform(0, 0.01, 300))
    bars = pd.DataFrame({"open": open_, "close": close, "high": highs, "low": lows})
    flags = flag_wicks(bars)
    assert list(flags[flags].index) == [120]


def test_flat_bars_have_no_suspect_wicks() -> None:
    bars = pd.DataFrame(
        {"open": [10.0] * 5, "high": [10.0] * 5, "low": [10.0] * 5, "close": [10.0] * 5}
    )
    assert not flag_wicks(bars).any()
