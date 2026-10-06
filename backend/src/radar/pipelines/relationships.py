"""How the markets move together (spec F5, F8, and decision 035). All I/O lives here.

Two stored results, both kept as rows in `model_registry` so that requests only read:

- `relationships` (one row): correlations between the primary markets, the grid across
  the whole universe, risk transmission, and weekend gaps.
- `drivers` (one row per primary market): the macro driver regression.
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from radar.analytics import correlation, summary, transmission
from radar.db.models import ModelRegistry, RegimeState
from radar.db.session import session_scope
from radar.features.calendars import nyse_schedule
from radar.features.panels import MixedPanel
from radar.logging import get_logger
from radar.models import drivers as driver_model
from radar.models import evidence
from radar.pipelines.datasets import build_mixed_panel, load_field, stock_daily
from radar.pipelines.regime import current_model as current_regime_model
from radar.universe import Universe

log = get_logger(__name__)

NAME = "relationships"
VERSION = "relationships-1"
DRIVERS_NAME = "drivers"
BITCOIN = "BTC/USD"
# Funds that stand for outside forces (spec F8), in the order shown.
DRIVER_SYMBOLS = ("SPY", "UUP", "TLT", "TIP", "VIXY")
SERIES_POINTS = 500
RECENT = 90
GRID_MIN_DAYS = 250
# A regime label older than this is not carried forward to a session.
LABEL_MAX_AGE = pd.Timedelta(days=4)
HOUR = pd.Timedelta(hours=1)


class PairPoint(BaseModel):
    day: date
    rolling_30: float | None
    rolling_90: float | None
    weighted: float | None


class Pair(BaseModel):
    a: str
    b: str
    # Latest readings: trailing 30 and 90 sessions, and the fast-adapting estimate.
    current_30: float | None
    current_90: float | None
    current_weighted: float | None
    # 95% range for the 90-session reading.
    low_90: float | None
    high_90: float | None
    # Over every session both have a return for.
    full: float
    n_days: int
    first_day: date
    last_day: date
    series: list[PairPoint]
    # Whose regime the table below is split by.
    regime_of: str
    by_regime: list[correlation.RegimeCorrelation]
    trust: summary.Trust


class WeekendNow(BaseModel):
    """Bitcoin's move since stock markets last closed, while they are shut."""

    since: AwareDatetime
    as_of: AwareDatetime
    bitcoin_move: float


class Relationships(BaseModel):
    as_of: AwareDatetime
    pairs: list[Pair]
    grid_recent: correlation.Grid | None
    grid_full: correlation.Grid | None
    spillovers: list[transmission.Spillover]
    spillover_trust: summary.Trust
    weekends: list[transmission.WeekendGap]
    weekend_now: WeekendNow | None
    weekend_trust: summary.Trust


def regime_labels(session: Session, symbol: str, closes: pd.DatetimeIndex) -> pd.Series:
    """The filtered regime label known at each session's close. NaN where none is recent."""
    registered = current_regime_model(session, symbol)
    if registered is None:
        return pd.Series(np.nan, index=closes, dtype=object)
    rows = session.execute(
        select(RegimeState.ts, RegimeState.label)
        .where(RegimeState.symbol == symbol, RegimeState.model_id == registered.id)
        .order_by(RegimeState.ts)
    ).all()
    if not rows:
        return pd.Series(np.nan, index=closes, dtype=object)
    known = pd.DataFrame(
        {
            "ts": pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], utc=True)).as_unit("ns"),
            "label": [r[1] for r in rows],
        }
    )
    wanted = pd.DataFrame({"close": closes.as_unit("ns")})
    matched = pd.merge_asof(
        wanted, known, left_on="close", right_on="ts", direction="backward", tolerance=LABEL_MAX_AGE
    )
    return pd.Series(matched["label"].to_numpy(), index=closes, dtype=object)


def _last(series: pd.Series) -> float | None:
    known = series.dropna()
    return None if known.empty else float(known.iloc[-1])


