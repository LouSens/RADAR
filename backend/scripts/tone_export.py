"""Write the tone data to one file, so notebook 04 can run without the app or its database.

    uv run python backend/scripts/tone_export.py

- `data/research/tone5/tone_dataset.parquet`: every labelled headline with its text, its
  market, its date, each labelling pass, the label used for scoring, who wrote the labels,
  and whether the row is for training and validation ("labelled") or the test set ("test").
- `data/research/tone5/earlier_candidates.json`: the validation figures of the base
  models tried in round 4, read from the runs stored then. Nothing is trained here.

The first file holds the provider's headlines, so it stays in the gitignored `data/`
folder and is never committed. To run the notebook elsewhere (Colab, say), copy it there
yourself. The script copies the test labels across without showing or scoring them.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from radar.pipelines import tone

OUT = Path("data/research/tone5")
COLUMNS = ["article_id", "symbol", "market", "created_at", "headline", "summary"]
PASSES = ["label_1", "label_2"]


def dataset(data: tone.Data) -> pd.DataFrame:
    labelled = data.labelled[COLUMNS].assign(
        label_1=data.labelled["first"],
        label_2=data.labelled["second"],
        label=data.labelled["sentiment"],
        part="labelled",
    )
    test = data.test[COLUMNS].assign(
        label_1=data.test["sentiment"], label_2=None, label=data.test["sentiment"], part="test"
    )
    both = pd.concat([labelled, test], ignore_index=True)
    both["summary"] = both["summary"].fillna("")
    both["labelled_by"] = "claude"
    both["rule"] = "decision 101"
    return both[[*COLUMNS, *PASSES, "label", "labelled_by", "rule", "part"]]


def earlier(data: tone.Data) -> dict[str, object]:
    """Round 4's base models on the walk-forward blocks, from stored runs only."""
    text = "asset + headline + summary"  # the input text round 4 used for this step
    found: dict[str, object] = {}
    for name, model in tone.MODELS.items():
        rows = []
        for number, (train, validation) in enumerate(tone.blocks(data), start=1):
            for seed in tone.CHOICE_SEEDS:
                run = tone._name(
                    list(train["article_id"]),
                    list(validation["article_id"]),
                    text,
                    model,
                    tone.START,
                    seed,
                    None,
                )
                stored = tone.OUT / "runs" / run / "validation.npy"
                if stored.is_file():
                    scores = tone.measure(validation["sentiment"].tolist(), np.load(stored))
                    rows.append({"block": number, "seed": seed, **scores})
        found[name] = {"model": model, "runs": rows}
    return {
        "input text": text,
        "settings": tone.START,
        "block": tone.BLOCK,
        "blocks": tone.BLOCKS,
        "seeds": list(tone.CHOICE_SEEDS),
        "labels": "decision 101, before any relabelling",
        "models": found,
    }


def main() -> None:
    data = tone.load()
    OUT.mkdir(parents=True, exist_ok=True)
    both = dataset(data)
    both.to_parquet(OUT / "tone_dataset.parquet", index=False)
    (OUT / "earlier_candidates.json").write_text(json.dumps(earlier(data), indent=1))
    counts = both["part"].value_counts().to_dict()
    sys.stdout.write(f"{counts} written to {OUT.as_posix()}\n")


if __name__ == "__main__":
    main()
