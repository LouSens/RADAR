"""The account's record, built from the exchange's own history and stored.

Reads every purchase, sale, swap, arrival, departure and reward the read-only Binance
key can list, turns them into entries, sets each trade beside the prices around it, and
stores one result for the Portfolio screen: what each holding cost, what was made, how
trading compared with holding, and how the trades were timed.

The history is read again in full on every run, so a run cannot leave the record half
updated, and running twice gives the same result. Hourly prices come from Binance's
public market data and are kept in the gitignored `data/account/`, extended each run.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.analytics import trading
from radar.config import load_settings
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import ledger
from radar.models.ledger import Entry
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines import relationships
from radar.providers import binance_public
from radar.providers.binance import BinanceError
from radar.providers.binance_history import BinanceHistory
from radar.providers.public import PublicDataError, PublicReader

log = get_logger(__name__)

NAME = "account_record"
VERSION = "account-1"
STORE = Path("data/account")
SINCE = datetime(2017, 8, 1, tzinfo=UTC)
WINDOW = timedelta(days=30)
# Binance has no list of everything an account ever traded, so each coin has to be asked
# about by name. These widely traded coins are always asked about; others are found
# from the account's own swaps, rewards and holdings. A coin outside both is missed.
COMMON = (
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "PAXG",
    "MANTA",
    "ADA",
    "AVAX",
    "LINK",
    "DOT",
    "MATIC",
    "POL",
    "LTC",
    "TRX",
    "SHIB",
    "PEPE",
    "WIF",
    "BONK",
    "FLOKI",
    "ARB",
    "OP",
    "SUI",
    "APT",
    "SEI",
    "TIA",
    "INJ",
    "NEAR",
    "ATOM",
    "FIL",
    "ICP",
    "ETC",
    "XLM",
    "HBAR",
    "VET",
    "ALGO",
    "AAVE",
    "UNI",
    "MKR",
    "CRV",
    "LDO",
    "SNX",
    "COMP",
    "SUSHI",
    "CAKE",
    "RUNE",
    "GRT",
    "FET",
    "RNDR",
    "RENDER",
    "TAO",
    "WLD",
    "JUP",
    "PYTH",
    "JTO",
    "STRK",
    "ZK",
    "ZRO",
    "EIGEN",
    "ENA",
    "ETHFI",
    "PENDLE",
    "ONDO",
    "W",
    "ALT",
    "PIXEL",
    "PORTAL",
    "AEVO",
    "DYM",
    "XAI",
    "ACE",
    "NFP",
    "AI",
    "SAGA",
    "OMNI",
    "REZ",
    "BB",
    "NOT",
    "IO",
    "LISTA",
    "BANANA",
    "TON",
    "DOGS",
    "HMSTR",
    "CATI",
    "NEIRO",
    "SCR",
    "MOVE",
    "ME",
    "PENGU",
    "TRUMP",
    "MELANIA",
    "BERA",
    "LAYER",
    "KAITO",
    "XVG",
    "OM",
    "PHB",
    "ZEC",
    "BCH",
    "EOS",
    "XMR",
    "DASH",
    "NEO",
    "IOTA",
    "QTUM",
    "ZIL",
    "ENJ",
    "SAND",
    "MANA",
    "AXS",
    "GALA",
    "APE",
    "CHZ",
    "FTM",
    "S",
    "KAS",
    "ORDI",
    "SATS",
    "1000SATS",
    "BOME",
    "MEME",
    "PEOPLE",
    "LUNC",
    "LUNA",
    "USTC",
    "GMT",
    "GMX",
    "DYDX",
    "BLUR",
    "IMX",
    "STX",
    "MINA",
    "ROSE",
    "KAVA",
    "CFX",
    "ID",
    "MAGIC",
    "HOOK",
    "EDU",
    "MAV",
    "ARKM",
    "CYBER",
    "NTRN",
    "TURBO",
    "WBETH",
    "PURR",
    "HYPE",
    "VIRTUAL",
    "AIXBT",
    "ANIME",
)
QUOTES = ("USDT", "USDC", "FDUSD")
# Windows with nothing in them, in a row, after which looking further back stops.
QUIET_WINDOWS = 12
HOUR_MS = 3_600_000
# Seconds between requests for fills.
PAUSE = 0.2
# A coin is a holding when what is held is worth at least this many dollars.
HELD_FROM = 1.0

Prices = Callable[[str, datetime, datetime], pd.DataFrame]


class Trips(BaseModel):
    """Round trips in one asset: from holding none, to some, to none again."""

    count: int
    ended_up: int
    average_gain: float | None
    average_loss: float | None
    days_when_up: float | None
    days_when_down: float | None
    total: float


class AssetRecord(BaseModel):
    asset: str
    standing: ledger.Standing
    price: float | None
    value: float | None
    unrealised: float | None
    compared: ledger.Compared | None
    trips: Trips | None
    buys: trading.Habit | None
    sells: trading.Habit | None
    usual: trading.Usual | None
    buys_unusual: bool
    sells_unusual: bool
    # Units held now according to the portfolio, and how far history is from them.
    held_units: float | None
    missing_share: float | None
    # Whether what is held is worth showing as a holding, and not a crumb.
    held: bool = False
    # Cost of units that history still shows but the account no longer has: moved,
    # withdrawn, or swapped in a way the trade history does not list.
    moved_out_cost: float = 0.0


class Month(BaseModel):
    month: str
    bought: float
    sold: float
    trades: int


class Record(BaseModel):
    as_of: AwareDatetime
    model_version: str
    first_trade: AwareDatetime | None
    trades: int
    realised: float
    unrealised: float
    fees: float
    put_in: float
    as_traded: float
    if_held: float
    assets: list[AssetRecord]
    months: list[Month]
    # Entries whose cost was taken from the market price of the day.
    priced_at_market: int
    # Cost of coins that left without a sale on record, over all coins.
    moved_out_cost: float = 0.0


def collect(
    history: BinanceHistory,
    assets: list[str],
    now: datetime,
    pause: float = PAUSE,
    listed: dict[str, list[str]] | None = None,
) -> list[Entry]:
    """Every entry the account's history gives, for `assets`, the common coins, and
    whatever else its swaps and rewards mention. `pause` is the wait between requests,
    which keeps a long scan inside the exchange's limits."""
    entries: list[Entry] = []
    likely = set(assets)
    # With the exchange's own list every coin it trades is asked about; the common
    # coins stay in for ones it has since stopped listing.
    names = likely | set(COMMON) | set(listed or {})
    quiet, end = 0, now
    while end > SINCE and quiet < QUIET_WINDOWS:
        start = end - WINDOW
        found = 0
        for swap in history.conversions(start, end):
            entries += ledger.from_conversion(
                swap.at, swap.from_asset, swap.from_quantity, swap.to_asset, swap.to_quantity
            )
            names |= {swap.from_asset, swap.to_asset}
            likely |= {swap.from_asset, swap.to_asset}
            found += 1
        for move in history.movements(start, end):
            entries.append(
                Entry(
                    at=move.at,
                    asset=move.asset,
                    kind="arrived" if move.arrived else "left",
                    units=move.quantity if move.arrived else -move.quantity,
                )
            )
            found += 1
        for reward in history.rewards(start, end):
            entries.append(
                Entry(at=reward.at, asset=reward.asset, kind="reward", units=reward.quantity)
            )
            names.add(reward.asset)
            likely.add(reward.asset)
            found += 1
        quiet = 0 if found else quiet + 1
        end = start
    for asset in sorted(names - ledger.CASH):
        quotes = (listed or {}).get(asset) or list(QUOTES)
        for quote in quotes:
            try:
                fills = history.fills(asset + quote)
            except BinanceError:
                fills = []  # no such pair
            time.sleep(pause)
            for fill in fills:
                entry = ledger.from_fill(
                    fill.pair,
                    fill.at,
                    fill.bought,
                    fill.quantity,
                    fill.amount,
                    fill.fee,
                    fill.fee_asset,
                )
                if entry is not None:
                    entries.append(entry)
            # Nearly every trade is against USDT: a coin never traded there is not asked
            # about against the other dollars, unless the account itself points to it.
            if quote == quotes[0] and not fills and asset not in likely:
                break
    return sorted(entries, key=lambda e: e.at)


