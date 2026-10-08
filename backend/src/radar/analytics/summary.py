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


def grade_xray(n_days: int, young: int = 0) -> Trust:
    """Solid when the mix was measured over three years of shared sessions or more and
    every holding has a long record."""
    if young:
        return Trust(
            grade="fair",
            reason=f"Measured over {n_days:,} trading days for most holdings, but {young} "
            f"newer holding{'' if young == 1 else 's'} had to be estimated on a short history.",
        )
    if n_days >= 750:
        return Trust(
            grade="solid",
            reason=f"Measured over {n_days:,} trading days that every holding has prices for.",
        )
    return Trust(
        grade="fair",
        reason=f"Measured over only {n_days:,} trading days that every holding has prices "
        "for; how holdings move together changes over time.",
    )


def grade_stress(available: int, partial: int, total: int) -> Trust:
    """Solid when every episode could be replayed with every holding."""
    if total == 0 or available == 0:
        return Trust(
            grade="rough", reason="None of the past episodes has prices for these holdings."
        )
    if available == total and partial == 0:
        return Trust(
            grade="solid",
            reason=f"All {total} episodes were replayed with every holding, on real prices.",
        )
    return Trust(
        grade="fair",
        reason=f"{available} of {total} episodes could be replayed, {partial} of them "
        "without some holdings. The past is a guide, not a limit on what can happen.",
    )


def grade_relationship(n_days: int) -> Trust:
    """Solid when the two markets share three years of sessions or more."""
    if n_days >= 750:
        return Trust(
            grade="solid",
            reason=f"Measured on {n_days:,} trading days both markets have prices for. "
            "It describes the past; relationships between markets drift.",
        )
    return Trust(
        grade="fair",
        reason=f"Measured on only {n_days:,} trading days both markets have prices for.",
    )


def grade_spillovers(episodes: list[int]) -> Trust:
    """Graded on the pair with the fewest episodes: 30 for solid, 15 for fair."""
    if not episodes or min(episodes) < 15:
        fewest = min(episodes) if episodes else 0
        return Trust(
            grade="rough",
            reason=f"Some pairs have as few as {fewest} past episodes, too few to judge.",
        )
    fewest = min(episodes)
    if fewest >= 30:
        return Trust(
            grade="solid",
            reason=f"Every pair has {fewest} or more past episodes, each judged on what "
            "followed it and corrected for the number of pairs tested.",
        )
    return Trust(
        grade="fair",
        reason=f"Pairs have as few as {fewest} past episodes, so the ranges are wide.",
    )


def grade_weekends(weekends: list[int]) -> Trust:
    """Graded on the number of weekends measured: 100 for solid, 30 for fair."""
    fewest = min(weekends) if weekends else 0
    if fewest >= 100:
        return Trust(grade="solid", reason=f"Measured on {fewest:,} or more past weekends.")
    if fewest >= 30:
        return Trust(grade="fair", reason=f"Measured on only {fewest} past weekends.")
    return Trust(grade="rough", reason=f"Only {fewest} past weekends, too few to judge.")


def grade_drivers(score: dict[str, object] | None) -> Trust:
    """Solid when, on 500 or more unseen days, the drivers explained some of the moves and
    explained more than the single simple driver did."""
    if not score:
        return Trust(grade="rough", reason="This has not been tested on unseen days yet.")
    days = int(str(score["n_days"]))
    own = float(str(score["r_squared"]))
    simple = float(str(score["baseline_r_squared"]))
    if own > 0 and own > simple and days >= 500:
        return Trust(
            grade="solid",
            reason=f"On {days:,} unseen days the drivers accounted for {percent(own)} of "
            f"the moves, against {percent(max(simple, 0))} for the simple rival.",
        )
    if own > 0:
        return Trust(
            grade="fair",
            reason=f"On {days:,} unseen days the drivers accounted for {percent(own)} of "
            f"the moves, no better than the simple rival's {percent(max(simple, 0))}.",
        )
    return Trust(
        grade="rough",
        reason=f"On {days:,} unseen days the drivers did not predict the moves better "
        "than the average of the days before.",
    )


