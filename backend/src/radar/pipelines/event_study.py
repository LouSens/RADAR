"""Run the sentiment-versus-price study for each asset and store the result."""

from typing import Any

import pandas as pd
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from radar.analytics import event_study
from radar.db.models import ModelRegistry, RegimeState, SentimentAggregate
from radar.db.session import session_scope
from radar.features.calendars import NEW_YORK
from radar.features.returns import log_returns
from radar.logging import get_logger
from radar.pipelines.datasets import load_field, stock_daily
from radar.pipelines.regime import current_model as current_regime_model
from radar.universe import Asset, Universe

log = get_logger(__name__)

MODEL_NAME = "event_study"
MODEL_VERSION = "event-study-1"


def day_of(asset: Asset, bucket_ends: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The day a daily bucket describes: the UTC day before a crypto bucket's end, or the
    trading session whose close ended a stock bucket."""
    if asset.asset_class == "crypto":
        return bucket_ends - pd.Timedelta(days=1)
    return bucket_ends.tz_convert(NEW_YORK).tz_localize(None).normalize()


def daily_inputs(session: Session, asset: Asset) -> pd.DataFrame:
    """Daily tone, return, and regime for one asset, one row per day with a return."""
    if asset.asset_class == "crypto":
        close = load_field(session, [asset.symbol], "1Day")[asset.symbol].dropna()
        returns = log_returns(close, step=pd.Timedelta(days=1))
    else:
        close = stock_daily(session, [asset.symbol])[asset.symbol].dropna()
        returns = log_returns(close)

    rows = session.execute(
        select(SentimentAggregate.ts, SentimentAggregate.score_mean).where(
            SentimentAggregate.symbol == asset.symbol, SentimentAggregate.bucket == "1Day"
        )
    ).all()
    tone = pd.Series(
        [r[1] for r in rows],
        index=day_of(asset, pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], utc=True))),
        dtype=float,
    )

    regimes = pd.Series(dtype=object)
    registered = current_regime_model(session, asset.symbol)
    if registered is not None:
        states = session.execute(
            select(RegimeState.ts, RegimeState.label).where(
                RegimeState.symbol == asset.symbol, RegimeState.model_id == registered.id
            )
        ).all()
        regimes = pd.Series(
            [s[1] for s in states],
            index=day_of(asset, pd.DatetimeIndex(pd.to_datetime([s[0] for s in states], utc=True))),
            dtype=object,
        )

    frame = pd.DataFrame({"ret": returns})
    frame["tone"] = tone.reindex(frame.index)
    frame["regime"] = regimes.reindex(frame.index)
    if asset.news_start is not None:
        start = pd.Timestamp(asset.news_start, tz=frame.index.tz)  # type: ignore[attr-defined]
        frame = frame.loc[frame.index >= start]
    return frame.sort_index()


def run_asset(engine: Engine, asset: Asset) -> dict[str, Any] | None:
    """Run the study for one asset and store it. Returns the stored result."""
    with session_scope(engine) as session:
        frame = daily_inputs(session, asset)
    if frame.empty or frame["tone"].notna().sum() == 0:
        log.warning("event_study_skipped", symbol=asset.symbol)
        return None
    regimes = frame["regime"] if frame["regime"].notna().any() else None
    result = event_study.study(frame["tone"], frame["ret"], regimes).model_dump()
    result["days_with_news"] = int(frame["tone"].notna().sum())
    days = pd.DatetimeIndex(frame.index)
    with session_scope(engine) as session:
        session.execute(
            update(ModelRegistry)
            .where(ModelRegistry.name == MODEL_NAME, ModelRegistry.symbol == asset.symbol)
            .values(is_current=False)
        )
        session.add(
            ModelRegistry(
                name=MODEL_NAME,
                symbol=asset.symbol,
                version=MODEL_VERSION,
                train_start=days[0].date(),
                train_end=days[-1].date(),
                is_current=True,
                params={
                    "threshold": event_study.THRESHOLD,
                    "min_events": event_study.MIN_EVENTS,
                    "offsets": list(event_study.OFFSETS),
                },
                metrics=result,
            )
        )
    log.info(
        "event_study_stored",
        symbol=asset.symbol,
        events=result["n_events"],
        verdict=result["verdict"],
    )
    return result


def current(session: Session, symbol: str) -> ModelRegistry | None:
    return session.scalars(
        select(ModelRegistry)
        .where(
            ModelRegistry.name == MODEL_NAME,
            ModelRegistry.symbol == symbol,
            ModelRegistry.is_current,
        )
        .order_by(ModelRegistry.trained_at.desc())
        .limit(1)
    ).first()


def run(engine: Engine, universe: Universe) -> int:
    return sum(run_asset(engine, asset) is not None for asset in universe.primary)
