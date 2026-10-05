"""Schema validation for bars. A bar that fails is rejected, reported, and never stored."""

from typing import Any

import pandas as pd
import pandera.pandas as pa

from radar.providers import schemas

PRICE = pa.Check.gt(0)

BAR_SCHEMA = pa.DataFrameSchema(
    {
        "ts": pa.Column(nullable=False, unique=True),
        "open": pa.Column(float, PRICE, coerce=True),
        "high": pa.Column(float, PRICE, coerce=True),
        "low": pa.Column(float, PRICE, coerce=True),
        "close": pa.Column(float, PRICE, coerce=True),
        "volume": pa.Column(float, pa.Check.ge(0), coerce=True),
        "trade_count": pa.Column(int, pa.Check.ge(0), coerce=True),
        "vwap": pa.Column(float, pa.Check.ge(0), coerce=True),
    },
    checks=[
        pa.Check(
            lambda df: df["high"] >= df[["open", "close"]].max(axis=1),
            name="high_at_least_open_and_close",
        ),
        pa.Check(
            lambda df: df["low"] <= df[["open", "close"]].min(axis=1),
            name="low_at_most_open_and_close",
        ),
    ],
)

BAR_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "trade_count", "vwap"]


def bars_frame(bars: list[schemas.Bar]) -> pd.DataFrame:
    rows = [
        (b.timestamp, b.open, b.high, b.low, b.close, b.volume, b.trade_count, b.vwap) for b in bars
    ]
    return pd.DataFrame(rows, columns=BAR_COLUMNS)


def invalid_rows(frame: pd.DataFrame) -> dict[Any, list[str]]:
    """Map the index of each failing row to the names of the checks it failed."""
    if frame.empty:
        return {}
    failures: dict[Any, list[str]] = {}
    naive = frame["ts"].map(lambda ts: ts.tzinfo is None or ts.utcoffset() is None)
    for index in frame.index[naive]:
        failures.setdefault(index, []).append("timestamp_is_timezone_aware")
    try:
        BAR_SCHEMA.validate(frame, lazy=True)
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases.dropna(subset=["index"])
        for index, check in zip(cases["index"], cases["check"], strict=True):
            failures.setdefault(index, []).append(str(check))
    return failures


def split_valid_bars(
    bars: list[schemas.Bar],
) -> tuple[list[schemas.Bar], list[dict[str, Any]]]:
    """Separate bars that pass validation from those that do not."""
    failures = invalid_rows(bars_frame(bars))
    valid = [bar for i, bar in enumerate(bars) if i not in failures]
    rejected = [
        {"ts": bars[i].timestamp.isoformat(), "checks": sorted(set(checks))}
        for i, checks in sorted(failures.items())
    ]
    return valid, rejected
