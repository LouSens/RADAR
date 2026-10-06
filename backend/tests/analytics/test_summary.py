"""The trust grades and the what-changed list, rule by rule."""

from radar.analytics import summary


def regime(
    ordered: bool = True, model: float = 2.0, baseline: float = 1.9, days: int = 1602
) -> dict[str, object]:
    return {
        "n_days": days,
        "volatility_is_ordered": ordered,
        "model_log_density": model,
        "baseline_log_density": baseline,
    }


def test_regime_grade() -> None:
    assert summary.grade_regime(regime()).grade == "solid"
    assert "1,602 unseen days" in summary.grade_regime(regime()).reason
    assert summary.grade_regime(regime(model=1.8)).grade == "fair"  # did not beat the rule
    assert summary.grade_regime(regime(days=400)).grade == "fair"  # too little history
    assert summary.grade_regime(regime(ordered=False)).grade == "rough"
    assert summary.grade_regime(None).grade == "rough"


def outlook(held: float, low: float, high: float, model: float = 0.0100) -> dict[str, object]:
    return {
        "nominal": 0.8,
        "empirical_conformal": held,
        "conformal_low": low,
        "conformal_high": high,
        "n": 1595,
        "pinball_model": model,
        "pinball_baseline": 0.0100,
    }


def test_outlook_grade() -> None:
    good = summary.grade_outlook(outlook(0.803, 0.75, 0.85))
    assert good.grade == "solid"
    assert "held 80.3% of the time (75% to 85%) over 1,595 past forecasts" in good.reason
    # Well calibrated, but a simple forecast was more accurate.
    assert summary.grade_outlook(outlook(0.803, 0.75, 0.85, model=0.0104)).grade == "fair"
    # The stated 80% is outside the range of how often it held.
    assert summary.grade_outlook(outlook(0.90, 0.86, 0.93)).grade == "rough"
    assert summary.grade_outlook(None).grade == "rough"


def scores(
    har: float, carry_p: float | None, regime_qlike: float, regime_p: float
) -> list[dict[str, object]]:
    return [
        {"model": "har", "qlike": har, "dm_p_value_vs_har": None},
        {"model": "gbt", "qlike": 0.6, "dm_p_value_vs_har": 0.2},
        {"model": "carry", "qlike": 0.9, "dm_p_value_vs_har": carry_p},
        {"model": "regime", "qlike": regime_qlike, "dm_p_value_vs_har": regime_p},
    ]


def test_swings_grade() -> None:
    assert summary.grade_swings(scores(0.47, 0.0, 0.53, 0.002), "har", 1601).grade == "solid"
    # The regime average scored a touch lower, but not measurably: still solid.
    assert summary.grade_swings(scores(0.667, 0.0, 0.659, 0.65), "har", 2201).grade == "solid"
    # The regime average is measurably better: only fair.
    assert summary.grade_swings(scores(0.667, 0.0, 0.60, 0.01), "har", 2201).grade == "fair"
    # Beats repeating yesterday, but not beyond chance.
    assert summary.grade_swings(scores(0.85, 0.4, 0.95, 0.5), "har", 300).grade == "fair"
    assert summary.grade_swings(scores(0.95, 0.4, 0.99, 0.5), "har", 300).grade == "rough"
    assert summary.grade_swings([], "har", 0).grade == "rough"


def limit(reliable: bool, breaches: int, expected: float) -> dict[str, object]:
    return {"reliable": reliable, "n": 1351, "breaches": breaches, "expected_breaches": expected}


def test_risk_grade() -> None:
    both = summary.grade_risk([limit(True, 73, 67.6), limit(True, 12, 13.5)])
    assert both.grade == "solid"
    assert "73 breaks against 68 expected, 12 breaks against 14 expected" in both.reason
    assert summary.grade_risk([limit(True, 73, 67.6), limit(False, 31, 13.5)]).grade == "fair"
    assert summary.grade_risk([limit(False, 130, 67.6), limit(False, 31, 13.5)]).grade == "rough"
    assert summary.grade_risk([]).grade == "rough"


