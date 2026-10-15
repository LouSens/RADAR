"""The headline text a tone model reads.

Notebook 04 trains the tone model on cleaned headlines and the app scores headlines
with it, so both must clean a headline the same way, character for character. The
notebook holds its own copy of these two functions in a cell marked `app-parity`, and
`tests/models/test_notebook_text.py` checks that the copies agree.
"""

import html
import re

_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")
# What a headline carries that says nothing about its tone.
_EXCHANGE_TAG = re.compile(r"\s*\((?:NYSE|NASDAQ|AMEX|ARCA|OTC|CRYPTO|BATS|TSX)\b[^)]*\)?", re.I)
_REVISION_TAG = re.compile(r"\s*\((?:UPDATED|CORRECTED)\)", re.I)
_SOURCE_TAIL = re.compile(r"(?<=['\"\u2019\u201d])\s*-\s*[A-Z@][^-]{1,40}$")


def headline_key(headline: str) -> str:
    """A headline with case, punctuation, and every number removed.

    Two headlines that differ only in their figures get the same key.
    """
    lowered = _NUMBER.sub("#", headline.lower())
    return _NOT_WORD.sub(" ", lowered).strip()


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
