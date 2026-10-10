"""Check and gather the three blind labelling passes of decision 104.

    uv run python backend/scripts/tone_relabel.py          # what is done, what is missing
    uv run python backend/scripts/tone_relabel.py merge    # write the labels file

Each pass was drawn in its own random order with its own random keys, in parts under
`data/research/tone5/relabel/in/`; a labeller wrote `KEY<TAB>LABEL` lines to the file of
the same name under `out/`. `merge` joins the keys back to their articles and writes
`backend/src/radar/sentiment_round5_labels.csv`, one row per article and pass. It reads
no earlier label and scores nothing.
"""

import sys
from pathlib import Path

import pandas as pd

WORK = Path("data/research/tone5/relabel")
TARGET = Path("backend/src/radar/sentiment_round5_labels.csv")
LABELS = {"positive", "negative", "neutral"}
PASSES = (1, 2, 3)


def part_labels(part: Path) -> tuple[dict[str, str], list[str]]:
    """The labels written for one part, and what is wrong with them."""
    wanted = [line.split(" | ")[0] for line in part.read_text(encoding="utf-8").splitlines()]
    written = WORK / "out" / f"{part.stem}.tsv"
    if not written.is_file():
        return {}, ["not written"]
    found: dict[str, str] = {}
    problems: list[str] = []
    for line in written.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, _, label = line.strip().partition("\t")
        label = label.strip().lower()
        if key not in wanted or label not in LABELS or key in found:
            problems.append(f"bad line: {line[:40]!r}")
        else:
            found[key] = label
    missing = len(wanted) - len(found)
    if missing:
        problems.append(f"{missing} of {len(wanted)} keys missing")
    return found, problems


def gather() -> tuple[pd.DataFrame, dict[str, list[str]]]:
    rows, problems = [], {}
    for number in PASSES:
        keys = pd.read_csv(WORK / f"map_p{number}.csv").set_index("key")["article_id"]
        for part in sorted((WORK / "in").glob(f"p{number}_*.txt")):
            found, wrong = part_labels(part)
            if wrong:
                problems[part.stem] = wrong
            rows += [(int(keys[key]), number, label) for key, label in found.items()]
    return pd.DataFrame(rows, columns=["article_id", "pass", "sentiment"]), problems


def main(arguments: list[str]) -> int:
    labels, problems = gather()
    for part, wrong in problems.items():
        sys.stdout.write(f"{part}: {'; '.join(wrong)}\n")
    sys.stdout.write(f"{len(labels)} labels gathered; {len(problems)} parts not complete\n")
    if arguments[:1] != ["merge"]:
        return 0
    if problems:
        sys.stderr.write("Not merged: every part must be complete first\n")
        return 1
    labels = labels.sort_values(["article_id", "pass"])
    labels["rule"] = "decision 104"
    labels["labelled_by"] = "claude"
    labels.to_csv(TARGET, index=False, lineterminator="\n")
    sys.stdout.write(f"wrote {TARGET.as_posix()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