def news(accuracy: float, low: float, high: float) -> dict[str, object]:
    return {
        "labelled_by": ["claude"],
        "model": {"n": 700, "accuracy": accuracy, "accuracy_low": low, "accuracy_high": high},
    }


def test_news_grade_uses_the_low_end_of_the_range() -> None:
    rough = summary.grade_news(news(0.611, 0.575, 0.647))
    assert rough.grade == "rough"
    assert "61% of 700 headlines (57% to 65%)" in rough.reason
    assert "AI model, not a person" in rough.reason
    assert summary.grade_news(news(0.72, 0.68, 0.76)).grade == "fair"
    assert summary.grade_news(news(0.86, 0.82, 0.89)).grade == "solid"
    assert summary.grade_news(None).grade == "rough"


def test_changes_list_only_what_moved() -> None:
    quiet = summary.changes(
        regime_label="calm",
        days_in_state=85,
        swings_now=0.0145,
        swings_week_ago=0.0140,
        tone_now=-0.05,
        tone_week_ago=-0.02,
    )
    assert quiet == []

    busy = summary.changes(
        regime_label="turbulent",
        days_in_state=3,
        swings_now=0.03,
        swings_week_ago=0.02,
        tone_now=-0.4,
        tone_week_ago=0.1,
    )
    assert [c.topic for c in busy] == ["state", "swings", "tone"]
    assert busy[0].text == "The market state changed to turbulent 3 days ago."
    assert busy[1].text == "Expected daily swings are 50% larger than a week ago."
    assert busy[2].text == "News tone has turned more negative over the past week."
    # Missing inputs are skipped, not guessed.
    partial = summary.changes(
        regime_label=None,
        days_in_state=None,
        swings_now=0.01,
        swings_week_ago=0.02,
        tone_now=None,
        tone_week_ago=0.3,
    )
    assert [c.text for c in partial] == ["Expected daily swings are 50% smaller than a week ago."]


def test_no_grade_or_change_tells_the_reader_what_to_do() -> None:
    texts = [
        summary.grade_regime(regime()).reason,
        summary.grade_outlook(outlook(0.803, 0.75, 0.85)).reason,
        summary.grade_swings(scores(0.47, 0.0, 0.53, 0.002), "har", 1601).reason,
        summary.grade_risk([limit(True, 73, 67.6)]).reason,
        summary.grade_news(news(0.611, 0.575, 0.647)).reason,
    ]
    for text in texts:
        lowered = text.lower()
        assert "buy" not in lowered
        assert "sell" not in lowered
        assert "you should" not in lowered


def test_the_range_ahead_is_graded_on_how_often_past_ranges_held() -> None:
    # 80% of 40 is 32; anything from 27 to 37 is what such a range plausibly gives.
    solid = summary.grade_simulation(40, 31, 0.8, 30)
    assert solid.grade == "solid"
    assert "held in 31 of 40 past 30-session forecasts" in solid.reason
    assert summary.grade_simulation(40, 22, 0.8, 30).grade == "rough"
    assert summary.grade_simulation(40, 40, 0.8, 30).grade == "rough"  # too wide is also off
    few = summary.grade_simulation(12, 10, 0.8, 90)
    assert few.grade == "fair"
    assert "few cases" in few.reason
    assert summary.grade_simulation(0, 0, 0.8, 30).grade == "rough"


def test_a_signal_record_is_graded_on_its_thinnest_kind() -> None:
    assert summary.grade_signals([140, 210]).grade == "solid"
    fair = summary.grade_signals([44, 140])
    assert fair.grade == "fair"
    assert "44 to 140 past cases" in fair.reason
    rough = summary.grade_signals([3, 20, 48])
    assert rough.grade == "rough"
    assert "not judged" in rough.reason
    assert summary.grade_signals([]).grade == "rough"