def grade_moves(evidence: dict[str, object] | None, has_reference: bool) -> Trust:
    """Solid when the split into the wider market and the asset's own cleared its bar on
    unseen days, or when no split is made and only the count of each day's size is shown.
    Fair when a split was wanted and could not be supported (decision 095)."""
    counted = "How large each day was is a count against the days before it."
    if not has_reference:
        return Trust(
            grade="solid",
            reason=f"{counted} No split is made: this market is what others are measured against.",
        )
    whole = evidence.get("whole") if evidence else None
    if evidence and evidence.get("passed") and isinstance(whole, dict):
        agreed = float(str(whole["sign_agreement"]))
        return Trust(
            grade="solid",
            reason=f"On {int(str(whole['n_days'])):,} unseen days the wider market accounted for "
            f"{percent(float(str(whole['share_explained'])))} of its moves, and on "
            f"{percent(agreed)} of its {int(str(whole['n_large'])):,} large days it moved the "
            "same way.",
        )
    why = str(evidence["reason"]) if evidence and evidence.get("reason") else "it is untested"
    return Trust(
        grade="fair",
        reason=f"No split into the wider market and its own is shown: {why}. {counted}",
    )


def grade_mixes(n_days: int) -> Trust:
    """Graded on how much history the mixes were run through: three years for solid."""
    if n_days <= 0:
        return Trust(
            grade="rough", reason="There is too little shared history to run the mixes through."
        )
    if n_days >= 750:
        return Trust(
            grade="solid",
            reason=f"Each mix was run through {n_days:,} trading days, deciding at every "
            "monthly rebalance from earlier days only. This is what happened, not a forecast.",
        )
    return Trust(
        grade="fair",
        reason=f"Each mix was run through only {n_days:,} trading days. This is what "
        "happened, not a forecast.",
    )


# The stated level whose past record grades the portfolio's range ahead.
SIMULATION_LEVEL = 0.8


def grade_simulation(n: int, inside: int, level: float, days: int) -> Trust:
    """Solid when the count of past ranges that held is one a range of that level
    would plausibly give (the middle 95% of a binomial) on at least 30 cases; fair
    when it is in line on fewer; rough when it is off."""
    from scipy.stats import binom

    if n <= 0:
        return Trust(
            grade="rough",
            reason="There is too little shared history to check past ranges against what happened.",
        )
    low, high = binom.interval(0.95, n, level)
    record = (
        f"The {percent(level)} range held in {inside} of {n} past {days}-session "
        "forecasts, each drawn from earlier days only"
    )
    if not low <= inside <= high:
        return Trust(grade="rough", reason=record + ", which is off its stated level.")
    if n >= 30:
        return Trust(grade="solid", reason=record + ", in line with its stated level.")
    return Trust(
        grade="fair",
        reason=record + ", in line with its stated level, but that is few cases to judge by.",
    )


def grade_signals(occurrences: list[int]) -> Trust:
    """Graded on the fewest past cases behind any kind of this signal: 100 for solid, 30
    for fair. A record says what followed on average, so it is only as good as its count."""
    if not occurrences:
        return Trust(grade="rough", reason="This signal has not fired in the stored history.")
    fewest, most = min(occurrences), max(occurrences)
    span = f"{fewest:,}" if fewest == most else f"{fewest:,} to {most:,}"
    record = f"Each kind of this signal rests on {span} past cases, found using only what "
    record += "was known on the day"
    if fewest >= 100:
        return Trust(grade="solid", reason=record + ".")
    if fewest >= 30:
        return Trust(grade="fair", reason=record + ". Under 100 is a modest sample.")
    return Trust(
        grade="rough",
        reason=record + ". Kinds with under 30 cases are not judged at all.",
    )


def grade_events(counts: list[int]) -> Trust:
    """Graded on the market with the fewest past events of this kind: 100 for solid, 30
    for fair."""
    seen = [n for n in counts if n > 0]
    if not seen:
        return Trust(grade="rough", reason="No past events of this kind are in the stored prices.")
    fewest, most = min(seen), max(seen)
    span = f"{fewest:,}" if fewest == most else f"{fewest:,} to {most:,}"
    record = f"Measured on {span} past events per market, from the official release dates"
    if fewest >= 100:
        return Trust(grade="solid", reason=record + ".")
    if fewest >= 30:
        return Trust(grade="fair", reason=record + ". Under 100 is a modest sample.")
    return Trust(grade="rough", reason=record + ". Under 30 is too few to judge.")


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
