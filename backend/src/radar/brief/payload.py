"""F7. The daily brief's payload: every fact the brief may state, and nothing else.

Numbers are stored here already rounded to what the text shows. The writer may only
print numbers found in this payload, and `grounding.check` enforces that, so a number
in the brief can always be traced to a stored result.
"""

from typing import Literal

from pydantic import BaseModel

# Where a sentence's evidence lives on the screen: a tab of a market or portfolio page.
Section = Literal["state", "outlook", "swings", "risk", "signals", "portfolio", "target"]


class StateFacts(BaseModel):
    label: str
    # Whole percent, at most 99: a model is never certain. `more_than` is set when
    # the figure was capped, and the text then says "more than 99%".
    probability_percent: int
    more_than: bool = False
    days_in_state: int


class OutlookFacts(BaseModel):
    horizon_days: int
    # "8 in 10": the level of the range, as counts.
    held: int
    out_of: int
    low: float
    high: float
    price: float


class SwingsFacts(BaseModel):
    # A typical day's move expected tomorrow, in percent.
    typical_day_percent: float


class RiskFacts(BaseModel):
    # A one-day loss this large or worse is expected on about one day in `one_in`.
    loss_percent: float
    one_in: int
    on_days: int = 1


class SignalFacts(BaseModel):
    type: Literal["regime_change", "abnormal_move"]
    variant: str
    days_ago: int
    # How many past cases its record rests on, and what the record says.
    occurrences: int
    verdict: str
    size_verdict: str


class AssetFacts(BaseModel):
    symbol: str
    name: str
    state: StateFacts | None = None
    outlook: OutlookFacts | None = None
    swings: SwingsFacts | None = None
    risk: RiskFacts | None = None
    # Signals from the last `signal_window_days`, newest first.
    signals: list[SignalFacts] = []
    signal_window_days: int = 7


class PortfolioFacts(BaseModel):
    value: float
    # The mix's daily movement as a multiple of US stocks', and the word for it.
    risk_level: str | None = None
    times_stocks: float | None = None
    # A typical day in money, and the value range 30 sessions ahead.
    typical_day: float | None = None
    range_days: int | None = None
    range_held: int | None = None
    range_out_of: int | None = None
    range_low: float | None = None
    range_high: float | None = None
    # Where it stands against the user's target: plain descriptions, already worded.
    target: str | None = None
    off_target: list[str] = []


class Payload(BaseModel):
    """One day's brief input. `day` is the date the brief is for, in ISO form."""

    day: str
    assets: list[AssetFacts]
    portfolio: PortfolioFacts | None = None