def pair(a: str, b: str, returns: pd.DataFrame, labels: pd.Series, regime_of: str) -> Pair | None:
    both = returns[[a, b]].dropna()
    if len(both) < correlation.WINDOWS[-1]:
        return None
    r30 = correlation.rolling(both[a], both[b], 30)
    r90 = correlation.rolling(both[a], both[b], 90)
    fast = correlation.weighted(both[a], both[b])
    days = pd.DatetimeIndex(both.index).tz_convert("America/New_York")
    tail = slice(max(len(both) - SERIES_POINTS, 0), len(both))
    current_90 = _last(r90)
    low, high = correlation.interval(current_90, 90) if current_90 is not None else (None, None)

    def at(series: pd.Series, i: int) -> float | None:
        value = series.iloc[i]
        return None if pd.isna(value) else float(value)

    return Pair(
        a=a,
        b=b,
        current_30=_last(r30),
        current_90=current_90,
        current_weighted=_last(fast),
        low_90=low,
        high_90=high,
        full=float(np.corrcoef(both[a], both[b])[0, 1]),
        n_days=len(both),
        first_day=days[0].date(),
        last_day=days[-1].date(),
        series=[
            PairPoint(
                day=days[i].date(),
                rolling_30=at(r30, i),
                rolling_90=at(r90, i),
                weighted=at(fast, i),
            )
            for i in range(tail.start, tail.stop)
        ],
        regime_of=regime_of,
        by_regime=correlation.by_regime(both[a], both[b], labels.reindex(both.index)),
        trust=summary.grade_relationship(len(both)),
    )


def weekend_moves(
    session: Session, panel: MixedPanel, symbols: list[str]
) -> tuple[pd.Series, pd.DataFrame, WeekendNow | None]:
    """Bitcoin's move from the last close to each post-weekend open, and each market's gap.

    A weekend is any break of three or more calendar days between sessions, so a holiday
    Monday is included. Bitcoin's price at the open is the last hourly close at or before
    it, so nothing later than the open is used.
    """
    closes = pd.DatetimeIndex(panel.prices.index)
    schedule = nyse_schedule(closes[0], closes[-1]).reindex(panel.sessions)
    opens = pd.DatetimeIndex(schedule["open"]).tz_convert("UTC")
    after_break = np.concatenate(
        [[False], (panel.sessions[1:] - panel.sessions[:-1]) >= pd.Timedelta(days=3)]
    )
    hourly = load_field(session, [BITCOIN], "1Hour")[BITCOIN].dropna()
    ends = pd.DataFrame(
        {
            "end": (pd.DatetimeIndex(hourly.index) + HOUR).as_unit("ns"),
            "price": hourly.to_numpy(dtype=float),
        }
    )
    at_open = pd.merge_asof(
        pd.DataFrame({"open": opens.as_unit("ns")}),
        ends,
        left_on="open",
        right_on="end",
        direction="backward",
        tolerance=pd.Timedelta(hours=6),
    )["price"].to_numpy(dtype=float)
    previous_close = panel.prices[BITCOIN].shift(1).to_numpy(dtype=float)
    bitcoin = pd.Series(np.log(at_open / previous_close), index=closes)[after_break]

    stock_open = stock_daily(session, symbols, "open").reindex(panel.sessions)
    stock_close = panel.prices[symbols]
    gaps = pd.DataFrame(
        np.log(stock_open.to_numpy(dtype=float) / stock_close.shift(1).to_numpy(dtype=float)),
        index=closes,
        columns=symbols,
    )[after_break]

    now = None
    if len(ends) and ends["end"].iloc[-1] - closes[-1] > pd.Timedelta(hours=2):
        last_price = float(ends["price"].iloc[-1])
        close_price = float(panel.prices[BITCOIN].iloc[-1])
        if not np.isnan(close_price):
            now = WeekendNow(
                since=closes[-1].to_pydatetime(),
                as_of=pd.Timestamp(ends["end"].iloc[-1]).to_pydatetime(),
                bitcoin_move=float(np.log(last_price / close_price)),
            )
    return bitcoin, gaps, now


def build(session: Session, universe: Universe, panel: MixedPanel | None = None) -> Relationships:
    panel = panel or build_mixed_panel(session, universe)
    returns = panel.returns
    closes = pd.DatetimeIndex(returns.index)
    primary = [a.symbol for a in universe.primary]
    labels = {symbol: regime_labels(session, symbol, closes) for symbol in primary}

    pairs = []
    for i, a in enumerate(primary):
        for b in primary[i + 1 :]:
            built = pair(a, b, returns, labels[a], a)
            if built:
                pairs.append(built)

    spillovers = [
        transmission.spillover(source, target, labels[source], returns[target], steps)
        for source in primary
        for target in primary
        if source != target
        for steps in transmission.HORIZONS
    ]
    adjusted = evidence.benjamini_hochberg([row.p_value for row in spillovers])
    spillovers = [
        transmission.spill_verdict(row, q) for row, q in zip(spillovers, adjusted, strict=True)
    ]

    weekends: list[transmission.WeekendGap] = []
    weekend_now = None
    stocks = [a.symbol for a in universe.primary if a.asset_class == "stock"]
    if BITCOIN in returns.columns and stocks:
        bitcoin, gaps, weekend_now = weekend_moves(session, panel, stocks)
        weekends = [transmission.weekend_gap(symbol, bitcoin, gaps[symbol]) for symbol in stocks]
        adjusted = evidence.benjamini_hochberg([row.p_value for row in weekends])
        weekends = [
            transmission.link_verdict(row, q) for row, q in zip(weekends, adjusted, strict=True)
        ]

    # A market with a short history would shrink the grid to its own few sessions.
    held = [
        a.symbol
        for a in universe.assets
        if a.symbol in returns.columns and returns[a.symbol].notna().sum() >= GRID_MIN_DAYS
    ]
    return Relationships(
        as_of=closes[-1].to_pydatetime(),
        pairs=pairs,
        grid_recent=correlation.grid(returns[held].tail(RECENT)),
        grid_full=correlation.grid(returns[held]),
        spillovers=spillovers,
        spillover_trust=summary.grade_spillovers([row.episodes for row in spillovers]),
        weekends=weekends,
        weekend_now=weekend_now,
        weekend_trust=summary.grade_weekends([row.weekends for row in weekends]),
    )


