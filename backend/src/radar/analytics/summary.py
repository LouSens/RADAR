"""The plain-language summary at the top of each market page, and a trust grade per claim.

Every section of the page makes one claim. Each claim gets one of three grades, worked
out by a fixed rule from the evidence already stored for it:

- `solid`: tested on unseen data, beat its simple rival, and its error bars are tight.
- `fair`: holds up, with a caveat the reason names.
- `rough`: a weak reading; treat as a hint.

The rules are here, in one place, so they are the same on every screen and can be tested.
"""

from typing import Literal

from pydantic import BaseModel

Grade = Literal["solid", "fair", "rough"]
SIGNIFICANCE = 0.05


class Trust(BaseModel):
    grade: Grade
    # One sentence saying what the grade rests on, with its numbers.
    reason: str


def percent(value: float, digits: int = 0) -> str:
    return f"{value * 100:.{digits}f}%"


def grade_regime(evaluation: dict[str, object] | None) -> Trust:
    """Solid when, on unseen days, rougher states were followed by larger swings and the
    model also predicted those days better than the simple 30-day rule."""
    if not evaluation:
        return Trust(grade="rough", reason="This model has not been tested on unseen days yet.")
    days = int(str(evaluation["n_days"]))
    ordered = bool(evaluation["volatility_is_ordered"])
    beats = float(str(evaluation["model_log_density"])) > float(
        str(evaluation["baseline_log_density"])
    )
    if ordered and beats and days >= 1000:
        return Trust(
            grade="solid",
            reason=f"On {days:,} unseen days, rougher states were followed by larger swings, "
            "and the model beat a simple 30-day rule.",
        )
    if ordered:
        return Trust(
            grade="fair",
            reason=f"On {days:,} unseen days, rougher states were followed by larger swings, "
            "but the model did not clearly beat a simple rule or has little history.",
        )
    return Trust(
        grade="rough",
        reason=f"On {days:,} unseen days the states did not sort the following day's swings.",
    )


def grade_outlook(row: dict[str, object] | None) -> Trust:
    """Solid when the stated level lies inside the 95% range of how often the adjusted
    range actually held, and the simulator was no worse than a constant-volatility walk."""
    if not row:
        return Trust(grade="rough", reason="How often past ranges held has not been measured yet.")
    nominal = float(str(row["nominal"]))
    held = float(str(row["empirical_conformal"]))
    low, high = float(str(row["conformal_low"])), float(str(row["conformal_high"]))
    cases = int(str(row["n"]))
    calibrated = low <= nominal <= high
    no_worse = float(str(row["pinball_model"])) <= float(str(row["pinball_baseline"])) * 1.01
    record = (
        f"The {percent(nominal)} range held {percent(held, 1)} of the time "
        f"({percent(low)} to {percent(high)}) over {cases:,} past forecasts"
    )
    if calibrated and no_worse:
        return Trust(grade="solid", reason=record + ".")
    if calibrated:
        return Trust(
            grade="fair",
            reason=record
            + ", but a simple constant-volatility forecast was a little more accurate.",
        )
    return Trust(grade="rough", reason=record + ", which is off its stated level.")


def grade_swings(scores: list[dict[str, object]], shown: str, days: int) -> Trust:
    """Solid when the shown model beat "yesterday repeated" beyond chance and was not
    measurably worse than the regime average."""
    by_name = {str(s["model"]): s for s in scores}
    chosen, carry, regime = by_name.get(shown), by_name.get("carry"), by_name.get("regime")
    if chosen is None or carry is None:
        return Trust(grade="rough", reason="The forecast has not been scored on unseen days yet.")

    def p_against_har(score: dict[str, object] | None) -> float | None:
        value = score.get("dm_p_value_vs_har") if score else None
        return None if value is None else float(str(value))

    beats_carry = float(str(chosen["qlike"])) < float(str(carry["qlike"]))
    carry_p = p_against_har(carry if shown == "har" else chosen)
    clear = beats_carry and carry_p is not None and carry_p < SIGNIFICANCE
    regime_p = p_against_har(regime)
    loses_to_regime = (
        regime is not None
        and float(str(regime["qlike"])) < float(str(chosen["qlike"]))
        and regime_p is not None
        and regime_p < SIGNIFICANCE
    )
    if clear and not loses_to_regime:
        return Trust(
            grade="solid",
            reason=f"On {days:,} unseen days it beat both simple forecasts, "
            "by more than chance against repeating yesterday.",
        )
    if beats_carry:
        return Trust(
            grade="fair",
            reason=f"On {days:,} unseen days it beat repeating yesterday, "
            "but not clearly, or a simpler average did as well.",
        )
    return Trust(
        grade="rough", reason=f"On {days:,} unseen days it did not beat repeating yesterday."
    )


