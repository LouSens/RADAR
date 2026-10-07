"""Build and run the model notebooks from their sources in notebooks/src/.

Each source is a plain Python file in "percent" format: a line `# %% [markdown]` starts
a text cell (its lines are comments) and a line `# %%` starts a code cell. Keeping the
sources as Python means they can be read, reviewed, and linted like any other code.

The notebooks import the same modules the app runs, so what they show cannot drift from
what the app does. Run with:

    uv run python backend/scripts/build_notebooks.py            # all of them
    uv run python backend/scripts/build_notebooks.py 03_swings_and_loss  # one

Needs the database running and filled. `04_news` also needs `uv sync --extra nlp`.
"""

import sys
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

SOURCES = Path("notebooks/src")
OUTPUT = Path("notebooks")
MARKDOWN = "# %% [markdown]"
CODE = "# %%"


def parse(text: str) -> list[tuple[str, str]]:
    """Split a percent-format source into (kind, source) cells."""
    cells: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith(MARKDOWN):
            cells.append(("markdown", []))
        elif line.startswith(CODE):
            cells.append(("code", []))
        elif cells:
            cells[-1][1].append(line)
    result = []
    for kind, lines in cells:
        if kind == "markdown":
            lines = [line[2:] if line.startswith("# ") else line.lstrip("#") for line in lines]
        source = "\n".join(lines).strip()
        if source:
            result.append((kind, source))
    return result


def build(source: Path) -> Path:
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell(text)
        if kind == "markdown"
        else nbformat.v4.new_code_cell(text)
        for kind, text in parse(source.read_text(encoding="utf-8"))
    ]
    ExecutePreprocessor(timeout=3600, kernel_name="python3").preprocess(
        notebook, {"metadata": {"path": "."}}
    )
    target = OUTPUT / f"{source.stem}.ipynb"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        nbformat.write(notebook, handle)
    return target


def main(names: list[str]) -> int:
    sources = sorted(SOURCES.glob("*.py"))
    if names:
        sources = [s for s in sources if s.stem in names]
    if not sources:
        sys.stderr.write("No matching notebook sources in notebooks/src/\n")
        return 1
    for source in sources:
        target = build(source)
        sys.stdout.write(f"built {target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
