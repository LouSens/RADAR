from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.universe import Universe, load_universe

MINIMAL = """
crypto_location = "us-1"
[timeframes]
crypto = ["1Hour", "1Day"]
stock = ["1Day"]
[[assets]]
symbol = "BTC/USD"
name = "Bitcoin"
asset_class = "crypto"
is_primary = true
bars_symbol = "BTC/USD"
history_start = 2021-01-01
news_symbols = ["BTCUSD"]
news_start = 2022-01-01
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "universe.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_default_universe_matches_the_audit_decisions() -> None:
    universe = load_universe()
    assert universe.crypto_location == "us-1"
    assert universe.timeframes.crypto == ("1Hour", "1Day")
    assert [a.symbol for a in universe.primary] == ["BTC/USD", "GLD"]
    assert {a.symbol for a in universe.of_class("stock")} == {"SPY", "GLD"}

    gold = universe.get("GLD")
    assert gold.news_symbols == ("GLD",)
    assert gold.asset_class == "stock"
    assert gold.news_start == date(2023, 1, 1)
    assert universe.get("BTC/USD").news_start == date(2022, 1, 1)
    assert universe.news_symbols == ("BTCUSD", "GLD")
    assert universe.timeframes_for(universe.get("SPY")) == ("1Hour", "1Day")
    assert "PAXG/USD" not in {a.symbol for a in universe.assets}


def test_loads_a_custom_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write(tmp_path, MINIMAL)
    monkeypatch.setenv("RADAR_UNIVERSE_FILE", str(path))
    assert [a.symbol for a in load_universe().assets] == ["BTC/USD"]


def test_unknown_symbol_raises() -> None:
    with pytest.raises(KeyError):
        load_universe().get("DOGE/USD")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('crypto_location = "us-1"', 'crypto_location = "../v2"'),
        ('crypto = ["1Hour", "1Day"]', 'crypto = ["1Fortnight"]'),
        ('news_symbols = ["BTCUSD"]', 'news_symbols = ["BTC/USD"]'),
        ("news_start = 2022-01-01", ""),
        ("is_primary = true", "is_primary = false"),
        ('name = "Bitcoin"', 'name = "Bitcoin"\nleverage = 3'),
    ],
)
def test_invalid_universe_is_rejected(tmp_path: Path, old: str, new: str) -> None:
    assert old in MINIMAL
    with pytest.raises(ValidationError):
        load_universe(write(tmp_path, MINIMAL.replace(old, new)))


def test_duplicate_symbols_are_rejected(tmp_path: Path) -> None:
    block = MINIMAL[MINIMAL.index("[[assets]]") :]
    with pytest.raises(ValidationError):
        load_universe(write(tmp_path, MINIMAL + block))


def test_universe_is_immutable() -> None:
    universe: Universe = load_universe()
    with pytest.raises(ValidationError):
        universe.crypto_location = "us"  # type: ignore[misc]
