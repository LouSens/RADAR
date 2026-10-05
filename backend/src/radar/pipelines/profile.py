"""Phase 1 data profile: measured facts about the stored data (spec 7.3).

`radar profile` writes docs/DATA_PROFILE.md. The exploration notebook calls the same
functions, so the notebook's figures and the document's numbers cannot disagree.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from radar.db.models import NewsArticle, NewsSymbol
from radar.db.session import session_scope
from radar.features.panels import MixedPanel
from radar.features.returns import log_returns
from radar.pipelines.datasets import (
    build_crypto_panel,
    build_mixed_panel,
    build_realised_volatility,
    load_field,
    stock_daily,
)
from radar.pipelines.quality import load_bars
from radar.quality.gaps import expected_index, find_gaps
from radar.universe import Asset, Universe

PROFILE_PATH = Path("docs/DATA_PROFILE.md")
PERIODS_PER_YEAR = {"crypto": 365, "stock": 252}


@dataclass
class Profile:
    generated_at: datetime
    coverage: pd.DataFrame
    returns: pd.DataFrame
    volatility: pd.DataFrame
    panels: dict[str, object]
    correlation: pd.DataFrame
    news: pd.DataFrame


def daily_returns(session: Session, asset: Asset) -> pd.Series:
    """Daily log returns of one asset on its own calendar."""
    if asset.asset_class == "crypto":
        close = load_field(session, [asset.symbol], "1Day")[asset.symbol].dropna()
        return log_returns(close, step=pd.Timedelta(days=1)).dropna()
    close = stock_daily(session, [asset.symbol])[asset.symbol].dropna()
    return log_returns(close).dropna()


def coverage_table(session: Session, universe: Universe) -> pd.DataFrame:
    rows = []
    for asset in universe.assets:
        for timeframe in universe.timeframes_for(asset):
            frame = load_bars(session, asset.symbol, timeframe)
            if frame.empty:
                continue
            actual = pd.DatetimeIndex(frame["ts"])
            gaps = find_gaps(
                expected_index(asset.asset_class, timeframe, actual[0], actual[-1]), actual
            )
            rows.append(
                {
                    "symbol": asset.symbol,
                    "timeframe": timeframe,
                    "first": actual[0],
                    "last": actual[-1],
                    "bars": len(frame),
                    "missing": gaps.missing,
                    "missing_share": gaps.missing_share,
                    "quote_only_share": float(frame["is_quote_only"].mean()),
                    "outliers": int(frame["is_outlier"].sum()),
                }
            )
    return pd.DataFrame(rows)


def returns_table(session: Session, universe: Universe) -> pd.DataFrame:
    rows = []
    for asset in universe.assets:
        r = daily_returns(session, asset)
        squared = r**2
        rows.append(
            {
                "symbol": asset.symbol,
                "days": len(r),
                "mean": r.mean(),
                "std": r.std(),
                "annual_volatility": r.std() * np.sqrt(PERIODS_PER_YEAR[asset.asset_class]),
                "skew": r.skew(),
                "excess_kurtosis": r.kurt(),
                "worst": r.min(),
                "best": r.max(),
                "autocorr_1": r.autocorr(1),
                "squared_autocorr_1": squared.autocorr(1),
                "squared_autocorr_5": squared.autocorr(5),
            }
        )
    return pd.DataFrame(rows)


def volatility_table(session: Session, universe: Universe) -> pd.DataFrame:
    rows = []
    for asset in universe.assets:
        rv = build_realised_volatility(session, asset)
        valid = rv["rv"].dropna()
        rows.append(
            {
                "symbol": asset.symbol,
                "days": len(rv),
                "flagged": int(rv["flagged"].sum()),
                "flagged_share": float(rv["flagged"].mean()),
                "median": valid.median(),
                "p95": valid.quantile(0.95),
                "max": valid.max(),
                "log_autocorr_1": pd.Series(np.log(valid[valid > 0])).autocorr(1),
            }
        )
    return pd.DataFrame(rows)


def panel_facts(crypto: pd.DataFrame, mixed: MixedPanel) -> dict[str, object]:
    return {
        "crypto_rows": len(crypto),
        "crypto_first": crypto.index.min(),
        "crypto_last": crypto.index.max(),
        "mixed_rows": len(mixed.returns),
        "mixed_first": mixed.returns.index.min(),
        "mixed_last": mixed.returns.index.max(),
        "mixed_filled": {k: int(v) for k, v in mixed.filled.sum().items() if v},
        "mixed_rows_complete": len(mixed.returns.dropna()),
        "mixed_complete_first": mixed.returns.dropna().index.min(),
    }


def news_table(session: Session) -> pd.DataFrame:
    year = func.extract("year", NewsArticle.created_at)
    rows = session.execute(
        select(
            NewsSymbol.symbol,
            year.label("year"),
            func.count().label("articles"),
            func.count(NewsArticle.duplicate_of).label("duplicates"),
        )
        .join(NewsArticle, NewsArticle.id == NewsSymbol.article_id)
        .group_by(NewsSymbol.symbol, year)
        .order_by(NewsSymbol.symbol, year)
    ).all()
    frame = pd.DataFrame(rows, columns=["symbol", "year", "articles", "duplicates"])
    frame["year"] = frame["year"].astype(int)
    return frame


def build_profile(engine: Engine, universe: Universe) -> Profile:
    with session_scope(engine) as session:
        crypto = build_crypto_panel(session, universe)
        mixed = build_mixed_panel(session, universe)
        return Profile(
            generated_at=datetime.now(UTC).replace(microsecond=0),
            coverage=coverage_table(session, universe),
            returns=returns_table(session, universe),
            volatility=volatility_table(session, universe),
            panels=panel_facts(crypto, mixed),
            correlation=mixed.returns.dropna().corr(),
            news=news_table(session),
        )


# --- rendering -------------------------------------------------------------------------


def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return [*lines, ""]


def _pct(value: Any, digits: int = 2) -> str:
    return "n/a" if pd.isna(value) else f"{100 * value:.{digits}f}%"


def _num(value: Any, digits: int = 2) -> str:
    return "n/a" if pd.isna(value) else f"{value:.{digits}f}"


def render(p: Profile) -> str:
    out = [
        "# RADAR data profile",
        "",
        "Generated by `uv run radar profile` from the stored data. Do not edit by hand.",
        "The figures in `notebooks/01_exploration.ipynb` are drawn from the same functions.",
        "",
        f"- Run at: {p.generated_at:%Y-%m-%d %H:%M} UTC",
        "- Every number is measured from the database. Times are UTC.",
        "",
        "## 1. History depth and missing data",
        "",
        "Missing is measured against the calendar each series should follow: every hour or"
        " day for crypto, New York Stock Exchange sessions for stocks (regular hours only"
        " for hourly bars).",
        "",
    ]
    out += _table(
        [
            "Symbol",
            "Timeframe",
            "First",
            "Last",
            "Bars",
            "Missing",
            "Missing share",
            "Quote-only",
            "Outlier flags",
        ],
        [
            [
                r.symbol,
                r.timeframe,
                f"{r.first:%Y-%m-%d}",
                f"{r.last:%Y-%m-%d}",
                f"{r.bars:,}",
                f"{r.missing:,}",
                _pct(r.missing_share),
                _pct(r.quote_only_share),
                r.outliers,
            ]
            for r in p.coverage.itertuples()
        ],
    )

    out += [
        "## 2. Daily return distributions",
        "",
        "Log returns on each asset's own calendar. Excess kurtosis above 0 means fatter"
        " tails than a normal distribution. Annual volatility uses 365 days for crypto and"
        " 252 for stocks.",
        "",
    ]
    out += _table(
        [
            "Symbol",
            "Days",
            "Mean",
            "Daily std",
            "Annual volatility",
            "Skew",
            "Excess kurtosis",
            "Worst day",
            "Best day",
        ],
        [
            [
                r.symbol,
                f"{r.days:,}",
                _pct(r.mean, 3),
                _pct(r.std),
                _pct(r.annual_volatility, 1),
                _num(r.skew),
                _num(r.excess_kurtosis, 1),
                _pct(r.worst, 1),
                _pct(r.best, 1),
            ]
            for r in p.returns.itertuples()
        ],
    )

    out += [
        "## 3. Autocorrelation and volatility clustering",
        "",
        "Autocorrelation of returns near 0 means yesterday's direction says little about"
        " today's. Autocorrelation of squared returns above 0 means large moves follow"
        " large moves: volatility clusters, which is what the regime model relies on.",
        "",
    ]
    out += _table(
        ["Symbol", "Returns, lag 1", "Squared returns, lag 1", "Squared returns, lag 5"],
        [
            [
                r.symbol,
                _num(r.autocorr_1, 3),
                _num(r.squared_autocorr_1, 3),
                _num(r.squared_autocorr_5, 3),
            ]
            for r in p.returns.itertuples()
        ],
    )

    out += [
        "## 4. Realised volatility",
        "",
        "Daily realised volatility from hourly bars (spec 7.4). Flagged days had too few"
        " hourly bars and carry no value.",
        "",
    ]
    out += _table(
        [
            "Symbol",
            "Days",
            "Flagged",
            "Flagged share",
            "Median",
            "95th percentile",
            "Largest",
            "Log autocorrelation, lag 1",
        ],
        [
            [
                r.symbol,
                f"{r.days:,}",
                r.flagged,
                _pct(r.flagged_share),
                _pct(r.median),
                _pct(r.p95),
                _pct(r.max, 1),
                _num(r.log_autocorr_1, 3),
            ]
            for r in p.volatility.itertuples()
        ],
    )

    f = p.panels
    out += [
        "## 5. Aligned panels",
        "",
        f"- Crypto panel: {f['crypto_rows']:,} UTC days, {f['crypto_first']:%Y-%m-%d} to"
        f" {f['crypto_last']:%Y-%m-%d}.",
        f"- Mixed panel: {f['mixed_rows']:,} trading sessions, {f['mixed_first']:%Y-%m-%d} to"
        f" {f['mixed_last']:%Y-%m-%d}; {f['mixed_rows_complete']:,} sessions have every asset,"
        f" starting {f['mixed_complete_first']:%Y-%m-%d}.",
        f"- Crypto prices carried forward at a session close: {f['mixed_filled'] or 'none'}.",
        "",
        "### Correlation of daily returns, mixed panel, sessions with every asset",
        "",
    ]
    symbols = list(p.correlation.columns)
    out += _table(
        ["", *symbols],
        [[row, *[_num(p.correlation.loc[row, col]) for col in symbols]] for row in symbols],
    )

    out += ["## 6. News articles per year", "", "Duplicates are marked, not deleted.", ""]
    years = sorted(p.news["year"].unique())
    rows: list[list[object]] = []
    for symbol, group in p.news.groupby("symbol"):
        by_year = group.set_index("year")
        rows.append(
            [
                symbol,
                *[f"{int(by_year['articles'].get(y, 0)):,}" for y in years],
                f"{int(group['duplicates'].sum()):,}",
            ]
        )
    out += _table(["Asset", *[str(y) for y in years], "Duplicates"], rows)
    return "\n".join(out).rstrip() + "\n"


def write_profile(engine: Engine, universe: Universe) -> Profile:
    profile = build_profile(engine, universe)
    PROFILE_PATH.write_text(render(profile), encoding="utf-8", newline="\n")
    return profile
