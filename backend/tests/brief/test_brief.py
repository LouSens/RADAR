"""The brief's writers and the rule that every number in the text is in the payload."""

import pytest

from radar.brief import grounding, writer
from radar.brief.payload import (
    AssetFacts,
    OutlookFacts,
    Payload,
    PortfolioFacts,
    RiskFacts,
    SignalFacts,
    StateFacts,
    SwingsFacts,
)

BITCOIN = AssetFacts(
    symbol="BTC/USD",
    name="Bitcoin",
    state=StateFacts(label="turbulent", probability_percent=87, days_in_state=12),
    outlook=OutlookFacts(
        horizon_days=7, held=8, out_of=10, low=61200.0, high=68900.0, price=64850.0
    ),
    swings=SwingsFacts(typical_day_percent=2.1),
    risk=RiskFacts(loss_percent=3.4, one_in=20),
    signals=[
        SignalFacts(
            type="abnormal_move",
            variant="down",
            days_ago=2,
            occurrences=44,
            verdict="no measurable edge",
            size_verdict="followed by larger moves",
        ),
        SignalFacts(
            type="regime_change",
            variant="to turbulent",
            days_ago=1,
            occurrences=3,
            verdict="not enough occurrences",
            size_verdict="not enough occurrences",
        ),
    ],
)
PORTFOLIO = PortfolioFacts(
    value=400.63,
    risk_level="low",
    times_stocks=0.37,
    typical_day=1.57,
    range_days=30,
    range_held=8,
    range_out_of=10,
    range_low=392.46,
    range_high=414.27,
    target="moderate risk",
    off_target=["it is moving more or less than the target's range"],
)
PAYLOAD = Payload(day="2026-10-06", assets=[BITCOIN], portfolio=PORTFOLIO)


def test_numbers_are_read_out_of_prose() -> None:
    text = (
        f"Between $61,200 and $68,900.50; down {grounding.MINUS}3.4% or -2; 8 in 10, v2 and 1.5x."
    )
    assert grounding.numbers_in_text(text) == [61200.0, 68900.5, -3.4, -2.0, 8.0, 10.0, 1.5]
    assert grounding.numbers_in_text("No figures here.") == []


def test_numbers_are_found_anywhere_in_a_payload_including_inside_text() -> None:
    found = grounding.numbers_in_payload(
        {"a": 1, "b": [2.5, {"c": "US stocks (S&P 500)"}], "flag": True, "none": None}
    )
    assert sorted(found) == [1.0, 2.5, 500.0]


def test_the_template_brief_contains_only_numbers_from_its_payload() -> None:
    items = writer.write(PAYLOAD)
    assert [(i.symbol, i.writer) for i in items] == [
        ("BTC/USD", "template"),
        ("PORTFOLIO", "template"),
    ]
    bitcoin, portfolio = items
    assert grounding.ungrounded(bitcoin.text, BITCOIN) == []
    assert grounding.ungrounded(portfolio.text, PORTFOLIO) == []
    # And the check does catch a figure that is not there.
    assert grounding.ungrounded(bitcoin.text + " It rose 9.9%.", BITCOIN) == [9.9]
    assert not grounding.check("Worth $401.", PORTFOLIO)


def test_the_template_says_what_is_and_never_what_to_do() -> None:
    bitcoin, portfolio = writer.write(PAYLOAD)
    assert [s.section for s in bitcoin.sentences] == [
        "state",
        "outlook",
        "swings",
        "risk",
        "signals",
        "signals",
    ]
    assert bitcoin.sentences[0].text == (
        "Bitcoin: the market is in a turbulent state (87% probable), and has been for 12 days."
    )
    assert bitcoin.sentences[1].text == (
        "Over the next 7 days, 8 in 10 simulated outcomes end between $61,200 and $68,900, "
        "from $64,850 now."
    )
    assert bitcoin.sentences[3].text == (
        "A fall of 3.4% or more in a day is expected on about 1 day in 20."
    )
    # A signal carries its record, including when the record says nothing.
    assert bitcoin.sentences[4].text == (
        "2 days ago there was an abnormally large hourly move down. Over 44 past cases, "
        "this kind of signal has had no measurable edge in direction and has been followed "
        "by larger moves than usual."
    )
    assert bitcoin.sentences[5].text == (
        "Yesterday the market state changed to turbulent. It has happened 3 times before, "
        "too few to say what tends to follow."
    )
    assert portfolio.sentences[-1].text == (
        "Against your target (moderate risk): it is moving more or less than the target's range."
    )
    everything = (bitcoin.text + " " + portfolio.text).lower()
    assert not any(word in everything for word in writer.BANNED)