def stored_prices(source: PublicReader, store: Path = STORE) -> Prices:
    """Hourly bars for an asset against USDT, from file and extended to now."""

    def load(asset: str, start: datetime, end: datetime) -> pd.DataFrame:
        target = store / "prices" / f"{asset}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        kept = pd.read_parquet(target) if target.exists() else None
        first = int(start.timestamp() * 1000)
        if kept is not None and len(kept) and kept.index[0] <= pd.Timestamp(start):
            first = int(kept.index[-1].timestamp() * 1000) + HOUR_MS
        else:
            kept = None
        fresh = binance_public.hourly_bars(
            source, asset + "USDT", first, int(end.timestamp() * 1000)
        )
        frames = [f for f in (kept, fresh) if f is not None and len(f)]
        if not frames:
            return pd.DataFrame(columns=binance_public.BAR_FIELDS)
        bars = pd.concat(frames)
        bars = bars[~bars.index.duplicated(keep="last")].sort_index()
        bars.to_parquet(target)
        return bars

    return load


def _trips(entries: list[Entry], asset: str) -> Trips | None:
    found = ledger.round_trips(entries, asset)
    if not found:
        return None
    up = [t for t in found if t.gain > 0]
    down = [t for t in found if t.gain <= 0]
    return Trips(
        count=len(found),
        ended_up=len(up),
        average_gain=float(np.mean([t.gain for t in up])) if up else None,
        average_loss=float(np.mean([t.gain for t in down])) if down else None,
        days_when_up=float(np.median([t.days for t in up])) if up else None,
        days_when_down=float(np.median([t.days for t in down])) if down else None,
        total=float(sum(t.gain for t in found)),
    )


