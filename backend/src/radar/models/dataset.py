"""Building a labelled text dataset without leakage between its parts.

Leakage means the model is tested on something it has, in effect, already seen. Three
ways it can happen with news headlines, and what is done about each:

- The same or nearly the same headline in two parts. Many headlines are templates
  ("Bitcoin Whale Moves 2,901 BTC Off Coinbase"). Headlines are reduced to a key with
  the numbers removed, and each key is kept only once across the whole dataset.
- Testing on the past. News language drifts, so the parts are split by time: the model
  trains on the oldest articles, is tuned on later ones, and is tested on the newest.
- Reusing the test part to make choices. The validation part exists for that; the test
  part is scored once, at the end.
"""

import html
import re
from collections.abc import Iterable
from itertools import pairwise

import pandas as pd

SPLITS = ("train", "validation", "test")
_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")
# What a headline carries that says nothing about its tone.
_EXCHANGE_TAG = re.compile(r"\s*\((?:NYSE|NASDAQ|AMEX|ARCA|OTC|CRYPTO|BATS|TSX)\b[^)]*\)?", re.I)
_REVISION_TAG = re.compile(r"\s*\((?:UPDATED|CORRECTED)\)", re.I)
_SOURCE_TAIL = re.compile(r"(?<=['\"\u2019\u201d])\s*-\s*[A-Z@][^-]{1,40}$")
_SENTENCE_END = re.compile(r"[.!?][\"'\u2019\u201d)]*(?=\s|$)")


def headline_key(headline: str) -> str:
    """A headline with case, punctuation, and every number removed.

    Two headlines that differ only in their figures get the same key.
    """
    lowered = _NUMBER.sub("#", headline.lower())
    return _NOT_WORD.sub(" ", lowered).strip()


def drop_repeats(frame: pd.DataFrame, exclude_keys: Iterable[str] = ()) -> pd.DataFrame:
    """Keep the earliest article for each headline key, and none whose key is excluded.

    `frame` has columns `headline` and `created_at`.
    """
    keyed = frame.assign(key=frame["headline"].map(headline_key))
    keyed = keyed[~keyed["key"].isin(set(exclude_keys)) & (keyed["key"] != "")]
    return keyed.sort_values("created_at").drop_duplicates("key", keep="first")


def time_split(frame: pd.DataFrame, validation: float = 0.15, test: float = 0.15) -> pd.DataFrame:
    """Add a `split` column: oldest rows train, the next validate, the newest test.

    Rows are ordered by `created_at`. Every training row is older than every validation
    row, and every validation row older than every test row; rows that share the
    boundary instant go to the earlier part together.
    """
    ordered = frame.sort_values("created_at").reset_index(drop=True)
    n = len(ordered)
    stamps = ordered["created_at"]
    first_validation = stamps.iloc[int(n * (1 - validation - test))] if n else None
    first_test = stamps.iloc[int(n * (1 - test))] if n else None
    split = pd.Series("train", index=ordered.index)
    if n:
        split[stamps > first_validation] = "validation"
        split[stamps > first_test] = "test"
    return ordered.assign(split=split)


def check_no_leakage(frame: pd.DataFrame) -> None:
    """Raise if the parts overlap in articles, in headline keys, or in time."""
    keys = frame["headline"].map(headline_key)
    for column, values in (("article_id", frame["article_id"]), ("headline key", keys)):
        if values.duplicated().any():
            raise ValueError(f"The same {column} appears more than once")
    latest = frame.groupby("split")["created_at"].max()
    earliest = frame.groupby("split")["created_at"].min()
    for before, after in pairwise(SPLITS):
        if before in latest.index and after in earliest.index and latest[before] >= earliest[after]:
            raise ValueError(f"The {before} part is not older than the {after} part")


def clean_headline(headline: str) -> str:
    """A headline without the parts that carry no tone.

    White space is evened out, HTML entities are read, and a revision note
    ("(UPDATED)"), an exchange tag ("(NYSE:ORCL)") and a source after a closing quote
    ("' - Bloomberg") are removed. The words themselves are left as they are: case and
    punctuation carry tone in a headline.
    """
    text = " ".join(html.unescape(headline).split())
    text = _REVISION_TAG.sub("", text)
    text = _EXCHANGE_TAG.sub("", text)
    text = _SOURCE_TAIL.sub("", text)
    return " ".join(text.split())


def whole_sentences(summary: str) -> str:
    """A summary up to its last complete sentence, or nothing if it has none.

    Stored summaries are cut at a fixed length, often in the middle of a sentence. Half
    a sentence can turn its meaning around, so it is dropped.
    """
    text = clean_headline(summary)
    ends = [found.end() for found in _SENTENCE_END.finditer(text)]
    return text[: ends[-1]] if ends else ""


def model_text(
    headline: str,
    summary: str = "",
    market: str = "",
    *,
    with_asset: bool = False,
    with_summary: bool = False,
) -> str:
    """The text a tone model reads, built from the parts chosen.

    `with_asset` puts the market's name in front ("Gold: ..."), since one headline can
    be good news for one holding and bad for another. `with_summary` adds the summary's
    whole sentences, unless it only repeats the headline.
    """
    text = clean_headline(headline)
    if with_summary:
        extra = whole_sentences(summary)
        if extra and headline_key(extra) != headline_key(text):
            text = f"{text if text.endswith(('.', '!', '?')) else text + '.'} {extra}"
    return f"{market}: {text}" if with_asset and market else text


def walk_forward_blocks(n: int, block: int, blocks: int) -> list[tuple[range, range]]:
    """Positions to train on and to validate on, for rows already in time order.

    The last `blocks` stretches of `block` rows are each validated by a model trained
    on every row before that stretch, so no model is ever scored on rows older than
    something it was trained on.
    """
    if block <= 0 or blocks <= 0 or n <= block * blocks:
        raise ValueError("Not enough rows for that many blocks")
    starts = [n - block * (blocks - k) for k in range(blocks)]
    return [(range(0, start), range(start, start + block)) for start in starts]
