"""Notebook 04 holds its own copy of the headline cleaning; it must match the app's.

The notebook trains the tone model and the app scores headlines with it. The link
between the two is the saved model, not shared code, so the text each builds has to be
the same, character for character. The cell the notebook marks `app-parity` is run here
and compared with `radar.models.dataset` on made-up headlines.
"""

from pathlib import Path
from typing import Any

from radar.models import dataset

SOURCE = Path(__file__).parents[3] / "notebooks" / "src" / "04_news.py"

# Made up, one for each thing the cleaning handles.
EXAMPLES = [
    "Gold Rises As Dollar Slips",
    "Gold &amp; Silver   Rise As Dollar Slips (UPDATED)",
    "Analyst Praises Example Corp (NYSE:EXMP) After Earnings",
    "Example Corp (NASDAQ: EXMP) Cuts Forecast (CORRECTED)",
    "'Example Bank Cuts Its Forecast' - Example Wire",
    "“Bitcoin Could Double” - @example",
    "Bitcoin Falls 5% After Reported Hack",
    "Fed Holds Rates.",
    "Is Gold Overbought?",
    "Example Whale Moves 2,901 Coins Off Exchange",
    "  Leading And Trailing Spaces  ",
    "Exchange Halts Withdrawals (CRYPTO: EXM)",
    "Gold Hits $2,500; Silver Follows",
    "Q&amp;A: What Moved Markets",
    "Example Miner Expands (TSX:EXM) (UPDATED)",
    "Asia Mixed - Markets Today",
]


def notebook_functions() -> dict[str, Any]:
    """Run the notebook cell marked `app-parity` and return what it defines."""
    cells: list[list[str]] = []
    keep = False
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if line.startswith("# %%"):
            keep = line.strip() == "# %% app-parity"
            if keep:
                cells.append([])
        elif keep:
            cells[-1].append(line)
    assert len(cells) == 1, "the notebook should mark one cell app-parity"
    defined: dict[str, Any] = {}
    exec(compile("\n".join(cells[0]), str(SOURCE), "exec"), defined)  # noqa: S102
    return defined


def test_notebook_and_app_clean_and_key_headlines_alike() -> None:
    notebook = notebook_functions()
    for headline in EXAMPLES:
        assert notebook["clean_headline"](headline) == dataset.clean_headline(headline), headline
        assert notebook["headline_key"](headline) == dataset.headline_key(headline), headline


def test_the_examples_exercise_the_cleaning() -> None:
    """Guard against a list of examples that every implementation would pass."""
    changed = sum(dataset.clean_headline(h) != " ".join(h.split()) for h in EXAMPLES)
    assert changed >= 6
