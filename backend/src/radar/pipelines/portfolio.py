"""Store holdings and analyse the portfolio's risk (spec F6, F10). All I/O lives here.

Holdings arrive through a `HoldingsSource`. Saving them replaces the stored set and
recomputes the analysis, which is kept as one row so that requests only ever read it.
The worker recomputes it as new prices arrive.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.analytics import summary
from radar.config import load_settings
from radar.db.models import Portfolio, PortfolioAnalysis, PortfolioHolding
from radar.features.panels import MixedPanel
from radar.models import drivers as driver_model
from radar.models import portfolio as model
from radar.models import portfolio_simulation as simulation_model
from radar.models import regular_buying as buying_model
from radar.models import sleeves as sleeve_model
from radar.models.holdings import (
    CASH,
    CASH_NAME,
    NO_HISTORY,
    Holding,
    Holdings,
    HoldingsSource,
)
from radar.models.tail_risk import MIN_WINDOW
from radar.pipelines import discover, rebalance
from radar.pipelines.datasets import build_mixed_panel
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.binance import BinanceError, BinanceReading, BinanceSource
from radar.universe import Universe

log = structlog.get_logger(__name__)

PORTFOLIO_ID = 1
MIX = "PORTFOLIO"
# Funds that stand for outside forces (spec F8), in the order shown.
DRIVER_SYMBOLS = ("SPY", "UUP", "TLT", "TIP", "VIXY")
DRIVER_WINDOW = 250
# What the mix's swings are set against: the stock market is the yardstick.
STOCKS = "SPY"
REFERENCES = ("TLT", "GLD", "SPY", "BTC/USD")
# Holdings whose market state is read from another instrument (decision 011).
STATE_OF = {"PAXG/USD": "GLD"}


class Position(BaseModel):
    symbol: str
    name: str
    quantity: float
    tag: str | None
    # Price at the close of the last session used, and the holding's value at it.
    price: float
    value: float
    weight: float


class Unmeasured(BaseModel):
    symbol: str
    name: str
    weight: float
    # Sessions of price history it has; `model.MIN_HISTORY` are needed.
    days: int


class HoldingState(BaseModel):
    """The market state of a holding right now, from the market it belongs to."""

    symbol: str
    # The market whose state is quoted: the holding itself, or the one that stands for it.
    market: str
    label: str
    weight: float


class Trusts(BaseModel):
    xray: summary.Trust
    risk: summary.Trust
    stress: summary.Trust
    drivers: summary.Trust | None = None
    simulation: summary.Trust | None = None


class Analysis(BaseModel):
    """Everything the Portfolio screen shows, as stored."""

    as_of: AwareDatetime
    model_version: str
    value: float
    # The part of `value` the risk figures cover: everything except holdings with too
    # little price history. Money figures for risk are shares of this.
    covered_value: float = 0.0
    # Holdings counted in the money but not yet in the risk figures, and why.
    unmeasured: list[Unmeasured] = []
    # Newer holdings: in the risk figures, but estimated on the short history they have.
    # The loss limits are measured on the rest and scaled up for these.
    young: list[Unmeasured] = []
    risk_level: model.RiskLevel | None = None
    positions: list[Position]
    xray: model.Xray
    limits: list[model.LimitHorizon]
    stress: list[model.StressResult]
    # Which outside forces the whole mix has moved with (250 sessions), when measurable.
    drivers: driver_model.WindowResult | None = None
    driver_names: dict[str, str] = {}
    # The current state of each holding's market, where RADAR models one.
    states: list[HoldingState] = []
    # Risk levels, other mixes, and the gap to the user's target. Null when the
    # stock market yardstick is not available.
    plan: rebalance.Plan | None = None
    # The range of the portfolio's value 30 and 90 sessions ahead, when there is
    # enough joint history to draw one.
    simulation: simulation_model.Simulation | None = None
    # What the core and the satellite holdings carry; null until one is tagged.
    sleeves: sleeve_model.Report | None = None
    trust: Trusts


def stored_holdings(session: Session) -> tuple[str | None, list[Holding]]:
    """The saved holdings and where they came from."""
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    if portfolio is None:
        return None, []
    rows = session.scalars(
        select(PortfolioHolding)
        .where(PortfolioHolding.portfolio_id == PORTFOLIO_ID)
        .order_by(PortfolioHolding.symbol)
    ).all()
    holdings = [
        Holding(
            symbol=r.symbol,
            quantity=r.quantity,
            tag="core" if r.tag == "core" else "satellite" if r.tag == "satellite" else None,
        )
        for r in rows
    ]
    if portfolio.cash > 0:
        holdings.append(Holding(symbol=CASH, quantity=portfolio.cash))
    return portfolio.source, holdings


def save(
    session: Session, source: HoldingsSource, leveraged: list[dict[str, Any]] | None = None
) -> Holdings:
    """Replace the stored holdings with what the source holds. Does not commit."""
    read = source.read()
    return store(session, read, leveraged)


def store(
    session: Session,
    read: Holdings,
    leveraged: list[dict[str, Any]] | None = None,
    wallets: list[dict[str, Any]] | None = None,
) -> Holdings:
    """Replace the stored holdings with ones already read. Does not commit."""
    now = datetime.now(UTC)
    cash = sum(h.quantity for h in read.holdings if h.symbol == CASH)
    assets = [h for h in read.holdings if h.symbol != CASH]
    # Tags belong to the user: a source that carries none leaves them as they were.
    before = session.get(Portfolio, PORTFOLIO_ID)
    tags = dict(before.tags) if before is not None else {}
    tags |= {h.symbol: h.tag for h in assets if h.tag}
    session.execute(
        insert(Portfolio)
        .values(
            id=PORTFOLIO_ID,
            name="My portfolio",
            source=read.source,
            updated_at=now,
            leveraged=leveraged or [],
            wallets=wallets or [],
            cash=cash,
            tags=tags,
        )
        .on_conflict_do_update(
            index_elements=[Portfolio.id],
            set_={
                "source": read.source,
                "updated_at": now,
                "leveraged": leveraged or [],
                "wallets": wallets or [],
                "cash": cash,
                "tags": tags,
            },
        )
    )
    session.execute(delete(PortfolioHolding).where(PortfolioHolding.portfolio_id == PORTFOLIO_ID))
    session.execute(delete(PortfolioAnalysis).where(PortfolioAnalysis.portfolio_id == PORTFOLIO_ID))
    if assets:
        session.execute(
            insert(PortfolioHolding),
            [
                {
                    "portfolio_id": PORTFOLIO_ID,
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "tag": tags.get(h.symbol),
                }
                for h in assets
            ],
        )
    return read


def analyse(
    holdings: list[Holding],
    panel: MixedPanel,
    universe: Universe,
    *,
    min_window: int = MIN_WINDOW,
    with_drivers: bool = True,
    with_simulation: bool = True,
) -> Analysis:
    """The full analysis of a set of holdings on a price panel. Pure given its inputs."""
    cash = sum(h.quantity for h in holdings if h.symbol == CASH)
    holdings = [h for h in holdings if h.symbol != CASH]
    if not holdings:
        raise model.NotEnoughHistoryError(
            "Only cash is held, so there is no market risk to analyse."
        )
    symbols = [h.symbol for h in holdings]
    prices = panel.prices[symbols]
    priced = prices.ffill().iloc[-1]
    if priced.isna().any():
        missing = ", ".join(str(s) for s in priced[priced.isna()].index)
        raise model.NotEnoughHistoryError(f"No stored price for {missing}.")
    # A holding with too little history is counted in the money and left out of the
    # risk figures, which then describe the rest. Nothing stands in for it.
    history = panel.returns[symbols].notna().sum()
    short = [h for h in holdings if int(history[h.symbol]) < model.MIN_YOUNG]
    young = [h for h in holdings if model.MIN_YOUNG <= int(history[h.symbol]) < model.MIN_HISTORY]
    short_value = {h.symbol: h.quantity * float(priced[h.symbol]) for h in short}
    everything = holdings
    holdings = [h for h in holdings if h not in short and h not in young]
    if not holdings:
        raise model.NotEnoughHistoryError(
            f"None of the holdings has {model.MIN_HISTORY} sessions of price history yet."
        )
    symbols = [h.symbol for h in holdings]
    prices = panel.prices[symbols]
    values = np.array([h.quantity * float(priced[h.symbol]) for h in holdings])
    # Cash is part of the money and none of the risk: the weights of the priced
    # holdings add up to less than one by exactly the share held in cash.
    young_symbols = [h.symbol for h in young]
    young_values = np.array([h.quantity * float(priced[h.symbol]) for h in young])
    total = float(values.sum()) + float(young_values.sum()) + cash
    weights = values / total
    young_weights = young_values / total
    cash_weight = cash / total
    returns = panel.returns[symbols]

    grand_total = total + sum(short_value.values())
    mix = model.mix_returns(returns, weights)
    xray = model.xray(returns, weights, panel.returns[young_symbols], young_weights)
    # The limits are measured on the holdings with a long record, then scaled by how
    # much the newer ones add to the mix's swings.
    lift = (
        xray.daily_volatility / xray.established_volatility
        if young and xray.established_volatility > 0
        else 1.0
    )
    limits = model.scale_limits(model.loss_limits(mix, min_window=min_window), lift)
    reference_symbols = [s for s in REFERENCES if s in panel.returns.columns]
    level = (
        model.risk_level(mix, panel.returns[reference_symbols], STOCKS)
        if STOCKS in reference_symbols
        else None
    )
    if level is not None:
        level = model.scale_level(level, lift)
    prices = panel.prices[symbols + young_symbols]
    weights_all = np.concatenate([weights, young_weights])
    episodes = [
        model.Episode(name=e.name, start=e.start, end=e.end) for e in universe.stress_episodes
    ]
    # Through a past episode cash is always there and never changes.
    if cash > 0:
        stress = model.stress(
            prices.assign(**{CASH: 1.0}), np.append(weights_all, cash_weight), episodes
        )
        xray = xray.model_copy(
            update={
                "holdings": [
                    *xray.holdings,
                    model.HoldingRisk(
                        symbol=CASH, weight=cash_weight, daily_volatility=0.0, risk_share=0.0
                    ),
                ]
            }
        )
    else:
        stress = model.stress(prices, weights_all, episodes)

    # Holdings left alone for 30 and 90 sessions, drawn from their joint record.
    # Newer holdings are not in that record: every path is widened for them.
    simulation = (
        simulation_model.run(returns.dropna().to_numpy(dtype=float), weights, total, scale=lift)
        if with_simulation
        else None
    )
    sleeves = sleeve_model.report(
        xray.holdings,
        {h.symbol: h.tag for h in everything if h.tag},
        panel.returns[symbols + young_symbols],
        CASH,
    )

    day = next((h for h in limits if h.horizon_days == 1), None)
    shown = (
        [
            {
                "reliable": m.backtest.reliable,
                "n": m.backtest.n,
                "breaches": m.backtest.breaches,
                "expected_breaches": m.backtest.expected_breaches,
            }
            for level in day.levels
            for m in level.methods
            if m.method == day.shown
        ]
        if day
        else []
    )
    available = [s for s in stress if s.available]

    # The same driver regression as for a single market, with the mix as the target.
    chosen = [s for s in DRIVER_SYMBOLS if s in panel.returns.columns]
    drivers = None
    if with_drivers and len(chosen) >= 2:
        frame = panel.returns[chosen].copy()
        frame[MIX] = mix
        baseline = "SPY" if "SPY" in chosen else chosen[0]
        drivers = driver_model.analyse(frame, MIX, chosen, baseline, DRIVER_WINDOW)
    score = drivers.out_of_sample if drivers else None
    return Analysis(
        as_of=pd.Timestamp(panel.prices.index[-1]).to_pydatetime(),
        model_version=model.MODEL_VERSION,
        value=grand_total,
        covered_value=total,
        unmeasured=[
            Unmeasured(
                symbol=h.symbol,
                name=universe.get(h.symbol).name,
                weight=short_value[h.symbol] / grand_total,
                days=int(history[h.symbol]),
            )
            for h in short
        ],
        young=[
            Unmeasured(
                symbol=h.symbol,
                name=universe.get(h.symbol).name,
                weight=float(young_values[i]) / grand_total,
                days=int(history[h.symbol]),
            )
            for i, h in enumerate(young)
        ],
        risk_level=level,
        positions=[
            Position(
                symbol=h.symbol,
                name=universe.get(h.symbol).name,
                quantity=h.quantity,
                tag=h.tag,
                price=float(priced[h.symbol]),
                value=h.quantity * float(priced[h.symbol]),
                weight=h.quantity * float(priced[h.symbol]) / grand_total,
            )
            for h in everything
        ]
        + (
            [
                Position(
                    symbol=CASH,
                    name=CASH_NAME,
                    quantity=cash,
                    tag=None,
                    price=1.0,
                    value=cash,
                    weight=cash / grand_total,
                )
            ]
            if cash > 0
            else []
        ),
        xray=xray,
        limits=limits,
        stress=stress,
        drivers=drivers,
        driver_names={s: universe.get(s).name for s in chosen} if drivers else {},
        simulation=simulation,
        sleeves=sleeves,
        trust=Trusts(
            simulation=_grade_simulation(simulation),
            drivers=summary.grade_drivers(
                {
                    "n_days": score.n_days,
                    "r_squared": score.r_squared,
                    "baseline_r_squared": score.baseline_r_squared,
                }
            )
            if score
            else None,
            xray=summary.grade_xray(xray.n_days, len(young)),
            risk=summary.grade_risk(shown),  # type: ignore[arg-type]
            stress=summary.grade_stress(
                len(available), sum(1 for s in available if s.missing), len(stress)
            ),
        ),
    )


def _grade_simulation(simulation: simulation_model.Simulation | None) -> summary.Trust | None:
    """Graded on the shortest horizon, which has the most past ranges to judge by."""
    if simulation is None:
        return None
    horizon = simulation.horizons[0]
    checked = next(c for c in horizon.coverage if c.level == summary.SIMULATION_LEVEL)
    return summary.grade_simulation(checked.n, checked.inside, checked.level, horizon.summary.steps)


def refresh(session: Session, universe: Universe, panel: MixedPanel | None = None) -> str | None:
    """Recompute and store the analysis of the saved holdings. Does not commit.

    Returns None on success, or one sentence saying why there is no analysis.
    """
    _, holdings = stored_holdings(session)
    session.execute(delete(PortfolioAnalysis).where(PortfolioAnalysis.portfolio_id == PORTFOLIO_ID))
    if not holdings:
        return "There are no holdings yet."
    panel = panel or build_mixed_panel(session, universe)
    try:
        result = analyse(holdings, panel, universe)
    except model.NotEnoughHistoryError as error:
        return str(error)
    states = holding_states(session, result, panel, universe)
    plan = None
    if result.risk_level is not None:
        plan = rebalance.build(
            result.xray,
            result.risk_level,
            [y.symbol for y in result.young],
            {s.symbol: s.label for s in states},
            result.covered_value,
            panel,
            stored_target(session),
        )
    result = result.model_copy(update={"states": states, "plan": plan})
    session.add(
        PortfolioAnalysis(
            portfolio_id=PORTFOLIO_ID,
            as_of=result.as_of,
            computed_at=datetime.now(UTC),
            model_version=result.model_version,
            payload=result.model_dump(mode="json"),
        )
    )
    return None


def holding_states(
    session: Session, analysis: Analysis, panel: MixedPanel, universe: Universe
) -> list[HoldingState]:
    """The filtered market state behind each holding, where a regime model exists."""
    from radar.pipelines.relationships import regime_labels

    closes = pd.DatetimeIndex(panel.prices.index[-1:])
    primary = {a.symbol for a in universe.primary}
    states = []
    for position in analysis.positions:
        market = STATE_OF.get(position.symbol, position.symbol)
        if market not in primary:
            continue
        label = regime_labels(session, market, closes).iloc[-1]
        if isinstance(label, str):
            states.append(
                HoldingState(
                    symbol=position.symbol, market=market, label=label, weight=position.weight
                )
            )
    return states


class WhatIf(BaseModel):
    """The risk of a mix the user is trying out, at the portfolio's current value."""

    value: float
    # Each holding's share of the whole, cash included, as understood.
    weights: dict[str, float]
    names: dict[str, str]
    # The mix's daily movement, and that as a multiple of US stocks' with its level.
    daily_volatility: float
    ratio: float | None
    level: str | None
    # Loss limits over one day as shares of the value: passed about 1 day in 20, and 1 in 100.
    limit_95: float | None
    limit_99: float | None
    deepest_fall: float
    risk_shares: dict[str, float]
    n_days: int
    # Newer holdings estimated on a short record, and any left out of the risk figures.
    young: list[Unmeasured]
    unmeasured: list[Unmeasured]