def test_missing_results_are_left_out_and_a_capped_probability_is_worded() -> None:
    quiet = AssetFacts(
        symbol="GLD",
        name="Gold",
        state=StateFacts(label="calm", probability_percent=99, more_than=True, days_in_state=1),
    )
    (item,) = writer.write(Payload(day="2026-10-06", assets=[quiet]))
    assert item.text == (
        "Gold: the market is in a calm state (more than 99% probable), and has been for 1 day. "
        "No signals in the past 7 days."
    )
    (empty,) = writer.write(Payload(day="2026-10-06", assets=[AssetFacts(symbol="X", name="X")]))
    assert empty.text == "There are no results for X yet."
    on_target = PORTFOLIO.model_copy(update={"off_target": []})
    assert writer.TemplateWriter().portfolio(on_target)[-1].text == (
        "It is within your target (moderate risk) on every measure."
    )


def rewrite(change: str) -> writer.LlmWriter:
    """A stand-in language model: it returns the sentences it was given, numbered, with
    one change made to the text."""

    def complete(prompt: str) -> str:
        lines = [line for line in prompt.splitlines() if line[:1].isdigit()]
        if change == "invent":
            lines[1] = "2. Over the next 7 days it could reach $75,000."
        elif change == "advise":
            lines[0] = lines[0] + " You should sell."
        elif change == "drop":
            lines = lines[:-1]
        elif change == "fail":
            raise RuntimeError("the service is down")
        return "\n".join(line.replace("simulated outcomes", "possible outcomes") for line in lines)

    return writer.LlmWriter(complete)


def test_a_rewrite_is_used_only_when_every_number_is_in_the_payload() -> None:
    bitcoin, _ = writer.write(PAYLOAD, rewrite("reword"))
    assert bitcoin.writer == "llm"
    assert "8 in 10 possible outcomes" in bitcoin.text
    assert grounding.ungrounded(bitcoin.text, BITCOIN) == []
    assert [s.section for s in bitcoin.sentences][:2] == ["state", "outlook"]


@pytest.mark.parametrize("change", ["invent", "advise", "drop", "fail"])
def test_a_rewrite_that_breaks_a_rule_is_replaced_by_the_template(change: str) -> None:
    template, _ = writer.write(PAYLOAD)
    rewritten, _ = writer.write(PAYLOAD, rewrite(change))
    assert rewritten.text == template.text
    assert "75,000" not in rewritten.text
    assert "should" not in rewritten.text


def test_a_writer_that_returns_ungrounded_text_is_overruled() -> None:
    class Careless:
        name = "careless"

        def asset(self, facts: AssetFacts) -> list[writer.Sentence]:
            return [writer.Sentence(text="It will rise 40% next week.", section="outlook")]

        def portfolio(self, facts: PortfolioFacts) -> list[writer.Sentence]:
            return [writer.Sentence(text="Worth about $400.63 today.", section="portfolio")]

    bitcoin, portfolio = writer.write(PAYLOAD, Careless())
    assert bitcoin.writer == "template"
    assert "40%" not in bitcoin.text
    # A grounded sentence from another writer is kept.
    assert (portfolio.writer, portfolio.text) == ("careless", "Worth about $400.63 today.")


def test_the_brief_opens_with_the_price_now_and_what_there_is_to_do() -> None:
    from radar.brief.payload import TodayFacts

    moved = BITCOIN.model_copy(
        update={"today": TodayFacts(price=65120.0, change_percent=-1.4, articles=12)}
    )
    account = PORTFOLIO.model_copy(
        update={"has_plan": True, "to_buy": ["US stocks $49.20", "Gold $36.10"]}
    )
    payload = Payload(day="2026-10-07", assets=[moved], portfolio=account)
    bitcoin, portfolio = writer.write(payload)
    assert bitcoin.sentences[0].text == "Bitcoin: $65,120 now, down 1.4% since the last close."
    assert bitcoin.sentences[1].text == "12 news articles in the last 24 hours."
    assert [s.section for s in bitcoin.sentences[:2]] == ["price", "news"]
    assert portfolio.sentences[1].text == (
        "Cash over your plan to put in: US stocks $49.20, Gold $36.10."
    )
    assert portfolio.sentences[1].section == "todo"
    # Every number is still one the payload holds, and the wording rules still hold.
    assert bitcoin.writer == portfolio.writer == "template"
    assert not grounding.ungrounded(bitcoin.text, moved)
    assert not grounding.ungrounded(portfolio.text, account)
    everything = (bitcoin.text + " " + portfolio.text).lower()
    assert not any(word in everything for word in writer.BANNED)


def test_a_flat_price_and_a_matched_plan_are_said_plainly() -> None:
    from radar.brief.payload import TodayFacts

    flat = BITCOIN.model_copy(update={"today": TodayFacts(price=64850.0, change_percent=0.0)})
    matched = PORTFOLIO.model_copy(update={"has_plan": True})
    bitcoin, portfolio = writer.write(Payload(day="2026-10-07", assets=[flat], portfolio=matched))
    assert bitcoin.sentences[0].text == "Bitcoin: $64,850 now, unchanged since the last close."
    assert bitcoin.sentences[1].section == "state"  # no news count when there is none
    assert portfolio.sentences[1].text == "Nothing to do: your account matches your plan."
