"""Load stored bars into the frames the feature builders take. All I/O lives here."""

from collections.abc import Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.db.models import Bar
from radar.features.calendars import nyse_schedule, session_of
from radar.features.panels import MixedPanel, crypto_panel, mixed_panel
from radar.features.returns import log_returns
from radar.features.volatility import (
    realised_volatility_crypto,
    realised_volatility_stock,
    smoothed_log_volatility,
)
from radar.universe import Asset, Universe


def load_field(
    session: Session, symbols: Sequence[str], timeframe: str, field: str = "close"
) -> pd.DataFrame:
    """One column per symbol, indexed by bar start (UTC)."""
    rows = session.execute(
        select(Bar.ts, Bar.symbol, getattr(Bar, field))
        .where(Bar.symbol.in_(symbols), Bar.timeframe == timeframe)
        .order_by(Bar.ts)
    ).all()
    frame = pd.DataFrame(rows, columns=["ts", "symbol", field])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    wide = frame.pivot(index="ts", columns="symbol", values=field)
    wide.columns.name = None
    return wide.reindex(columns=list(symbols))


def stock_daily(session: Session, symbols: Sequence[str], field: str = "close") -> pd.DataFrame:
    """Stock daily values indexed by session date instead of the midnight stamp."""
    frame = load_field(session, symbols, "1Day", field)
    frame.index = session_of(pd.DatetimeIndex(frame.index))
    return frame


def build_crypto_panel(session: Session, universe: Universe) -> pd.DataFrame:
    symbols = [a.symbol for a in universe.of_class("crypto")]
    return crypto_panel(load_field(session, symbols, "1Day"))


def build_mixed_panel(session: Session, universe: Universe) -> MixedPanel:
    stocks = stock_daily(session, [a.symbol for a in universe.of_class("stock")])
    crypto = load_field(session, [a.symbol for a in universe.of_class("crypto")], "1Hour")
    first = stocks.index.min().tz_localize("America/New_York").tz_convert("UTC")
    last = min(
        stocks.index.max().tz_localize("America/New_York").tz_convert("UTC") + pd.Timedelta(days=1),
        crypto.index.max() + pd.Timedelta(hours=1)
        if len(crypto)
        else pd.Timestamp.max.tz_localize("UTC"),
    )
    return mixed_panel(stocks, crypto, nyse_schedule(first, last))


def build_realised_volatility(session: Session, asset: Asset) -> pd.DataFrame:
    hourly = load_field(session, [asset.symbol], "1Hour")[asset.symbol].dropna()
    if asset.asset_class == "crypto":
        return realised_volatility_crypto(hourly)
    daily = pd.DataFrame(
        {
            "open": stock_daily(session, [asset.symbol], "open")[asset.symbol],
            "close": stock_daily(session, [asset.symbol], "close")[asset.symbol],
        }
    )
    first = daily.index.min().tz_localize("America/New_York").tz_convert("UTC")
    last = daily.index.max().tz_localize("America/New_York").tz_convert("UTC") + pd.Timedelta(
        days=1
    )
    return realised_volatility_stock(hourly, daily, nyse_schedule(first, last))


def build_regime_observations(session: Session, asset: Asset) -> pd.DataFrame:
    """Daily inputs for the regime model: `ret`, `log_rv`, and the raw `rv`.

    One row per completed day (UTC day for crypto, trading session for stocks), indexed
    by that day. `log_rv` is log realised volatility smoothed over about five days,
    trailing only. Days without a realised-volatility value are left out, not filled.
    """
    volatility = build_realised_volatility(session, asset)["rv"]
    if asset.asset_class == "crypto":
        close = load_field(session, [asset.symbol], "1Day")[asset.symbol].dropna()
        returns = log_returns(close, step=pd.Timedelta(days=1))
    else:
        close = stock_daily(session, [asset.symbol])[asset.symbol].dropna()
        returns = log_returns(close)
    frame = pd.DataFrame({"ret": returns, "rv": volatility}).dropna()
    frame = frame[frame["rv"] > 0]
    frame["log_rv"] = smoothed_log_volatility(frame["rv"])
    return frame[["ret", "log_rv", "rv"]]
