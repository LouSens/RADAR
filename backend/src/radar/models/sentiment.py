"""F3. News sentiment: score each article's tone, then summarise tone over time.

Each article's headline and summary are scored by FinBERT, a language model trained on
financial text, which gives the probability that the tone is positive, negative, or
neutral. The article's score is `P(positive) - P(negative)`, from -1 to +1.

No lookahead: a bucket's figures use only articles published before the bucket ended.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import pandas as pd

MODEL_VERSION = "finbert-prosus-1"
MODEL_ID = "ProsusAI/finbert"
LABELS = ("positive", "negative", "neutral")
MAX_CHARACTERS = 2_000
DEFAULT_HALF_LIFE = pd.Timedelta(hours=24)


def article_text(headline: str, summary: str = "") -> str:
    """The text that is scored: the headline, then the summary if it adds anything."""
    headline = " ".join(headline.split())
    summary = " ".join(summary.split())
    if not summary or summary == headline:
        return headline[:MAX_CHARACTERS]
    joined = headline if headline.endswith((".", "!", "?")) else f"{headline}."
    return f"{joined} {summary}"[:MAX_CHARACTERS]


def score_of(probabilities: np.ndarray) -> np.ndarray:
    """`P(positive) - P(negative)` for rows of [positive, negative, neutral]."""
    scores: np.ndarray = probabilities[:, 0] - probabilities[:, 1]
    return scores


class Scorer(Protocol):
    """Anything that turns texts into rows of [positive, negative, neutral] probabilities."""

    version: str

    def probabilities(self, texts: Sequence[str]) -> np.ndarray: ...


class FinbertScorer:
    """FinBERT, on the graphics card when one is available and on the CPU otherwise.

    The model is downloaded from Hugging Face on first use. Needs the `nlp` extra
    (`uv sync --extra nlp`).
    """

    def __init__(
        self,
        model: str = MODEL_ID,
        version: str = MODEL_VERSION,
        batch_size: int = 64,
        device: str | None = None,
    ) -> None:
        """`model` is a Hugging Face model id, or a folder holding a fine-tuned model."""
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.version = version
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self._tokenizer = AutoTokenizer.from_pretrained(model)
        self._model = AutoModelForSequenceClassification.from_pretrained(model).to(self.device)
        self._model.eval()
        # Put the model's own label order into ours, whatever it is.
        names = {i: name.lower() for i, name in self._model.config.id2label.items()}
        self._order = [next(i for i, name in names.items() if name == label) for label in LABELS]

    def probabilities(self, texts: Sequence[str]) -> np.ndarray:
        torch = self._torch
        out: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            encoded = self._tokenizer(
                batch, padding=True, truncation=True, max_length=256, return_tensors="pt"
            ).to(self.device)
            with torch.no_grad():
                logits = self._model(**encoded).logits
            out.append(torch.softmax(logits, dim=-1)[:, self._order].cpu().numpy())
        return np.concatenate(out) if out else np.empty((0, len(LABELS)))


def aggregate(
    times: pd.DatetimeIndex,
    scores: np.ndarray,
    edges: pd.DatetimeIndex,
    half_life: pd.Timedelta = DEFAULT_HALF_LIFE,
) -> pd.DataFrame:
    """Summarise article scores into the buckets between consecutive `edges`.

    Returns one row per bucket, indexed by the bucket's end, with:

    - `article_count` and `score_mean`: the articles published inside the bucket
      (`score_mean` is empty for a bucket with none);
    - `score_decayed`: an average of every article published before the bucket ended,
      where an article's weight halves every `half_life`. Empty until the first article.
    """
    # Work in nanoseconds whatever resolution the inputs carry.
    raw = times.as_unit("ns").to_numpy(dtype="datetime64[ns]").astype("int64")
    order = np.argsort(raw, kind="stable")
    stamps = raw[order]
    values = np.asarray(scores, dtype=float)[order]
    bounds = edges.as_unit("ns").to_numpy(dtype="datetime64[ns]").astype("int64")
    # Articles in bucket k have bounds[k] <= t < bounds[k + 1].
    cuts = np.searchsorted(stamps, bounds, side="left")
    half = float(half_life.as_unit("ns").value)
    count = np.zeros(len(bounds) - 1, dtype=int)
    mean = np.full(len(bounds) - 1, np.nan)
    decayed = np.full(len(bounds) - 1, np.nan)
    weighted = 0.0
    weight = 0.0
    for k in range(len(bounds) - 1):
        end = bounds[k + 1]
        fade = 0.5 ** ((end - bounds[k]) / half)
        weighted *= fade
        weight *= fade
        inside = slice(cuts[k], cuts[k + 1])
        if cuts[k + 1] > cuts[k]:
            fresh = 0.5 ** ((end - stamps[inside]) / half)
            weighted += float(fresh @ values[inside])
            weight += float(fresh.sum())
            count[k] = cuts[k + 1] - cuts[k]
            mean[k] = float(values[inside].mean())
        if weight > 1e-12:
            decayed[k] = weighted / weight
    return pd.DataFrame(
        {"article_count": count, "score_mean": mean, "score_decayed": decayed}, index=edges[1:]
    )