def build(entries: list[Entry], prices: Prices, held: dict[str, float], now: datetime) -> Record:
    """The record from entries, hourly prices and the units held now."""
    traded = sorted({e.asset for e in entries if e.kind == "buy" and e.asset not in ledger.CASH})
    bars: dict[str, pd.DataFrame] = {}
    for asset in traded:
        first = min(e.at for e in entries if e.asset == asset)
        try:
            bars[asset] = prices(asset, first - timedelta(days=10), now)
        except Exception as error:  # a market that cannot be read is left out
            log.warning("account_prices_unavailable", asset=asset, error=type(error).__name__)

    def price_at(asset: str, at: datetime) -> float | None:
        frame = bars.get(asset)
        if frame is None or frame.empty:
            return None
        i = int(pd.DatetimeIndex(frame.index).searchsorted(pd.Timestamp(at), side="right")) - 1
        return float(frame["close"].iloc[i]) if i >= 0 else None

    standings = ledger.standing(entries, price_at)
    assets: list[AssetRecord] = []
    for asset in traded:
        from_history = standings[asset]
        now_standing, moved_out = (
            ledger.reconcile(from_history, held.get(asset, 0.0)) if held else (from_history, 0.0)
        )
        frame = bars.get(asset)
        price: float | None = None
        buys = sells = None
        typical = None
        buys_unusual = sells_unusual = False
        if frame is not None and len(frame):
            price = float(frame["close"].iloc[-1])
            context = trading.context(entries, frame, asset)
            buys, sells = trading.habit(context, "buy"), trading.habit(context, "sell")
            if now_standing.first is not None:
                typical = trading.usual(frame, pd.Timestamp(now_standing.first))
            buys_unusual = trading.place_is_unusual(context, "buy", frame)
            sells_unusual = trading.place_is_unusual(context, "sell", frame)
        cost = now_standing.average_cost
        value = None if price is None else now_standing.units * price
        assets.append(
            AssetRecord(
                asset=asset,
                standing=now_standing,
                price=price,
                value=value,
                unrealised=(
                    None if price is None or cost is None else (price - cost) * now_standing.units
                ),
                compared=None if price is None else ledger.against_holding(entries, asset, price),
                trips=_trips(entries, asset),
                buys=buys,
                sells=sells,
                usual=typical,
                buys_unusual=buys_unusual,
                sells_unusual=sells_unusual,
                held_units=held.get(asset),
                missing_share=(
                    ledger.missing_share(from_history.units, held[asset]) if asset in held else None
                ),
                held=value is not None and value >= HELD_FROM,
                moved_out_cost=moved_out,
            )
        )
    assets.sort(key=lambda a: a.standing.bought, reverse=True)
    trades = [e for e in entries if e.kind in ("buy", "sell") and e.asset not in ledger.CASH]
    by_month: dict[str, Month] = {}
    for entry in trades:
        key = entry.at.strftime("%Y-%m")
        month = by_month.setdefault(key, Month(month=key, bought=0.0, sold=0.0, trades=0))
        month.trades += 1
        if entry.kind == "buy":
            month.bought += entry.dollars or 0.0
        else:
            month.sold += entry.dollars or 0.0
    compared = [a.compared for a in assets if a.compared is not None]
    return Record(
        as_of=now,
        model_version=VERSION,
        first_trade=trades[0].at if trades else None,
        trades=len(trades),
        realised=sum(a.standing.realised for a in assets),
        unrealised=sum(a.unrealised or 0.0 for a in assets),
        fees=sum(a.standing.fees for a in assets),
        put_in=sum(c.put_in for c in compared),
        as_traded=sum(c.as_traded for c in compared),
        if_held=sum(c.if_held for c in compared),
        assets=assets,
        months=[by_month[key] for key in sorted(by_month)],
        priced_at_market=sum(a.standing.priced_at_market for a in assets),
        moved_out_cost=sum(a.moved_out_cost for a in assets),
    )


