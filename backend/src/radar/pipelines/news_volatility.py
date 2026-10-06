"""Run the news-and-swings comparison for each primary market and store the result."""

import pandas as pd
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, SentimentAggregate
from radar.db.session import session_scope
from radar.logging import get_logger
from radar.models import evidence
from radar.models import news_volatility as model
from radar.pipelines import relationships
from radar.pipelines.datasets import build_regime_observations
from radar.pipelines.event_study import day_of
from radar.pipelines.volatility import HORIZON_STEPS
from radar.universe import Asset, Universe

log = get_logger(__name__)

NAME = "news_volatility"


class NewsTest(BaseModel):
    """Whether news improved the swings forecast for one market, as stored."""

    symbol: str
    computed_at: AwareDatetime | None = None
    model_version: str
    # How many comparisons were judged together across all markets.
    comparisons: int
    horizons: list[model.HorizonResult]
    # True when any comparison for this market met the rule.
    news_helps: bool


def daily_news(session: Session, asset: Asset, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Article count and average tone on each of `days`. A day with no row has no articles."""
    rows = session.execute(
        select(
            SentimentAggregate.ts, SentimentAggregate.article_count, SentimentAggregate.score_mean
        ).where(SentimentAggregate.symbol == asset.symbol, SentimentAggregate.bucket == "1Day")
    ).all()
    if not rows:
        return pd.DataFrame({"count": 0, "tone": float("nan")}, index=days)
    index = day_of(asset, pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], utc=True)))
    frame = pd.DataFrame({"count": [r[1] for r in rows], "tone": [r[2] for r in rows]}, index=index)
    frame = frame[~frame.index.duplicated(keep="last")].reindex(days)
    frame["count"] = frame["count"].fillna(0)
    return frame


def compare(
    session: Session, asset: Asset, *, min_train: int = 250, refit_every: int = 21
) -> list[model.HorizonResult]:
    """The comparison for one market on the days from which its news is used."""
    observations = build_regime_observations(session, asset)
    rv = observations["rv"].dropna()
    if asset.news_start is not None:
        start = pd.Timestamp(asset.news_start)
        index = pd.DatetimeIndex(rv.index)
        start = start.tz_localize("UTC") if index.tz is not None else start
        rv = rv[index >= start]
    days = pd.DatetimeIndex(rv.index)
    news = daily_news(session, asset, days)
    features = model.news_features(news["count"], news["tone"])
    results = []
    for horizon_days, steps in HORIZON_STEPS[asset.asset_class].items():
        try:
            walk = model.walk_forward(
                rv, features, steps, min_train=min_train, refit_every=refit_every
            )
            results.append(model.evaluate(walk, steps, horizon_days))
        except ValueError as error:
            log.warning("news_volatility_skipped", symbol=asset.symbol, reason=str(error))
    return results


def run(engine: Engine, universe: Universe) -> int:
    """Compare for every primary market, judge all comparisons together, and store."""
    with session_scope(engine) as session:
        found = {asset.symbol: compare(session, asset) for asset in universe.primary}
    pairs = [pair for horizons in found.values() for h in horizons for pair in h.pairs]
    adjusted = iter(evidence.benjamini_hochberg([pair.dm_p_value for pair in pairs]))
    stored = 0
    with session_scope(engine) as session:
        for symbol, horizons in found.items():
            if not horizons:
                continue
            judged = [
                h.model_copy(update={"pairs": [model.judge(p, next(adjusted)) for p in h.pairs]})
                for h in horizons
            ]
            result = NewsTest(
                symbol=symbol,
                model_version=model.MODEL_VERSION,
                comparisons=len(pairs),
                horizons=judged,
                news_helps=any(p.verdict == "news helps" for h in judged for p in h.pairs),
            )
            relationships._store(
                session,
                NAME,
                symbol,
                model.MODEL_VERSION,
                result.model_dump(mode="json"),
                judged[0].first_day,
                judged[0].last_day,
            )
            stored += 1
    log.info("news_volatility_stored", markets=stored, comparisons=len(pairs))
    return stored


def current(session: Session, symbol: str) -> ModelRegistry | None:
    return relationships.current(session, NAME, symbol)