def grade_risk(methods: list[dict[str, object]]) -> Trust:
    """Solid when every limit of the shown method held at its stated rate."""
    if not methods:
        return Trust(grade="rough", reason="These limits have not been tested on past data yet.")
    reliable = [bool(m["reliable"]) for m in methods]
    periods = int(str(methods[0]["n"]))
    broken = ", ".join(
        f"{int(str(m['breaches']))} breaks against "
        f"{float(str(m['expected_breaches'])):.0f} expected"
        for m in methods
    )
    if all(reliable):
        return Trust(
            grade="solid",
            reason=f"Over {periods:,} past periods the limits held as stated: {broken}.",
        )
    if any(reliable):
        return Trust(
            grade="fair",
            reason=f"Over {periods:,} past periods one limit held as stated "
            f"and one did not: {broken}.",
        )
    return Trust(
        grade="rough", reason=f"Over {periods:,} past periods the limits did not hold: {broken}."
    )


def grade_news(accuracy: dict[str, object] | None) -> Trust:
    """Graded on the low end of the accuracy range: 80% for solid, 65% for fair."""
    if not accuracy:
        return Trust(
            grade="rough", reason="The tone model has not been checked against labels yet."
        )
    model = accuracy["model"]
    if not isinstance(model, dict):
        raise TypeError("accuracy['model'] must be a mapping")
    low, high = float(model["accuracy_low"]), float(model["accuracy_high"])
    labeller = (
        " The labels came from an AI model, not a person."
        if "claude" in list(accuracy.get("labelled_by", []))  # type: ignore[call-overload]
        else ""
    )
    reason = (
        f"It agreed with labels on {percent(float(model['accuracy']))} of {int(model['n']):,} "
        f"headlines ({percent(low)} to {percent(high)}).{labeller}"
    )
    grade: Grade = "solid" if low >= 0.8 else "fair" if low >= 0.65 else "rough"
    return Trust(grade=grade, reason=reason)


class Change(BaseModel):
    """One thing that is different from a week ago."""

    topic: Literal["state", "swings", "tone"]
    text: str


def changes(
    *,
    regime_label: str | None,
    days_in_state: int | None,
    swings_now: float | None,
    swings_week_ago: float | None,
    tone_now: float | None,
    tone_week_ago: float | None,
) -> list[Change]:
    """What has moved in the past week, in plain words. Empty when nothing notable has."""
    found: list[Change] = []
    if regime_label is not None and days_in_state is not None and days_in_state <= 7:
        ago = "today" if days_in_state <= 1 else f"{days_in_state} days ago"
        found.append(
            Change(topic="state", text=f"The market state changed to {regime_label} {ago}.")
        )
    if swings_now and swings_week_ago and swings_week_ago > 0:
        move = swings_now / swings_week_ago - 1.0
        if abs(move) >= 0.15:
            direction = "larger" if move > 0 else "smaller"
            found.append(
                Change(
                    topic="swings",
                    text=f"Expected daily swings are {percent(abs(move))} {direction} "
                    "than a week ago.",
                )
            )
    if tone_now is not None and tone_week_ago is not None and abs(tone_now - tone_week_ago) >= 0.15:
        direction = "more positive" if tone_now > tone_week_ago else "more negative"
        found.append(
            Change(topic="tone", text=f"News tone has turned {direction} over the past week.")
        )
    return found
