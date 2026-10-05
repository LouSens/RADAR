"""The simple rival to the sentiment model: counting words from a finance word list.

Uses the Loughran-McDonald master dictionary, which marks words that read as positive
or negative in financial text. A text is positive when it has more positive words than
negative ones, negative in the reverse case, and neutral otherwise.

The dictionary is free for research use and is not part of this repository: it is
downloaded into `data/lexicons/` (see `radar lexicon`).
"""

import csv
import re
from collections.abc import Sequence
from pathlib import Path

MODEL_VERSION = "lm-wordlist-1"
DEFAULT_PATH = Path("data/lexicons/lm_master.csv")
WORD = re.compile(r"[A-Za-z]+")


class Lexicon:
    def __init__(self, positive: frozenset[str], negative: frozenset[str]) -> None:
        self.positive = positive
        self.negative = negative

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Lexicon":
        """Read the master dictionary. A word counts if its column holds a non-zero year."""
        positive: set[str] = set()
        negative: set[str] = set()
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                word = row["Word"].upper()
                if row["Positive"] not in ("0", ""):
                    positive.add(word)
                if row["Negative"] not in ("0", ""):
                    negative.add(word)
        return cls(frozenset(positive), frozenset(negative))

    def counts(self, text: str) -> tuple[int, int]:
        """How many positive and negative words the text holds."""
        words = [w.upper() for w in WORD.findall(text)]
        return sum(w in self.positive for w in words), sum(w in self.negative for w in words)

    def label(self, text: str) -> str:
        positive, negative = self.counts(text)
        if positive > negative:
            return "positive"
        if negative > positive:
            return "negative"
        return "neutral"

    def labels(self, texts: Sequence[str]) -> list[str]:
        return [self.label(text) for text in texts]
