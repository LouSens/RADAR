"""News text cleaning and duplicate detection."""

import html
import re

import pandas as pd

DUPLICATE_WINDOW = pd.Timedelta(hours=24)

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean_text(text: str | None) -> str:
    """Strip HTML tags and entities and collapse whitespace."""
    if not text:
        return ""
    without_tags = _TAG.sub(" ", html.unescape(text))
    # Entities can hide a second layer of markup, for example "&lt;b&gt;".
    return _SPACE.sub(" ", _TAG.sub(" ", html.unescape(without_tags))).strip()


def find_duplicates(
    articles: pd.DataFrame, window: pd.Timedelta = DUPLICATE_WINDOW
) -> dict[int, int]:
    """Map each duplicate article id to the id of the earlier article it repeats.

    `articles` has columns `id`, `symbol`, `created_at`, `headline`. Two articles are
    duplicates when they share a symbol and an identical headline (ignoring case) and
    were published within `window` of each other. The earliest one is the original.
    """
    duplicates: dict[int, int] = {}
    frame = articles.assign(key=articles["headline"].str.casefold().str.strip())
    frame = frame[frame["key"] != ""].sort_values(["created_at", "id"])
    for _, group in frame.groupby(["symbol", "key"], sort=False):
        if len(group) < 2:
            continue
        ids: list[int] = group["id"].tolist()
        times: list[pd.Timestamp] = group["created_at"].tolist()
        original_id, original_time = ids[0], times[0]
        for article_id, created in zip(ids[1:], times[1:], strict=True):
            if created - original_time <= window:
                if article_id != original_id:
                    duplicates[int(article_id)] = int(original_id)
            else:
                original_id, original_time = article_id, created
    return duplicates
