"""F7. Writers that turn a brief payload into sentences.

The template writer is the default: fixed wording, no outside service, the same text
for the same payload. A language-model writer can sit behind the same interface; its
text is used only if it passes the grounding check, and the template's is used
otherwise.

Wording rules (hard rule "honest output"): describe what is and what has happened;
never say what to do.
"""

from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel

from radar.brief import grounding
from radar.brief.payload import AssetFacts, Payload, PortfolioFacts, Section, SignalFacts

BANNED = ("buy", "sell", "you should")


class Sentence(BaseModel):
    text: str
    # The page that holds the evidence for it.
    section: Section


class Item(BaseModel):
    """One market's paragraph, or the portfolio's, as linked sentences."""

    symbol: str
    name: str
    sentences: list[Sentence]
    writer: str

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)


class BriefWriter(Protocol):
    name: str

    def asset(self, facts: AssetFacts) -> list[Sentence]: ...

    def portfolio(self, facts: PortfolioFacts) -> list[Sentence]: ...


def money(value: float) -> str:
    """Dollars as shown: whole dollars from a thousand up, cents below."""
    return f"${value:,.0f}" if abs(value) >= 1000 else f"${value:,.2f}"


def number(value: float) -> str:
    """A figure without needless decimals: 2.0 is written 2, 2.5 stays 2.5."""
    return f"{value:g}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


SIGNAL_NAME = {
    ("regime_change", "to calm"): "the market state changed to calm",
    ("regime_change", "to normal"): "the market state changed to normal",
    ("regime_change", "to turbulent"): "the market state changed to turbulent",
    ("abnormal_move", "up"): "there was an abnormally large hourly move up",
    ("abnormal_move", "down"): "there was an abnormally large hourly move down",
}
DIRECTION = {
    "followed by rises more often": "has been followed by rises more often than an ordinary day",
    "followed by falls more often": "has been followed by falls more often than an ordinary day",
    "no measurable edge": "has had no measurable edge in direction",
}
SIZE = {
    "followed by larger moves": "has been followed by larger moves than usual",
    "followed by smaller moves": "has been followed by smaller moves than usual",
}


def _signal(signal: SignalFacts) -> str:
    what = SIGNAL_NAME.get((signal.type, signal.variant), "a signal fired")
    when = (
        "Today"
        if signal.days_ago == 0
        else "Yesterday"
        if signal.days_ago == 1
        else f"{plural(signal.days_ago, 'day').capitalize()} ago"
    )
    if signal.verdict == "not enough occurrences":
        record = (
            f"It has happened {plural(signal.occurrences, 'time')} before, "
            "too few to say what tends to follow."
        )
    else:
        parts = [DIRECTION.get(signal.verdict, "has had no measurable edge in direction")]
        if signal.size_verdict in SIZE:
            parts.append(SIZE[signal.size_verdict])
        record = (
            f"Over {plural(signal.occurrences, 'past case')}, this kind of signal "
            + " and ".join(parts)
            + "."
        )
    return f"{when} {what}. {record}"


