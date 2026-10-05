"""The hand-labelled sample used to measure the news models.

`draw_sample` picks the same articles every time for a given seed. The sample with its
text is written under `data/`, which is never committed; the labels are kept in the
repo by article id only, with no article text.
"""

import csv
import io
import json
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.db.models import NewsArticle, NewsSymbol
from radar.universe import Universe

SAMPLE_SEED = 20261005
# Articles per primary asset. Gold has far less news, so it gets fewer.
SAMPLE_SIZES = {"BTC/USD": 80, "SPY": 80, "GLD": 40}
SAMPLE_PATH = Path("data/labels/sample.jsonl")
LABELS_FILE = "sentiment_labels.csv"


def draw_sample(
    session: Session,
    universe: Universe,
    sizes: dict[str, int] | None = None,
    seed: int = SAMPLE_SEED,
) -> pd.DataFrame:
    """A fixed random sample of stored articles, stratified by asset. Repeats left out."""
    sizes = sizes or SAMPLE_SIZES
    rng = np.random.default_rng(seed)
    frames = []
    taken: set[int] = set()
    for asset in universe.primary:
        wanted = sizes.get(asset.symbol, 0)
        if not wanted or asset.news_start is None:
            continue
        ids = [
            i
            for i in session.scalars(
                select(NewsArticle.id)
                .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
                .where(
                    NewsSymbol.symbol == asset.symbol,
                    NewsArticle.duplicate_of.is_(None),
                    NewsArticle.created_at >= pd.Timestamp(asset.news_start, tz="UTC"),
                )
                .order_by(NewsArticle.id)
            )
            if i not in taken
        ]
        chosen = sorted(rng.choice(ids, size=min(wanted, len(ids)), replace=False).tolist())
        taken.update(chosen)
        rows = session.execute(
            select(NewsArticle.id, NewsArticle.headline, NewsArticle.summary).where(
                NewsArticle.id.in_(chosen)
            )
        ).all()
        frames.append(
            pd.DataFrame(rows, columns=["article_id", "headline", "summary"]).assign(
                symbol=asset.symbol
            )
        )
    if not frames:
        return pd.DataFrame(columns=["article_id", "headline", "summary", "symbol"])
    return pd.concat(frames, ignore_index=True).sort_values("article_id", ignore_index=True)


def export_sample(sample: pd.DataFrame, path: Path = SAMPLE_PATH) -> None:
    """Write the sample with its text for labelling. The folder is not committed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sample.to_dict("records"):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_labels() -> pd.DataFrame:
    """The stored labels: `article_id`, `symbol`, `sentiment`, `topic`, `labelled_by`."""
    text = (resources.files("radar") / LABELS_FILE).read_text(encoding="utf-8")
    frame = pd.DataFrame(list(csv.DictReader(io.StringIO(text))))
    if frame.empty:
        return pd.DataFrame(columns=["article_id", "symbol", "sentiment", "topic", "labelled_by"])
    frame["article_id"] = frame["article_id"].astype("int64")
    return frame