def held_units(session: Session) -> dict[str, float]:
    """Units of each crypto asset the stored portfolio says are held now."""
    analysis = portfolio_job.stored_analysis(session)
    if analysis is None:
        return {}
    return {
        position.symbol.split("/")[0]: position.quantity
        for position in analysis.positions
        if "/" in position.symbol
    }


def stored(session: Session) -> Record | None:
    row = relationships.current(session, NAME, None)
    return None if row is None else Record.model_validate(row.metrics)


def run(engine: Engine, now: datetime | None = None) -> int:
    """Read the history, build the record and store it. Returns 1 when stored, 0 when
    no Binance key is configured or the account has no trades."""
    settings = load_settings()
    key, secret = settings.binance_api_key, settings.binance_api_secret
    if key is None or secret is None:
        log.info("account_record_skipped", reason="no Binance key")
        return 0
    now = now or datetime.now(UTC)
    with session_scope(engine) as session:
        held = held_units(session)
    try:
        with binance_public.reader() as source:
            listed = binance_public.dollar_pairs(source, QUOTES)
    except PublicDataError:
        listed = None  # the common coins are still asked about
    history = BinanceHistory(key, secret)
    try:
        entries = collect(history, sorted(held), now, listed=listed)
    finally:
        history.close()
    with binance_public.reader() as source:
        record = build(entries, stored_prices(source), held, now)
    if record.trades == 0 or record.first_trade is None:
        log.info("account_record_skipped", reason="no trades")
        return 0
    with session_scope(engine) as session:
        relationships._store(
            session,
            NAME,
            None,
            VERSION,
            record.model_dump(mode="json"),
            record.first_trade.date(),
            now.date(),
        )
    log.info("account_record_stored", trades=record.trades, assets=len(record.assets))
    return 1