def what_if(
    weights: dict[str, float], value: float, panel: MixedPanel, universe: Universe
) -> WhatIf:
    """The risk figures for a mix given as shares of the whole.

    The shares are turned into quantities at the latest prices and analysed exactly as
    saved holdings are, so the figures are comparable with the other tabs. Whatever the
    shares leave over is held as cash.
    """
    known = {a.symbol for a in universe.assets}
    shares = {s: float(w) for s, w in weights.items() if s != CASH and w > 0}
    unknown = sorted(set(shares) - known)
    if unknown:
        raise ValueError(f"RADAR has no price history for {', '.join(unknown)}.")
    total = sum(shares.values())
    if total > 1.0 + 1e-6:
        raise ValueError("The shares add up to more than 100%.")
    latest = panel.prices[list(shares)].ffill().iloc[-1] if shares else pd.Series(dtype=float)
    if latest.isna().any():
        raise ValueError("One of these has no stored price yet.")
    holdings = [Holding(symbol=s, quantity=w * value / float(latest[s])) for s, w in shares.items()]
    cash = max(0.0, 1.0 - total) * value
    if cash > 0:
        holdings.append(Holding(symbol=CASH, quantity=cash))
    result = analyse(holdings, panel, universe, with_drivers=False, with_simulation=False)
    day = next((h for h in result.limits if h.horizon_days == 1), None)

    def limit(level: float) -> float | None:
        if day is None:
            return None
        row = next((x for x in day.levels if x.level == level), None)
        found = next((m for m in row.methods if m.method == day.shown), None) if row else None
        return None if found is None else found.var * result.covered_value / result.value

    return WhatIf(
        value=result.value,
        weights={p.symbol: p.weight for p in result.positions},
        names={p.symbol: p.name for p in result.positions},
        daily_volatility=result.xray.daily_volatility * result.covered_value / result.value,
        ratio=None if result.risk_level is None else result.risk_level.ratio,
        level=None if result.risk_level is None else result.risk_level.label,
        limit_95=limit(0.95),
        limit_99=limit(0.99),
        deepest_fall=result.xray.deepest_fall.depth,
        risk_shares={h.symbol: h.risk_share for h in result.xray.holdings},
        n_days=result.xray.n_days,
        young=result.young,
        unmeasured=result.unmeasured,
    )


