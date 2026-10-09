"""Draw the headlines to label for decision 101, and write them out blind.

Two kinds are mixed in one random order, so the labeller cannot tell them apart:

- the new test set: stored headlines from the test period that no labelled set holds;
- an audit of old labels: headlines already labelled, to be labelled a second time.

What is written for the labeller holds a running number, the market and the headline,
and nothing else: not the article, not its date, not which kind it is and not the old
label. The key that ties a number back to an article stays in `draw.json`.

    uv run python backend/scripts/tone_draw.py            # the test set and the audit
    uv run python backend/scripts/tone_draw.py GLD        # every old label of one market
    uv run python backend/scripts/tone_draw.py merge      # join what was labelled, and compare
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import NewsArticle, NewsSymbol
from radar.db.session import make_engine, session_scope
from radar.models import dataset
from radar.pipelines import finetune as job
from radar.pipelines.labels import load_labels

OUT = Path("data/research/tone4")
TEST_FROM = pd.Timestamp("2026-08-01", tz="UTC")
SEED = 20261010
MARKET = {"BTC/USD": "Bitcoin", "SPY": "US stocks", "GLD": "Gold", "PAXG/USD": "Gold"}
NEW_PER_MARKET = {"Gold": None, "Bitcoin": 250, "US stocks": 250}  # None: all there is
AUDIT_PER_MARKET = 80
BATCH = 150


def say(text: str) -> None:
    sys.stdout.write(text + "\n")


def labelled_sets() -> tuple[pd.DataFrame, pd.DataFrame]:
    """The old labelled headlines usable for training, and every labelled headline."""
    with session_scope(make_engine()) as session:
        first = job.with_text(session, job.load_training_labels())
        second = job.with_text(session, job.load_replication_labels())
        reference = job.with_text(session, load_labels())
    usable = pd.concat([first, second], ignore_index=True)
    return usable, pd.concat([usable, reference], ignore_index=True)


def unlabelled_since(start: pd.Timestamp, everything: pd.DataFrame) -> pd.DataFrame:
    with session_scope(make_engine()) as session:
        rows = session.execute(
            select(NewsArticle.id, NewsSymbol.symbol, NewsArticle.created_at, NewsArticle.headline)
            .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
            .where(
                NewsArticle.duplicate_of.is_(None),
                NewsArticle.created_at >= start,
                NewsSymbol.symbol.in_(list(MARKET)),
            )
            .order_by(NewsArticle.id, NewsSymbol.symbol)
        ).all()
    found = pd.DataFrame(rows, columns=["article_id", "symbol", "created_at", "headline"])
    found = found[~found["article_id"].isin(set(everything["article_id"]))]
    return dataset.drop_repeats(found, everything["headline"].map(dataset.headline_key))


def write_batches(items: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    key = items[["n", "article_id", "symbol", "kind"]].to_dict("records")
    (OUT / f"{name}.json").write_text(json.dumps(key))
    for start in range(0, len(items), BATCH):
        part = items.iloc[start : start + BATCH]
        lines = [
            f"{row.n} | {MARKET[row.symbol]} | {' '.join(row.headline.split())}"
            for row in part.itertuples()
        ]
        path = OUT / f"{name}_{start // BATCH + 1:02d}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"{len(items)} headlines in {-(-len(items) // BATCH)} files named {name}_NN.txt")


def main(market: str | None) -> None:
    rng = np.random.default_rng(SEED)
    usable, everything = labelled_sets()
    old = usable[usable["created_at"] < TEST_FROM]
    if market is not None:
        # Every old label of one market, less the ones the audit already holds.
        audited = {
            item["article_id"] for item in json.loads((OUT / "draw.json").read_text())
        }
        chosen = old[(old["symbol"] == market) & ~old["article_id"].isin(audited)]
        chosen = chosen.assign(kind="again")
        name = f"again_{market.replace('/', '')}"
    else:
        free = unlabelled_since(TEST_FROM, everything)
        free = free.assign(market=free["symbol"].map(MARKET))
        new = []
        for name_, size in NEW_PER_MARKET.items():
            part = free[free["market"] == name_]
            taken = {i for frame in new for i in frame["article_id"]}
            part = part[~part["article_id"].isin(taken)]
            if size is not None:
                part = part.iloc[rng.choice(len(part), size=min(size, len(part)), replace=False)]
            new.append(part)
        seen = set()
        peeked = OUT / "peeked.csv"  # training headlines read with their labels beforehand
        if peeked.is_file():
            seen = set(pd.read_csv(peeked)["article_id"])
        audit = []
        for symbol in ("BTC/USD", "SPY", "GLD"):
            part = old[(old["symbol"] == symbol) & ~old["article_id"].isin(seen)]
            audit.append(part.iloc[rng.choice(len(part), size=AUDIT_PER_MARKET, replace=False)])
        chosen = pd.concat(
            [pd.concat(new).assign(kind="new"), pd.concat(audit).assign(kind="audit")],
            ignore_index=True,
        )
        name = "draw"
    chosen = chosen.iloc[rng.permutation(len(chosen))].reset_index(drop=True)
    chosen["n"] = range(1, len(chosen) + 1)
    write_batches(chosen, name)
    say(str(chosen["kind"].value_counts().to_dict()))


LETTER = {"P": "positive", "N": "negative", "U": "neutral"}
LABELS_FILE = Path("backend/src/radar/sentiment_round4_labels.csv")


def merge() -> None:
    """Join the labels to their articles; say how often the two passes agree."""
    usable, _ = labelled_sets()
    first = usable.set_index("article_id")["sentiment"]
    rows = []
    for key_file in sorted(OUT.glob("*.json")):
        if key_file.stem not in ("draw",) and not key_file.stem.startswith("again_"):
            continue
        given: dict[int, str] = {}
        for path in sorted(OUT.glob(f"labels_{key_file.stem}_*.txt")):
            for line in path.read_text().split("\n"):
                if line.strip():
                    number, letter = line.split()
                    given[int(number)] = LETTER[letter]
        for item in json.loads(key_file.read_text()):
            if item["n"] not in given:
                raise ValueError(f"{key_file.stem}: number {item['n']} has no label")
            rows.append(
                {
                    "article_id": item["article_id"],
                    "symbol": item["symbol"],
                    "sentiment": given[item["n"]],
                    "split": "test3" if item["kind"] == "new" else "second",
                    "labelled_by": "claude",
                }
            )
    out = pd.DataFrame(rows).sort_values(["split", "article_id"])
    out.to_csv(LABELS_FILE, index=False, lineterminator="\n")
    again = out[out["split"] == "second"].assign(market=lambda f: f["symbol"].map(MARKET))
    again = again.assign(before=again["article_id"].map(first))
    again["same"] = again["before"] == again["sentiment"]
    table = again.groupby("market")["same"].agg(["size", "mean"])
    say(f"new test set: {int((out['split'] == 'test3').sum())}")
    say(out[out["split"] == "test3"].assign(m=lambda f: f["symbol"].map(MARKET))
        .groupby("m")["sentiment"].value_counts().unstack().to_string())
    say("the two passes agree:\n" + table.round(3).to_string())
    say(f"all markets: {again['same'].mean():.3f} of {len(again)}")
    say(pd.crosstab(again["before"], again["sentiment"]).to_string())


if __name__ == "__main__":
    if sys.argv[1:] == ["merge"]:
        merge()
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else None)
