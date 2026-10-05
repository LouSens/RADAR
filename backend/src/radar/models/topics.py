"""News topics: assign each article one topic from a fixed list, with no training.

A pretrained language model is asked, for each topic, whether the sentence "This news
is about <topic description>" follows from the article. The topic it agrees with most
wins. This is called zero-shot classification: the model has never seen our labels.

The topic list is short on purpose and the same for every asset.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np

# Topic name -> the description the model is asked about.
TOPICS: dict[str, str] = {
    "regulation": "government regulation, new laws, or court rulings",
    "funds_flows": "investment funds, ETFs, or large investors moving money in or out",
    "security": "hacks, scams, fraud, or the collapse of a company",
    "macro": "the economy, central banks, interest rates, trade, or geopolitics",
    "adoption": "a company's business, products, earnings, or adoption by businesses",
    "price": "price moves, market commentary, or price forecasts",
    "other": "something unrelated to markets or the economy",
}
HYPOTHESIS = "This news is about {}."
MAX_CHARACTERS = 600
# Models tried on the labelled sample; the most accurate one is used (decision 030).
CANDIDATES = (
    "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
    "cross-encoder/nli-deberta-v3-small",
)
MODEL_ID = CANDIDATES[0]


class TopicScorer(Protocol):
    version: str

    def scores(self, texts: Sequence[str]) -> np.ndarray:
        """One row per text and one column per topic in `TOPICS`; rows sum to 1."""
        ...


def pick(scores: np.ndarray) -> tuple[list[str], np.ndarray]:
    """The winning topic of each row, and how strongly it won."""
    names = list(TOPICS)
    best = scores.argmax(axis=1)
    return [names[i] for i in best], scores[np.arange(len(scores)), best]


def version_of(model_id: str) -> str:
    return f"zeroshot:{model_id.split('/')[-1]}:1"


class ZeroShotTopics:
    """A natural-language-inference model used as a topic classifier.

    Runs on the graphics card when one is available. Needs the `nlp` extra.
    """

    def __init__(self, model_id: str = CANDIDATES[0], batch_size: int = 32) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.version = version_of(model_id)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.batch_size = batch_size
        self._tokenizer = AutoTokenizer.from_pretrained(model_id)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_id).to(self.device)
        self._model.eval()
        labels = {name.lower(): i for name, i in self._model.config.label2id.items()}
        self._entailment = labels["entailment"]
        self._hypotheses = [HYPOTHESIS.format(text) for text in TOPICS.values()]

    def scores(self, texts: Sequence[str]) -> np.ndarray:
        torch = self._torch
        n_topics = len(self._hypotheses)
        out: list[np.ndarray] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            premises = [text for text in batch for _ in range(n_topics)]
            hypotheses = self._hypotheses * len(batch)
            encoded = self._tokenizer(
                premises,
                hypotheses,
                padding=True,
                truncation="only_first",
                max_length=160,
                return_tensors="pt",
            ).to(self.device)
            with torch.no_grad(), torch.autocast(self.device, enabled=self.device == "cuda"):
                logits = self._model(**encoded).logits.float()
            agreement = logits[:, self._entailment].reshape(len(batch), n_topics)
            out.append(torch.softmax(agreement, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.empty((0, n_topics))