class Drivers(BaseModel):
    symbol: str
    as_of: AwareDatetime
    model_version: str
    # Names for the driver symbols, for display.
    names: dict[str, str]
    windows: list[driver_model.WindowResult]
    trust: summary.Trust


def build_drivers(
    symbol: str, panel: MixedPanel, universe: Universe, *, bootstraps: int = driver_model.BOOTSTRAPS
) -> Drivers | None:
    """The macro driver regression for one market (spec F8)."""
    known = {a.symbol: a.name for a in universe.assets}
    chosen = [s for s in DRIVER_SYMBOLS if s in panel.returns.columns and s != symbol]
    if len(chosen) < 2:
        return None
    # Stocks alone are the simple rival; for stocks themselves it is expected volatility.
    baseline = "SPY" if symbol != "SPY" and "SPY" in chosen else "VIXY"
    if baseline not in chosen:
        baseline = chosen[0]
    windows = [
        result
        for window in driver_model.WINDOWS
        if (
            result := driver_model.analyse(
                panel.returns, symbol, chosen, baseline, window, bootstraps=bootstraps
            )
        )
    ]
    if not windows:
        return None
    longest = windows[-1].out_of_sample
    return Drivers(
        symbol=symbol,
        as_of=pd.Timestamp(panel.returns.index[-1]).to_pydatetime(),
        model_version=driver_model.MODEL_VERSION,
        names={s: known[s] for s in chosen},
        windows=windows,
        trust=summary.grade_drivers(
            None
            if longest is None
            else {
                "n_days": longest.n_days,
                "r_squared": longest.r_squared,
                "baseline_r_squared": longest.baseline_r_squared,
            }
        ),
    )


def _store(
    session: Session,
    name: str,
    symbol: str | None,
    version: str,
    payload: dict[str, Any],
    first: date,
    last: date,
) -> None:
    session.execute(
        update(ModelRegistry)
        .where(
            ModelRegistry.name == name,
            ModelRegistry.symbol.is_(None) if symbol is None else ModelRegistry.symbol == symbol,
        )
        .values(is_current=False)
    )
    session.add(
        ModelRegistry(
            name=name,
            symbol=symbol,
            version=version,
            train_start=first,
            train_end=last,
            is_current=True,
            params={},
            metrics=payload,
        )
    )


def current(session: Session, name: str, symbol: str | None) -> ModelRegistry | None:
    return session.scalars(
        select(ModelRegistry)
        .where(
            ModelRegistry.name == name,
            ModelRegistry.symbol.is_(None) if symbol is None else ModelRegistry.symbol == symbol,
            ModelRegistry.is_current,
        )
        .order_by(ModelRegistry.trained_at.desc())
        .limit(1)
    ).first()


def run(engine: Engine, universe: Universe) -> int:
    """Recompute and store both results. Returns the number of rows stored."""
    stored = 0
    with session_scope(engine) as session:
        panel = build_mixed_panel(session, universe)
        first = panel.sessions[0].date()
        last = panel.sessions[-1].date()
        result = build(session, universe, panel)
        _store(session, NAME, None, VERSION, result.model_dump(mode="json"), first, last)
        stored += 1
        for asset in universe.primary:
            drivers = build_drivers(asset.symbol, panel, universe)
            if drivers is None:
                log.warning("drivers_skipped", symbol=asset.symbol)
                continue
            _store(
                session,
                DRIVERS_NAME,
                asset.symbol,
                driver_model.MODEL_VERSION,
                drivers.model_dump(mode="json"),
                first,
                last,
            )
            stored += 1
    log.info("relationships_stored", rows=stored)
    return stored