class RegularBuying(BaseModel):
    """A plan of regular purchases run through simulated futures. Nothing is saved."""

    # How each purchase is split, by symbol, and the names to show.
    weights: dict[str, float]
    names: dict[str, str]
    first_day: str
    last_day: str
    result: buying_model.Result
    trust: summary.Trust


def regular_buying(
    weights: dict[str, float],
    amount: float,
    every: int,
    purchases: int,
    panel: MixedPanel,
    universe: Universe,
) -> RegularBuying:
    """Simulate buying `amount` every `every` sessions, `purchases` times, split by
    `weights`. Raises ValueError with the reason when it cannot be done."""
    known = {a.symbol for a in universe.assets}
    shares = {s: float(w) for s, w in weights.items() if w > 0}
    unknown = sorted(set(shares) - known)
    if unknown:
        raise ValueError(f"RADAR has no price history for {', '.join(unknown)}.")
    total = sum(shares.values())
    if not shares or total <= 0:
        raise ValueError("Give at least one asset a share.")
    symbols = list(shares)
    # Name the asset that is too new, so the user knows which one to take out.
    history = panel.returns[symbols].notna().sum()
    short = [s for s in symbols if int(history[s]) < buying_model.MIN_DAYS]
    if short:
        named = ", ".join(
            f"{universe.get(s).name} ({int(history[s])} days of prices)" for s in short
        )
        raise ValueError(
            f"Too new to simulate: {named}. {buying_model.MIN_DAYS} days are needed; "
            "take it out to run the plan."
        )
    joint = panel.returns[symbols].dropna()
    split = np.array([shares[s] / total for s in symbols])
    result = buying_model.run(joint.to_numpy(dtype=float), split, amount, every, purchases)
    checked = next(c for c in result.coverage if c.level == summary.SIMULATION_LEVEL)
    days = pd.DatetimeIndex(joint.index)
    return RegularBuying(
        weights={s: float(w) for s, w in zip(symbols, split, strict=True)},
        names={s: universe.get(s).name for s in symbols},
        first_day=days[0].date().isoformat(),
        last_day=days[-1].date().isoformat(),
        result=result,
        trust=summary.grade_simulation(checked.n, checked.inside, checked.level, result.sessions),
    )


