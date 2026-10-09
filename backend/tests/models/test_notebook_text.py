"""Notebook 04 holds its own copy of the text preparation; it must match the app's.

The notebook trains the tone model and the app scores headlines with it. The link
between the two is the saved model, not shared code, so the text each builds has to be
the same, character for character. The cells the notebook marks `app-parity` are run
here and compared with `radar.models.dataset` on made-up headlines.
"""

from pathlib import Path
from typing import Any

import pytest

from radar.models import dataset

SOURCE = Path(__file__).parents[3] / "notebooks" / "src" / "04_news.py"

# (headline, summary, market): made up, one for each thing the preparation handles.
EXAMPLES = [
    ("Gold Rises As Dollar Slips", "", "Gold"),
    ("Gold &amp; Silver   Rise As Dollar Slips (UPDATED)", "", "Gold"),
    ("Analyst Praises Example Corp (NYSE:EXMP) After Earnings", "", "US stocks"),
    ("Example Corp (NASDAQ: EXMP) Cuts Forecast (CORRECTED)", "Shares fell.", "US stocks"),
    ("'Example Bank Cuts Its Forecast' - Example Wire", "", "US stocks"),
    ("“Bitcoin Could Double” - @example", "", "Bitcoin"),
    ("Bitcoin Falls 5% After Reported Hack", "Bitcoin fell. Analysts said the move", "Bitcoin"),
    ("Bitcoin Falls 5% After Reported Hack", "Bitcoin Falls 7% After Reported Hack.", "Bitcoin"),
    ("Fed Holds Rates.", "The decision was expected. Markets were little", "US stocks"),
    ("Is Gold Overbought?", "A summary with no sentence end", "Gold"),
    ("Stocks Rally!", 'He said "it holds." Then nothing more was', "US stocks"),
    ("Example Whale Moves 2,901 Coins Off Exchange", "", "Bitcoin"),
    ("  Leading And Trailing Spaces  ", "  Spaces   inside.  ", "Gold"),
    ("Gold Rises", "Bullion gained on the day. Analysts said the move could", ""),
    ("Tech Shares Rise While Energy Falls", "", ""),
    ("Example Corp To Report Results On Thursday", "Results are due Thursday.", "US stocks"),
    ("Exchange Halts Withdrawals (CRYPTO: EXM)", "Withdrawals stopped! Users waited.", "Bitcoin"),
    ("Gold Hits $2,500; Silver Follows", "Gold rose (again). Silver followed.)", "Gold"),
    ("Q&amp;A: What Moved Markets", "", "US stocks"),
    ("Example Miner Expands (TSX:EXM) (UPDATED)", "Output rose 3%. More to", "Gold"),
]


def notebook_functions() -> dict[str, Any]:
    """Run the notebook cells marked `app-parity` and return what they define."""
    cells: list[list[str]] = []
    keep = False
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if line.startswith("# %%"):
            keep = line.strip() == "# %% app-parity"
            if keep:
                cells.append([])
        elif keep:
            cells[-1].append(line)
    assert len(cells) == 3, "the notebook should mark three cells app-parity"
    defined: dict[str, Any] = {}
    for cell in cells:
        exec(compile("\n".join(cell), str(SOURCE), "exec"), defined)  # noqa: S102
    return defined


def test_there_are_twenty_examples() -> None:
    assert len(EXAMPLES) == 20
    assert len(set(EXAMPLES)) == 20


@pytest.mark.parametrize(
    "option", ["headline", "asset + headline", "headline + summary", "asset + headline + summary"]
)
def test_notebook_and_app_build_the_same_text(option: str) -> None:
    notebook = notebook_functions()
    parts = notebook["TEXTS"][option]
    for headline, summary, market in EXAMPLES:
        assert notebook["model_text"](headline, summary, market, **parts) == dataset.model_text(
            headline, summary, market, **parts
        ), (option, headline)


def test_notebook_and_app_clean_and_key_headlines_alike() -> None:
    notebook = notebook_functions()
    for headline, summary, _ in EXAMPLES:
        assert notebook["clean_headline"](headline) == dataset.clean_headline(headline)
        assert notebook["headline_key"](headline) == dataset.headline_key(headline)
        assert notebook["whole_sentences"](summary) == dataset.whole_sentences(summary)


def test_the_examples_exercise_the_preparation() -> None:
    """Guard against a list of examples that every implementation would pass."""
    changed = sum(dataset.clean_headline(h) != " ".join(h.split()) for h, _, _ in EXAMPLES)
    with_summary = sum(
        dataset.model_text(h, s, m, with_summary=True) != dataset.model_text(h, s, m)
        for h, s, m in EXAMPLES
    )
    assert changed >= 6
    assert with_summary >= 6
