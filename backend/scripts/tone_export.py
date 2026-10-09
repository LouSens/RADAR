"""Write the tone data to two files, so notebook 04 can run without the app or its database.

    uv run python backend/scripts/tone_export.py

- `data/research/tone4/tone_dataset.csv`: every labelled headline with its text, its
  market, its date, both labelling passes, and whether it is for training and
  validation ("labelled") or the test set ("test").
- `data/research/tone4/tone_pool.csv`: the unlabelled articles for self-training.

Both hold the provider's headlines, so they stay in the gitignored `data/` folder and
are never committed. To run the notebook elsewhere (Colab, say), copy the two files
there yourself.
"""

import sys

import pandas as pd

from radar.pipelines import tone

COLUMNS = ["article_id", "symbol", "market", "created_at", "headline", "summary"]


def main() -> None:
    data = tone.load()
    labelled = data.labelled[[*COLUMNS, "first", "second", "sentiment"]].assign(part="labelled")
    test = data.test[[*COLUMNS, "sentiment"]].assign(part="test")
    test["first"], test["second"] = test["sentiment"], None
    both = pd.concat([labelled, test], ignore_index=True)
    both.to_csv(tone.OUT / "tone_dataset.csv", index=False, encoding="utf-8")
    pool = tone.pool(data, "headline")[COLUMNS]
    pool.to_csv(tone.OUT / "tone_pool.csv", index=False, encoding="utf-8")
    sys.stdout.write(f"{len(labelled)} labelled, {len(test)} test, {len(pool)} pool\n")


if __name__ == "__main__":
    main()