def stored_target(session: Session) -> rebalance.Target | None:
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    if portfolio is None or not portfolio.target:
        return None
    return rebalance.Target.model_validate(portfolio.target)


def set_target(session: Session, target: rebalance.Target | None) -> bool:
    """Store or clear the target. Returns False when there is no portfolio yet."""
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    if portfolio is None:
        return False
    portfolio.target = None if target is None else target.model_dump(mode="json")
    return True


def set_tags(session: Session, tags: dict[str, str | None]) -> bool:
    """Tag holdings as core or satellite, or clear a tag with None. Symbols not
    named keep the tag they have. Returns False when there is no portfolio yet."""
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    if portfolio is None:
        return False
    merged = {**portfolio.tags, **tags}
    kept = {symbol: tag for symbol, tag in merged.items() if tag}
    portfolio.tags = kept
    for row in session.scalars(
        select(PortfolioHolding).where(PortfolioHolding.portfolio_id == PORTFOLIO_ID)
    ):
        row.tag = kept.get(row.symbol)
    return True


def stored_wallets(session: Session) -> list[dict[str, Any]]:
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    return list(portfolio.wallets) if portfolio is not None else []


def stored_leveraged(session: Session) -> list[dict[str, Any]]:
    portfolio = session.get(Portfolio, PORTFOLIO_ID)
    return list(portfolio.leveraged) if portfolio is not None else []