class TemplateWriter:
    """Fixed wording. Every number it prints is taken from the payload as it stands."""

    name = "template"

    def asset(self, facts: AssetFacts) -> list[Sentence]:
        out: list[Sentence] = []
        if facts.today is not None:
            today = facts.today
            if today.change_percent == 0:
                moved = "unchanged since the last close"
            else:
                way = "up" if today.change_percent > 0 else "down"
                moved = f"{way} {number(abs(today.change_percent))}% since the last close"
            out.append(
                Sentence(text=f"{facts.name}: {money(today.price)} now, {moved}.", section="price")
            )
            if today.articles:
                out.append(
                    Sentence(
                        text=f"{plural(today.articles, 'news article')} in the last "
                        f"{today.articles_hours} hours.",
                        section="news",
                    )
                )
        if facts.state is not None:
            state = facts.state
            out.append(
                Sentence(
                    text=f"{facts.name}: the market is in a {state.label} state "
                    f"({'more than ' if state.more_than else ''}"
                    f"{state.probability_percent}% probable), "
                    f"and has been for {plural(state.days_in_state, 'day')}.",
                    section="state",
                )
            )
        if facts.outlook is not None:
            look = facts.outlook
            out.append(
                Sentence(
                    text=f"Over the next {plural(look.horizon_days, 'day')}, {look.held} in "
                    f"{look.out_of} simulated outcomes end between {money(look.low)} and "
                    f"{money(look.high)}, from {money(look.price)} now.",
                    section="outlook",
                )
            )
        if facts.swings is not None:
            out.append(
                Sentence(
                    text="A typical day's move is expected to be about "
                    f"{number(facts.swings.typical_day_percent)}%.",
                    section="swings",
                )
            )
        if facts.risk is not None:
            out.append(
                Sentence(
                    text=f"A fall of {number(facts.risk.loss_percent)}% or more in a day is "
                    f"expected on about {plural(facts.risk.on_days, 'day')} in "
                    f"{facts.risk.one_in}.",
                    section="risk",
                )
            )
        if facts.signals:
            out.extend(Sentence(text=_signal(s), section="signals") for s in facts.signals)
        elif out:
            out.append(
                Sentence(
                    text=f"No signals in the past {plural(facts.signal_window_days, 'day')}.",
                    section="signals",
                )
            )
        if not out:
            out.append(
                Sentence(text=f"There are no results for {facts.name} yet.", section="state")
            )
        return out

    def portfolio(self, facts: PortfolioFacts) -> list[Sentence]:
        out = [Sentence(text=f"Your portfolio is worth {money(facts.value)}.", section="portfolio")]
        if facts.to_buy or facts.to_trim:
            parts = []
            if facts.to_buy:
                parts.append("cash over your plan to put in: " + ", ".join(facts.to_buy))
            if facts.to_trim:
                parts.append("over its share of your plan: " + ", ".join(facts.to_trim))
            text = "; ".join(parts) + "."
            out.append(Sentence(text=text[0].upper() + text[1:], section="todo"))
        elif facts.has_plan:
            out.append(
                Sentence(text="Nothing to do: your account matches your plan.", section="todo")
            )
        if facts.risk_level is not None and facts.times_stocks is not None:
            typical = (
                f", about {money(facts.typical_day)} on a typical day"
                if facts.typical_day is not None
                else ""
            )
            out.append(
                Sentence(
                    text=f"Its risk level is {facts.risk_level}: it moves "
                    f"{number(facts.times_stocks)} times as much as US stocks{typical}.",
                    section="portfolio",
                )
            )
        if (
            facts.range_low is not None
            and facts.range_high is not None
            and facts.range_days is not None
        ):
            out.append(
                Sentence(
                    text=f"In {facts.range_days} trading days, {facts.range_held} in "
                    f"{facts.range_out_of} simulated futures end between "
                    f"{money(facts.range_low)} and {money(facts.range_high)}.",
                    section="outlook",
                )
            )
        if facts.target is not None:
            if facts.off_target:
                text = f"Against your target ({facts.target}): " + "; ".join(facts.off_target) + "."
            else:
                text = f"It is within your target ({facts.target}) on every measure."
            out.append(Sentence(text=text, section="target"))
        return out


class LlmWriter:
    """A language-model rewrite, used only when grounded.

    `complete` takes a prompt and returns text. It is given the template's sentences
    and the payload, nothing else. If the result contains a number that is not in the
    payload, a banned word, or the wrong number of sentences, the template's text is
    kept. No provider is wired in by default.
    """

    name = "llm"

    def __init__(self, complete: Callable[[str], str]) -> None:
        self._complete = complete
        self._template = TemplateWriter()

    def _rewrite(self, sentences: list[Sentence], payload: BaseModel) -> list[Sentence]:
        prompt = (
            "Rewrite each numbered sentence in plain, calm English for an ordinary "
            "investor. Keep one line per sentence, in the same order. Use only the "
            "numbers already in the sentences. Describe; never give advice.\n\n"
            + "\n".join(f"{i + 1}. {s.text}" for i, s in enumerate(sentences))
        )
        try:
            lines = [line.strip() for line in self._complete(prompt).splitlines() if line.strip()]
        except Exception:
            return sentences
        cleaned = [
            line.split(". ", 1)[1] if line[:1].isdigit() and ". " in line else line
            for line in lines
        ]
        if len(cleaned) != len(sentences):
            return sentences
        text = " ".join(cleaned)
        if grounding.ungrounded(text, payload) or any(word in text.lower() for word in BANNED):
            return sentences
        return [
            Sentence(text=line, section=s.section)
            for line, s in zip(cleaned, sentences, strict=True)
        ]

    def asset(self, facts: AssetFacts) -> list[Sentence]:
        return self._rewrite(self._template.asset(facts), facts)

    def portfolio(self, facts: PortfolioFacts) -> list[Sentence]:
        return self._rewrite(self._template.portfolio(facts), facts)


def write(payload: Payload, writer: BriefWriter | None = None) -> list[Item]:
    """The brief for a payload: one item per market, then the portfolio's when there is
    one. Whatever the writer, text that is not grounded falls back to the template."""
    chosen: BriefWriter = writer or TemplateWriter()
    template = TemplateWriter()
    items = []
    for facts in payload.assets:
        sentences = chosen.asset(facts)
        used = chosen.name
        if grounding.ungrounded(" ".join(s.text for s in sentences), facts):
            sentences, used = template.asset(facts), template.name
        items.append(Item(symbol=facts.symbol, name=facts.name, sentences=sentences, writer=used))
    if payload.portfolio is not None:
        sentences = chosen.portfolio(payload.portfolio)
        used = chosen.name
        if grounding.ungrounded(" ".join(s.text for s in sentences), payload.portfolio):
            sentences, used = template.portfolio(payload.portfolio), template.name
        items.append(
            Item(symbol="PORTFOLIO", name="Your portfolio", sentences=sentences, writer=used)
        )
    return items
