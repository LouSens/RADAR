"""The configured asset universe, loaded from `universe.toml`."""

import os
import re
import tomllib
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_UNIVERSE_FILE = Path(__file__).with_name("universe.toml")
UNIVERSE_FILE_ENV = "RADAR_UNIVERSE_FILE"

AssetClass = Literal["crypto", "stock"]

_TIMEFRAME = re.compile(r"^\d{1,2}(Min|Hour|Day)$")
_LOCATION = re.compile(r"^[a-z]{2}(-\d)?$")


class _Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Asset(_Config):
    symbol: str
    name: str
    asset_class: AssetClass
    is_primary: bool = False
    # What the asset is to a long-run holder: the broad stock market, gold, or Bitcoin.
    # Left out for anything else, which the plan treats as a small bet. The screens
    # use this instead of knowing any ticker by name.
    kind: Literal["stocks", "gold", "bitcoin"] | None = None
    bars_symbol: str
    history_start: date
    news_symbols: tuple[str, ...] = ()
    news_start: date | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.news_symbols and self.news_start is None:
            raise ValueError(f"{self.symbol}: news_symbols needs news_start")
        if any("/" in s for s in self.news_symbols):
            raise ValueError(f"{self.symbol}: news symbols have no slash, for example BTCUSD")
        if self.is_primary and not self.news_symbols:
            raise ValueError(f"{self.symbol}: a primary asset needs news_symbols")
        return self


class Timeframes(_Config):
    crypto: tuple[str, ...]
    stock: tuple[str, ...]

    @model_validator(mode="after")
    def _check(self) -> Self:
        for timeframe in (*self.crypto, *self.stock):
            if not _TIMEFRAME.match(timeframe):
                raise ValueError(f"Invalid timeframe: {timeframe!r}")
        return self


class StressEpisode(_Config):
    """A named stretch of history the portfolio is replayed through (spec F6)."""

    name: str
    start: date
    end: date

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"{self.name}: the episode must end after it starts")
        return self


class Universe(_Config):
    crypto_location: str = Field(pattern=_LOCATION.pattern)
    timeframes: Timeframes
    assets: tuple[Asset, ...]
    stress_episodes: tuple[StressEpisode, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        symbols = [a.symbol for a in self.assets]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Duplicate asset symbols in the universe")
        if not self.primary:
            raise ValueError("The universe needs at least one primary asset")
        return self

    @property
    def primary(self) -> tuple[Asset, ...]:
        return tuple(a for a in self.assets if a.is_primary)

    @property
    def news_symbols(self) -> tuple[str, ...]:
        """Every provider news symbol the universe needs, without duplicates."""
        return tuple(dict.fromkeys(s for a in self.assets for s in a.news_symbols))

    def of_class(self, asset_class: AssetClass) -> tuple[Asset, ...]:
        return tuple(a for a in self.assets if a.asset_class == asset_class)

    def get(self, symbol: str) -> Asset:
        for asset in self.assets:
            if asset.symbol == symbol:
                return asset
        raise KeyError(symbol)

    def timeframes_for(self, asset: Asset) -> tuple[str, ...]:
        return self.timeframes.crypto if asset.asset_class == "crypto" else self.timeframes.stock


def load_universe(path: Path | None = None) -> Universe:
    path = path or Path(os.environ.get(UNIVERSE_FILE_ENV) or DEFAULT_UNIVERSE_FILE)
    with path.open("rb") as handle:
        return Universe.model_validate(tomllib.load(handle))


@cache
def get_universe() -> Universe:
    return load_universe()