def stored_analysis(session: Session) -> Analysis | None:
    row = session.get(PortfolioAnalysis, PORTFOLIO_ID)
    return None if row is None else Analysis.model_validate(row.payload)


Reader = Callable[[Universe], BinanceReading]
# Looks up unknown holdings names and registers the ones it finds.
Finder = Callable[[Universe, list[str]], list[Any]]


def read_exchange(
    session: Session, universe: Universe, reader: Reader, finder: Finder | None
) -> tuple[BinanceReading, Universe]:
    """Read the exchange; if it holds something unknown, find it and read again.

    Returns the reading and the universe it was resolved against, which includes any
    asset discovered on the way.
    """
    reading = reader(universe)
    unknown = [u.symbol for u in reading.holdings.unsupported if u.reason == NO_HISTORY]
    if unknown and finder is not None and finder(universe, unknown):
        universe = discover.extend(universe, session)
        reading = reader(universe)
    return reading, universe


def run(
    engine: Engine,
    universe: Universe,
    reader: Reader | None = None,
    finder: Finder | None = None,
) -> int:
    """Refresh the stored analysis with the latest prices. Returns 1 when one was stored."""
    with Session(engine) as session:
        universe = discover.extend(universe, session)
        source, _ = stored_holdings(session)
        if source == "binance" and reader is not None:
            # Holdings on an exchange change; read them again before analysing.
            try:
                reading, universe = read_exchange(session, universe, reader, finder)
                store(
                    session,
                    reading.holdings,
                    [p.model_dump() for p in reading.leveraged],
                    [w.model_dump() for w in reading.wallets],
                )
            except BinanceError as error:
                log.warning("portfolio_binance_read_failed", reason=str(error))
        problem = refresh(session, universe)
        session.commit()
    if problem:
        log.info("portfolio_skipped", reason=problem)
        return 0
    log.info("portfolio_done")
    return 1


def binance_reader() -> Reader | None:
    """A function that reads the Binance account, or None when no key is configured."""
    settings = load_settings()
    key, secret = settings.binance_api_key, settings.binance_api_secret
    if key is None or secret is None:
        return None

    def read(universe: Universe) -> BinanceReading:
        source = BinanceSource(key, secret, [a.symbol for a in universe.assets])
        try:
            return source.read_account()
        finally:
            source.close()

    return read


def asset_finder(engine: Engine) -> Finder | None:
    """A function that discovers unknown holdings through Alpaca's market data, or None
    when no Alpaca key is configured."""
    settings = load_settings()
    key, secret = settings.alpaca_api_key_id, settings.alpaca_api_secret_key
    if key is None or secret is None:
        return None

    def find(universe: Universe, names: list[str]) -> list[Any]:
        with AlpacaDataClient(key, secret) as client:
            return list(discover.discover(client, engine, universe, names))

    return find
