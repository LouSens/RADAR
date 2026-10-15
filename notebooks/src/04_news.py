# %% [markdown]
# # Two-Stage Parameter-Efficient Adaptation of FinBERT for Three-Class Sentiment Classification of Financial News Headlines
#
# **Abstract.** This notebook documents, end to end, the construction of a three-class
# (positive, negative, neutral) sentiment classifier for the financial news headlines that
# the RADAR application ingests from the Alpaca news API. Starting from FinBERT [1], a
# BERT-base encoder [2] further pre-trained on financial text, the model is adapted in two
# stages: (A) *task-adaptive pre-training* (TAPT) [3], which continues the masked-language-
# modelling objective on the unlabelled headlines of the training period, and (B)
# supervised fine-tuning with *low-rank adaptation* (LoRA) [4] on a labelled sample drawn
# from the same archive. Labels follow a written annotation rubric and were produced in
# independent blind passes, whose consistency is reported with Cohen's κ [8] and Fleiss'
# κ [9]. Every split respects time order and is separated by an embargo [13]; the test
# period is evaluated exactly once; results carry bootstrap confidence intervals [12], an
# exact McNemar test [10] and calibration diagnostics [11], [16]. The full pipeline runs on
# one consumer laptop GPU with 6 GB of memory.
#
# **Index terms:** financial sentiment analysis, FinBERT, task-adaptive pre-training,
# low-rank adaptation, annotation agreement, temporal evaluation.
#
# **Research questions.**
#
# * **RQ1.** What is the quality of the raw news archive, and what curation does it require? (§3–§6)
# * **RQ2.** Does TAPT on the feed's own unlabelled text lower held-out masked-language-model
#   perplexity, and does it improve the downstream classifier over LoRA fine-tuning alone? (§9, §11)
# * **RQ3.** How accurately does the final model classify headlines from a later, unseen
#   period, overall, per class and per ticker, relative to the untuned FinBERT? (§12)
#
# **Contributions.** (i) An auditable curation pipeline for a heavily templated news feed;
# (ii) an annotation rubric that fixes the subject of the sentiment, separates reported
# facts from opinion, states a contrast rule and specifies the treatment of reported market
# impact; (iii) a two-stage TAPT + LoRA recipe that fits a 6 GB GPU, including a correction
# for the masked-language-model head absent from the FinBERT checkpoint; (iv) a strictly
# temporal evaluation protocol with a single use of the test set.
#
# **Scope of the output.** The classifier describes the tone of a headline. It is not a
# forecast of price direction and is not used as one.
#
# ```
# raw Alpaca news ──► audit ──► clean ──► time split ──┬─► unlabelled train-period corpus ──► stage A: TAPT (masked LM, LoRA, merged)
#  (3 tickers)                                         │                                              │
#                                                      └─► labelling sample ──► labels (rubric v2)    ▼
#                                                                                   └────────► stage B: LoRA classifier ──► test once ──► saved model + card
# ```
#
# **Reproducibility.** The notebook is self-contained: it imports nothing from the RADAR
# application and requires no database. Its inputs are the raw Parquet files under
# `data/raw/alpaca_news/`, the rubric `notebooks/labels/RUBRIC.md`, the drawn sample
# `notebooks/labels/sample.csv` and the labels `notebooks/labels/tone_labels.csv`. The
# labels file contains article identifiers and class indices only; headline text is the
# news provider's and is neither committed nor printed in the committed copy.
#
# | Switch | Default | Effect |
# |---|---|---|
# | `FAST_RUN` | off (`TONE_FAST=1` enables it) | Reduced corpus and one short pass per stage, to verify that every cell executes. Its figures are **not results** |
# | `SHOW_TEXT` | off in the committed build | Print headline text in the error analysis; the committed copy reports counts only |
# | `RUN_TEST` | `True` | Evaluate the test period once and write the model card |
#
# **Contents.** §1 Experimental setup · §2 Data source · §3 Data-quality audit · §4 Cleaning
# and curation · §5 Exploratory data analysis · §6 Tokenisation and truncation · §7 Temporal
# partition · §8 Annotation · §9 Stage A: task-adaptive pre-training · §10 Class and ticker
# imbalance · §11 Stage B: LoRA fine-tuning · §12 Evaluation on the test period · §13 Error
# analysis · §14 Model artefact · §15 Conclusions, limitations and references

# %% [markdown]
# ## 1. Experimental Setup
#
# The cell below loads the libraries, fixes the random seeds of Python, NumPy and PyTorch,
# and reports the GPU. Mixed-precision arithmetic (16-bit floating point for matrix
# products, 32-bit for accumulation and the optimiser state) [15] is enabled when a GPU is
# present. GPU kernels are not bit-for-bit deterministic, so repeated runs can differ in
# the third decimal place; the size of this run-to-run variation is measured directly by
# the multi-seed ablation of §11.

# %%
import json
import math
import os
import random
import re
import time
import warnings
from collections import Counter
from html import unescape
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import transformers
from IPython.display import Markdown, display
from matplotlib.colors import LinearSegmentedColormap
from peft import LoraConfig, TaskType, get_peft_model
from scipy.stats import binomtest
from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score, precision_recall_fscore_support
from torch.utils.data import DataLoader, WeightedRandomSampler
from transformers import (
    AutoModelForMaskedLM,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    get_linear_schedule_with_warmup,
)

transformers.utils.logging.set_verbosity_error()
transformers.utils.logging.disable_progress_bar()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Run from the repository root whether the notebook is opened from notebooks/ or the root.
if not Path("data").is_dir() and Path("../data").is_dir():
    os.chdir("..")

COMMITTED_BUILD = os.environ.get("TONE_COMMITTED_BUILD") == "1"  # set by build_notebooks.py
FAST_RUN = os.environ.get("TONE_FAST") == "1"  # a quick check that every cell runs
SHOW_TEXT = not COMMITTED_BUILD  # provider headlines are never printed in the committed copy
RUN_TEST = True

SEED = 13
BASE_MODEL = "ProsusAI/finbert"  # BERT-base further trained on financial text
MLM_HEAD_DONOR = "bert-base-uncased"  # FinBERT's checkpoint has no masked-LM head (section 9)
MODEL_VERSION = "finbert-tone-1"

RAW_NEWS = Path("data/raw/alpaca_news")
LABEL_DIR = Path("notebooks/labels")
RUBRIC_PATH = LABEL_DIR / "RUBRIC.md"
SAMPLE_PATH = LABEL_DIR / "sample.csv"  # which articles are labelled, and for which split
LABELS_PATH = LABEL_DIR / "tone_labels.csv"  # article_id, pass, label, labelled_by
WORK = Path("data/research/tone") / ("fast" if FAST_RUN else "full")
BATCHES = Path("data/labels/tone_v2")  # headline text for labellers: gitignored
MODEL_DIR = WORK / "model" if FAST_RUN else Path("data/models/finbert-tone")
WORK.mkdir(parents=True, exist_ok=True)

# The three classes, in the order of FinBERT's own output head.
CLASSES = ("positive", "negative", "neutral")
TICKERS = {"BTCUSD": "BTC/USD", "GLD": "GLD", "SPY": "SPY"}  # folder -> app symbol
MARKET = {"BTCUSD": "Bitcoin", "GLD": "Gold", "SPY": "US stocks"}


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


seed_everything(SEED)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
USE_AMP = DEVICE == "cuda"
if DEVICE == "cuda":
    props = torch.cuda.get_device_properties(0)
    print(f"GPU: {props.name}, {props.total_memory / 2**30:.1f} GB")
else:
    print("No GPU found: everything runs on the CPU and stage A/B will be slow.")
print(f"torch {torch.__version__}, transformers {transformers.__version__}, fast run: {FAST_RUN}")

# %% [markdown]
# **Figure conventions.** Colours follow the Okabe–Ito palette [18], which remains
# distinguishable under the common forms of colour-vision deficiency. Each class and each
# ticker keeps one colour throughout: positive bluish green, negative vermillion, neutral
# grey; Bitcoin blue, gold orange, US stocks reddish purple. Every figure is followed by a
# caption that states the quantity shown, the period covered and the sample size *n*.

# %%
TONE_COLOUR = {"positive": "#009E73", "negative": "#D55E00", "neutral": "#8C8C8C"}
TICKER_COLOUR = {"BTCUSD": "#0072B2", "GLD": "#E69F00", "SPY": "#CC79A7"}
INK, MUTED = "#1F2328", "#6E7781"
SEQUENTIAL = LinearSegmentedColormap.from_list("seq", ["#F7FBFF", "#6BAED6", "#08306B"])

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "savefig.dpi": 200,
        "figure.figsize": (9, 4.2),
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": INK,
        "axes.edgecolor": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "legend.frameon": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
    }
)


def caption(text: str) -> None:
    """A figure caption under the plot: what is shown, the window and the sample size."""
    display(Markdown(f"<small>*{text}*</small>"))


# %% [markdown]
# ## 2. Data Source
#
# Headlines are taken from the Alpaca market-data news API, which redistributes articles
# from Benzinga tagged with the ticker symbols they concern. RADAR stores each API response
# unchanged as an append-only Parquet file, partitioned by the ticker under which it was
# requested: `BTCUSD` (Bitcoin), `GLD` (SPDR Gold Shares, whose news RADAR attaches to PAX
# Gold) and `SPY` (SPDR S&P 500, standing for US equities). Because every scheduled refresh
# re-requests recent articles, one article identifier appears in many files. Only the seven
# columns required here are read, which bounds memory use on a 16 GB machine.

# %%
COLUMNS = ["id", "headline", "summary", "created_at", "updated_at", "source", "symbols"]
frames = []
for folder in TICKERS:
    files = sorted((RAW_NEWS / folder).rglob("*.parquet"))
    for path in files:
        part = pd.read_parquet(path, columns=COLUMNS)
        part["ticker"] = folder
        frames.append(part)
raw = pd.concat(frames, ignore_index=True)
raw["created_at"] = pd.to_datetime(raw["created_at"], utc=True)
raw["updated_at"] = pd.to_datetime(raw["updated_at"], utc=True)
print(f"{len(raw):,} stored rows from {len(frames):,} files")
display(
    raw.groupby("ticker")
    .agg(rows=("id", "size"), articles=("id", "nunique"), first=("created_at", "min"), last=("created_at", "max"))
    .assign(first=lambda d: d["first"].dt.date, last=lambda d: d["last"].dt.date)
)

# %% [markdown]
# ## 3. Data-Quality Audit
#
# Twelve checks quantify each defect before any transformation is applied, so that every
# cleaning step in §4 is justified by a measured count. Stored rows are first reduced to
# one row per (article, ticker) pair, keeping the latest revision. Shares are computed over
# unique articles, except the refetch count, whose denominator is the number of stored rows.

# %%
latest = raw.sort_values("updated_at").drop_duplicates(["id", "ticker"], keep="last")
articles = latest.drop_duplicates("id", keep="last")
_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")


def audit(frame: pd.DataFrame) -> pd.DataFrame:
    h = frame["headline"].fillna("")
    words = h.str.split().str.len()
    non_ascii = h.map(lambda s: sum(ord(c) > 127 for c in s) / max(len(s), 1))
    keys = h.str.lower().str.replace(_NUMBER, "#", regex=True).str.replace(_NOT_WORD, " ", regex=True).str.strip()
    checks = {
        "refetched copies of the same article": len(raw) - len(latest),
        "articles filed under more than one ticker": int((latest.groupby("id").size() > 1).sum()),
        "empty headline": int((h.str.strip() == "").sum()),
        "empty source field": int((frame["source"].fillna("") == "").sum()),
        "HTML entity in headline (&amp; etc.)": int(h.str.contains(r"&[a-z]+;|&#\d+;", regex=True).sum()),
        "revision or exchange tag ((UPDATED), (NYSE:X))": int(
            h.str.contains(r"\((?:UPDATED|CORRECTED|NYSE|NASDAQ|AMEX|ARCA|OTC|CRYPTO|BATS|TSX)\b", case=False, regex=True).sum()
        ),
        "fewer than 4 words": int((words < 4).sum()),
        "more than 30 words": int((words > 30).sum()),
        "all capitals": int((h.str.upper() == h).sum() - (h.str.strip() == "").sum()),
        "over 30% non-ASCII characters": int((non_ascii > 0.3).sum()),
        "repeat of a template (same text once numbers are removed)": int(keys.duplicated().sum()),
        "updated before it was created": int((frame["updated_at"] < frame["created_at"]).sum()),
    }
    out = pd.DataFrame({"count": checks})
    base = pd.Series(len(frame), index=out.index)
    base["refetched copies of the same article"] = len(raw)  # a share of stored rows
    out["share"] = (out["count"] / base).map("{:.1%}".format)
    out["of"] = np.where(out.index == "refetched copies of the same article", "stored rows", "unique articles")
    return out


quality = audit(articles)
display(quality)
caption(f"Checks on {len(articles):,} unique articles, {articles['created_at'].min().date()} to {articles['created_at'].max().date()}.")

# %% [markdown]
# **Findings and their consequences.**
#
# 1. *Refetched copies.* The archive repeats articles heavily because each refresh refetches
#    them. Keeping the latest revision per identifier is a precondition for every later count.
# 2. *Missing source field.* An empty `source` value is frequent among older SPY and GLD
#    records. It does not affect the headline text, so these records are retained.
# 3. *Markup and tags.* HTML entities and revision or exchange tags (e.g. "(UPDATED)",
#    "(NYSE:X)") carry no sentiment and are removed in §4. Letter case and punctuation are
#    retained because they can carry tone ("FALLS", "?").
# 4. *Long headlines.* Headlines exceeding 30 words are almost exclusively US-equity items
#    that quote a speaker verbatim (central-bank officials, government statements, social-
#    media posts). They are market-relevant and are retained; the portion the model reads is
#    set by the token limit derived in §6. Headlines of fewer than four words ("Market
#    Wrap") carry no evaluable sentiment and are removed.
# 5. *Templates.* Repeated templates ("Bitcoin whale moves 1,000 BTC …") are the principal
#    threat to validity. In labelled data, a template occurring on both sides of a split
#    leaks information from training into evaluation; in the unlabelled corpus, thousands
#    of copies would bias the masked-language model towards a few sentences. The labelled
#    sample therefore keeps one headline per template, and the corpus at most three.

# %% [markdown]
# ## 4. Cleaning and Curation
#
# Two functions define the text representation. The normalisation $c(h)$ maps a raw
# headline $h$ to the string the model reads: it collapses white space, decodes HTML
# entities and removes revision tags, exchange tags and a trailing attribution after a
# closing quotation mark, leaving words, case and punctuation intact. The template key
# $k(h)$ lower-cases the headline, replaces every number by `#` and removes punctuation, so
# that two headlines differing only in their figures share a key.
#
# The cell marked `app-parity` is executed by the repository's test suite and compared,
# character for character, with the normalisation the application applies before scoring.
# The model is therefore trained and deployed on identical inputs.

# %% app-parity
import re
from html import unescape

_EXCHANGE_TAG = re.compile(r"\s*\((?:NYSE|NASDAQ|AMEX|ARCA|OTC|CRYPTO|BATS|TSX)\b[^)]*\)?", re.I)
_REVISION_TAG = re.compile(r"\s*\((?:UPDATED|CORRECTED)\)", re.I)
_SOURCE_TAIL = re.compile(r"(?<=['\"\u2019\u201d])\s*-\s*[A-Z@][^-]{1,40}$")
_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")


def clean_headline(headline: str) -> str:
    """Even out white space, read HTML entities, drop revision and exchange tags and a
    source after a closing quote. Words, case and punctuation are left as they are."""
    text = " ".join(unescape(headline).split())
    text = _REVISION_TAG.sub("", text)
    text = _EXCHANGE_TAG.sub("", text)
    text = _SOURCE_TAIL.sub("", text)
    return " ".join(text.split())


def headline_key(headline: str) -> str:
    """The headline with case, punctuation and every number removed: two headlines that
    differ only in their figures share a key."""
    lowered = _NUMBER.sub("#", headline.lower())
    return _NOT_WORD.sub(" ", lowered).strip()


# %%
RARITY = {"GLD": 0, "BTCUSD": 1, "SPY": 2}  # an article under several tickers goes to the rarest


def curate(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ticker_rank"] = out["ticker"].map(RARITY)
    out = out.sort_values(["id", "ticker_rank"]).drop_duplicates("id", keep="first")
    out["text"] = out["headline"].fillna("").map(clean_headline)
    out["n_words"] = out["text"].str.split().str.len()
    non_ascii = out["text"].map(lambda s: sum(ord(c) > 127 for c in s) / max(len(s), 1))
    keep = (out["n_words"] >= 4) & (non_ascii <= 0.3)
    out = out[keep].copy()
    out["key"] = out["text"].map(headline_key)
    out["template_count"] = out.groupby("key")["id"].transform("size")
    out = out.sort_values("created_at").reset_index(drop=True)
    return out[["id", "ticker", "created_at", "text", "summary", "n_words", "key", "template_count"]]


clean = curate(latest)
funnel = pd.DataFrame(
    {
        "rows": [len(raw), len(latest), len(articles), len(clean), clean["key"].nunique()],
    },
    index=[
        "stored rows",
        "one per article and ticker",
        "one per article",
        "after length and language filters",
        "distinct templates",
    ],
)
display(funnel)

# %% [markdown]
# ## 5. Exploratory Data Analysis
#
# Four views characterise the curated corpus: publication volume over time, headline
# length, hour of publication and the vocabulary most characteristic of each ticker. The
# last uses the weighted log-odds ratio with an informative Dirichlet prior of Monroe,
# Colaresi and Quinn [7]. For word $w$, ticker $i$ and the remaining tickers $j$, with
# counts $y_w$, corpus sizes $n$ and prior $\alpha_w$ equal to the word's total count
# ($\alpha_0=\sum_w \alpha_w$),
#
# $$\hat\delta_w^{(i-j)}=\log\frac{y^i_w+\alpha_w}{n^i+\alpha_0-y^i_w-\alpha_w}-\log\frac{y^j_w+\alpha_w}{n^j+\alpha_0-y^j_w-\alpha_w},\qquad
# z_w=\frac{\hat\delta_w^{(i-j)}}{\sqrt{1/(y^i_w+\alpha_w)+1/(y^j_w+\alpha_w)}} .$$
#
# The prior shrinks the estimate for rare words, which would otherwise dominate a ranking
# by raw frequency ratio. Words seen fewer than 30 times are excluded.

# %%
monthly = clean.assign(month=clean["created_at"].dt.tz_convert(None).dt.to_period("M")).groupby(["month", "ticker"]).size().unstack(fill_value=0)
fig, ax = plt.subplots()
for folder in TICKERS:
    if folder in monthly:
        ax.plot(monthly.index.to_timestamp(), monthly[folder], color=TICKER_COLOUR[folder], lw=1.6, label=MARKET[folder])
ax.set_yscale("log")
ax.set_ylabel("articles per month (log scale)")
ax.set_xlabel("month")
ax.set_title("News volume by ticker")
ax.legend(loc="upper left")
plt.show()
caption(
    f"Cleaned unique articles per calendar month, {clean['created_at'].min().date()} to "
    f"{clean['created_at'].max().date()}; n = {len(clean):,}. Bitcoin coverage starts in 2021; gold is about 1/25 of US stocks."
)

# %%
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
bins = np.arange(4, 32)
for folder in TICKERS:
    part = clean[clean["ticker"] == folder]
    axes[0].hist(part["n_words"], bins=bins, density=True, histtype="step", lw=1.8, color=TICKER_COLOUR[folder], label=f"{MARKET[folder]} (n={len(part):,})")
axes[0].set_xlabel("words per headline")
axes[0].set_ylabel("share of headlines")
axes[0].set_title("Headline length")
axes[0].legend()
share = clean.groupby("ticker")["template_count"].apply(lambda s: (s > 1).mean())
axes[1].bar([MARKET[t] for t in share.index], share.values, color=[TICKER_COLOUR[t] for t in share.index])
axes[1].set_ylabel("share of headlines that repeat a template")
axes[1].set_title("Templated headlines")
axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
plt.tight_layout()
plt.show()
caption("Left: density of cleaned headline length by ticker. Right: share of each ticker's headlines whose numberless key appears more than once.")

# %%
hours = clean["created_at"].dt.hour
fig, ax = plt.subplots(figsize=(9, 3.4))
for folder in TICKERS:
    h = hours[clean["ticker"] == folder].value_counts(normalize=True).sort_index()
    ax.plot(h.index, h.values, marker="o", ms=3, color=TICKER_COLOUR[folder], label=MARKET[folder])
ax.set_xticks(range(0, 24, 2))
ax.set_xlabel("hour of publication (UTC)")
ax.set_ylabel("share of the ticker's articles")
ax.set_title("When the news is published")
ax.legend()
plt.show()
caption("Share of each ticker's cleaned articles by UTC hour. US-stock news clusters around the New York session (13:30–20:00 UTC); Bitcoin news runs around the clock.")

# %%
def distinctive_words(frame: pd.DataFrame, top: int = 12) -> pd.DataFrame:
    """Words most typical of each ticker: weighted log-odds with an informative prior
    (Monroe, Colaresi and Quinn, 2008), which keeps rare words from topping the list."""
    token = re.compile(r"[a-z][a-z'\-]{2,}")
    counts = {t: Counter(w for s in frame.loc[frame["ticker"] == t, "text"].str.lower() for w in token.findall(s)) for t in TICKERS}
    total = sum(counts.values(), Counter())
    a0 = sum(total.values())
    rows = {}
    for t, c in counts.items():
        rest = total - c
        n_i, n_j = sum(c.values()), sum(rest.values())
        scores = {}
        for w, prior in total.items():
            if prior < 30:
                continue
            yi, yj = c[w], rest[w]
            delta = math.log((yi + prior) / (n_i + a0 - yi - prior)) - math.log((yj + prior) / (n_j + a0 - yj - prior))
            scores[w] = delta / math.sqrt(1 / (yi + prior) + 1 / (yj + prior))
        rows[MARKET[t]] = [w for w, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:top]]
    return pd.DataFrame(rows)


display(distinctive_words(clean))
caption("The 12 words most distinctive of each ticker's headlines (z-scored log-odds, words seen at least 30 times). Single words, so no headline text is reproduced.")

# %% [markdown]
# **Interpretation.** The Bitcoin vocabulary concerns crypto-assets directly. The gold
# vocabulary is dominated by the language of daily market summaries ("Asia", "Europe",
# "markets", "while … slept") and of social-media trend digests: a substantial part of the
# news filed under the gold fund is general market commentary rather than news about gold.
# This has two consequences. First, because the rubric (§8) labels a headline for its own
# subject, such headlines are labelled for the market they describe. Second, an aggregate
# gold sentiment computed from this feed partly reflects general market sentiment, which
# is a limitation to be stated wherever that aggregate is displayed.

# %% [markdown]
# ## 6. Tokenisation and Truncation
#
# FinBERT uses the uncased WordPiece vocabulary of BERT [2], [17] (30,522 entries). The cost
# of self-attention grows quadratically and activation memory linearly with the padded
# sequence length, so the length limit $L$ should be the smallest that rarely truncates.
# Truncation removes tokens from the end of a headline, which is often where the decisive
# clause of a contrast construction appears ("…, but shares slide"). The decision rule,
# fixed before inspecting the distribution, is
#
# $$L^{*}=\min\{L\in\{32,48,64,96,128\}:\ \hat F(L)\ge 0.995\},$$
#
# where $\hat F$ is the empirical cumulative distribution of tokenised headline length,
# including the `[CLS]` and `[SEP]` tokens.

# %%
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
lengths = np.array([len(ids) for ids in tokenizer(clean["text"].tolist(), add_special_tokens=True)["input_ids"]])
unk_rate = float(np.mean([tokenizer.unk_token_id in ids for ids in tokenizer(clean["text"].sample(min(20000, len(clean)), random_state=SEED).tolist())["input_ids"]]))
CANDIDATES = (32, 48, 64, 96, 128)
coverage = pd.DataFrame(
    {"limit": CANDIDATES, "headlines kept whole": [float((lengths <= c).mean()) for c in CANDIDATES], "headlines truncated": [int((lengths > c).sum()) for c in CANDIDATES]}
)
MAX_LEN = next(c for c in CANDIDATES if (lengths <= c).mean() >= 0.995)
display(coverage.style.format({"headlines kept whole": "{:.2%}"}).hide(axis="index"))

fig, ax = plt.subplots(figsize=(9, 3.6))
ax.hist(lengths, bins=np.arange(0, lengths.max() + 2), color="#56B4E9", edgecolor="white")
ax.axvline(MAX_LEN, color=INK, ls="--", lw=1.2, label=f"chosen limit: {MAX_LEN} tokens")
ax.axvline(np.percentile(lengths, 99), color=MUTED, ls=":", lw=1.2, label=f"99th percentile: {np.percentile(lengths, 99):.0f}")
ax.set_xlabel("word pieces per headline, with [CLS] and [SEP]")
ax.set_ylabel("headlines")
ax.set_title("Token length of cleaned headlines")
ax.legend()
plt.show()
caption(
    f"FinBERT's WordPiece tokenizer on all {len(lengths):,} cleaned headlines. Median {np.median(lengths):.0f}, maximum {lengths.max()}; "
    f"{unk_rate:.2%} of headlines contain an unknown-token piece. MAX_LEN = {MAX_LEN} truncates {int((lengths > MAX_LEN).sum()):,}."
)

# %% [markdown]
# ## 7. Temporal Partition
#
# Financial language is non-stationary: new assets, tickers and events enter the
# vocabulary over time. A classifier must therefore be evaluated on a period that follows
# the one it was trained on. The archive is partitioned into three windows:
#
# * **Test period:** the most recent six months (from 1 April 2026), used only in §12.
# * **Training and validation pool:** all earlier articles, separated from the test period
#   by a **seven-day embargo** [13], so that a story reported over several days cannot appear
#   on both sides of the boundary.
# * **Validation set:** the most recent 15% of each ticker's labelled pool (§8.2).
#
# The unlabelled corpus for stage A is drawn from the pool only. Pre-training on test-period
# text, even without labels, would expose the model to the vocabulary of the evaluation
# period, a form of transductive leakage.

# %%
TEST_START = pd.Timestamp("2026-04-01", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
clean["period"] = np.where(clean["created_at"] >= TEST_START, "test", np.where(clean["created_at"] < TEST_START - EMBARGO, "pool", "embargo"))
display(clean.pivot_table(index="ticker", columns="period", values="id", aggfunc="size", fill_value=0).rename(index=MARKET))

# %% [markdown]
# ## 8. Annotation
#
# ### 8.1 Annotation rubric
#
# Labels follow the written rubric reproduced below (`notebooks/labels/RUBRIC.md`). The
# class indices match the output order of the FinBERT classification head (0 positive,
# 1 negative, 2 neutral), so the base model's predictions and the labels share one scheme.
# The rubric resolves the four sources of inconsistency observed in earlier label sets:
#
# 1. **Subject of the sentiment:** the tone is judged for the headline's main subject, from
#    the perspective of an investor holding it.
# 2. **Factuality versus opinion:** reported facts (earnings against estimates, analyst
#    rating actions, deals, litigation, reported price moves) are labelled by their likely
#    effect on price; questions, listicles and speculative predictions are neutral.
# 3. **Contrast rule:** in headlines joined by *but, despite, even as, while, although*, the
#    label follows the main clause.
# 4. **Market impact:** a reported price move determines the label; routine notices and
#    directionless statistics are neutral; uncertain cases default to neutral, because a
#    polarity inversion is costlier than a missed weak polarity.

# %%
display(Markdown(RUBRIC_PATH.read_text(encoding="utf-8")))

# %% [markdown]
# ### 8.2 Sampling design
#
# Labelling the full archive is neither necessary nor efficient; unlabelled headlines
# contribute through stage A. The labelled sample is drawn once with a fixed seed and
# stored in `notebooks/labels/sample.csv`, so that it cannot change after annotation begins.
#
# * **Deduplication:** one headline per template key (the most recent), so no template is
#   labelled twice.
# * **Test set:** up to 300 headlines per ticker, drawn uniformly from the test period. Its
#   class distribution is the natural one, so test metrics describe the model on the feed
#   as it is.
# * **Training and validation pool:** up to 2,000 headlines per ticker, spread as evenly as
#   possible across calendar years and enriched for the minority classes. A uniform draw
#   would be predominantly neutral. The pool is therefore first scored by the untuned
#   FinBERT, and an equal number of headlines is drawn from each of its three predicted
#   classes. This stratification on a proxy prediction affects only *which* headlines are
#   annotated; every label is assigned under the rubric. It alters the class priors of the
#   training and validation sets, which is why the test set is drawn without it.
# * **Validation set:** the most recent 15% of each ticker's pool, so each ticker is
#   validated on months after its own training months. Validation windows of different
#   tickers overlap the training windows of others; this influences only model selection,
#   never the test.
#
# **Number of passes.** Each test headline receives three independent passes and is
# assigned the majority label; a three-way disagreement removes the headline as ambiguous.
# Each training headline receives one pass, and a random 15% receive a second to estimate
# agreement; where the two disagree, the headline is removed rather than assigned.

# %%
N_TEST_PER_TICKER, N_POOL_PER_TICKER, DOUBLE_SHARE = 300, 2000, 0.15


@torch.no_grad()
def predict_proba(model, texts: list[str], batch_size: int = 128) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(texts), batch_size):
        enc = tokenizer(texts[i : i + batch_size], padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt").to(DEVICE)
        with torch.autocast(DEVICE, dtype=torch.float16, enabled=USE_AMP):
            logits = model(**enc).logits
        out.append(torch.softmax(logits.float(), dim=-1).cpu().numpy())
    return np.concatenate(out) if out else np.empty((0, 3))


def even_over_years(cell: pd.DataFrame, take: int, seed: int) -> pd.DataFrame:
    """Up to `take` rows, as evenly over the calendar years as the rows allow: each year
    gets an equal quota, and what a thin year cannot fill passes to the others."""
    rng = np.random.default_rng(seed)
    years = {y: g.index.to_numpy()[rng.permutation(len(g))] for y, g in cell.groupby("year")}
    quota = dict.fromkeys(years, 0)
    left = min(take, len(cell))
    while left:
        open_years = [y for y in years if quota[y] < len(years[y])]
        share = max(1, left // len(open_years))
        for y in open_years:
            add = min(share, len(years[y]) - quota[y], left)
            quota[y] += add
            left -= add
            if not left:
                break
    return cell.loc[np.concatenate([years[y][: quota[y]] for y in years])]


def draw_sample(frame: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    one = frame[frame["period"] != "embargo"].sort_values("created_at").drop_duplicates("key", keep="last")
    base = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL).to(DEVICE)
    pool = one[one["period"] == "pool"].copy()
    pool["base_class"] = predict_proba(base, pool["text"].tolist()).argmax(axis=1)
    del base
    torch.cuda.empty_cache()
    parts = []
    for folder in TICKERS:
        test = one[(one["period"] == "test") & (one["ticker"] == folder)]
        parts.append(test.sample(min(N_TEST_PER_TICKER, len(test)), random_state=SEED).assign(split="test"))
        mine = pool[pool["ticker"] == folder].assign(year=lambda d: d["created_at"].dt.year)
        per_class = N_POOL_PER_TICKER // 3
        for c in range(3):
            cell = mine[mine["base_class"] == c]
            parts.append(even_over_years(cell, per_class, SEED + c).assign(split="pool"))
    sample = pd.concat(parts)[["id", "ticker", "created_at", "split"]].rename(columns={"id": "article_id"})
    pool_rows = sample["split"] == "pool"
    # Validation is the newest 15% of each ticker's pool, so each ticker is validated on
    # its own latest months.
    cutoff = sample[pool_rows].groupby("ticker")["created_at"].transform(lambda s: s.quantile(0.85))
    sample.loc[cutoff.index[sample.loc[cutoff.index, "created_at"] >= cutoff], "split"] = "validation"
    sample.loc[sample["split"] == "pool", "split"] = "train"
    sample["passes"] = np.where(sample["split"] == "test", 3, np.where(rng.random(len(sample)) < DOUBLE_SHARE, 2, 1))
    return sample.sort_values("created_at").reset_index(drop=True)


if SAMPLE_PATH.exists():
    sample = pd.read_csv(SAMPLE_PATH, parse_dates=["created_at"])
    print(f"sample read from {SAMPLE_PATH}: {len(sample):,} articles")
elif COMMITTED_BUILD or FAST_RUN:
    raise SystemExit("This run needs notebooks/labels/sample.csv: run the notebook by hand once to draw it.")
else:
    sample = draw_sample(clean)
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_csv(SAMPLE_PATH, index=False)
    print(f"sample drawn and saved to {SAMPLE_PATH}: {len(sample):,} articles")
display(sample.pivot_table(index="ticker", columns="split", values="article_id", aggfunc="size", fill_value=0).rename(index=MARKET))

# %% [markdown]
# ### 8.3 Annotation protocol
#
# Annotation is organised by pass. Pass 1 covers every sampled headline; pass 2 covers the
# test set and the doubly-annotated 15% of the training pool; pass 3 covers the test set.
# Each pass is divided into batches of at most 500 headlines in an order shuffled
# independently for that pass (`data/labels/tone_v2/batches/p{P}_{NNN}.csv`, not
# committed). Each batch is annotated by a separate annotator instance that receives only
# the rubric and the batch, and is instructed to judge every headline individually without
# keyword rules or auxiliary models; no annotator sees another pass. Answers are returned as
# `article_id,label` files and validated line by line (valid identifier, label in {0, 1, 2},
# no duplicates) before being merged into `notebooks/labels/tone_labels.csv`.
#
# **Annotator disclosure.** The annotators are instances of a large language model (Claude,
# Anthropic), not human experts. Agreement between passes therefore measures the
# consistency of the rubric as applied by that model, not agreement with human judgement;
# validation against a human-annotated subset is listed as future work in §15.

# %%
BATCH_SIZE = 500


def export_batches(sample: pd.DataFrame) -> int:
    folder = BATCHES / "batches"
    folder.mkdir(parents=True, exist_ok=True)
    text = clean.set_index("id")["text"]
    rows = sample.assign(headline=sample["article_id"].map(text))
    written = 0
    for p in (1, 2, 3):
        due = rows[rows["passes"] >= p].sample(frac=1, random_state=SEED + p)  # a new order per pass
        for n, start in enumerate(range(0, len(due), BATCH_SIZE)):
            due.iloc[start : start + BATCH_SIZE][["article_id", "headline"]].to_csv(folder / f"p{p}_{n:03d}.csv", index=False)
            written += 1
    return written


def merge_labels(sample: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for path in sorted((BATCHES / "out").glob("p*_*.csv")):
        p = int(re.match(r"p(\d)_", path.name).group(1))
        part = pd.read_csv(path, header=None, names=["article_id", "label"], comment="#", dtype=str)
        part = part[part["article_id"].str.strip().str.isdigit()]  # drops a header line if one was written
        part = part.assign(article_id=part["article_id"].astype(int), label=pd.to_numeric(part["label"].str.strip(), errors="coerce"))
        bad = ~part["label"].isin([0, 1, 2]) | ~part["article_id"].isin(sample["article_id"]) | part["article_id"].duplicated()
        if bad.any():
            raise ValueError(f"{path.name}: {int(bad.sum())} invalid lines")
        rows.append(part.assign(**{"pass": p, "labelled_by": "claude subagent, rubric v2"}))
    if not rows:
        return pd.DataFrame(columns=["article_id", "pass", "label", "labelled_by"])
    merged = pd.concat(rows).drop_duplicates(["article_id", "pass"], keep="last")
    merged.sort_values(["article_id", "pass"]).to_csv(LABELS_PATH, index=False)
    return merged


if not (FAST_RUN or COMMITTED_BUILD):
    print(f"{export_batches(sample)} batches written to {BATCHES / 'batches'}")
    if (BATCHES / "out").is_dir():
        print(f"{len(merge_labels(sample)):,} labels merged into {LABELS_PATH}")
labels = pd.read_csv(LABELS_PATH) if LABELS_PATH.exists() else pd.DataFrame(columns=["article_id", "pass", "label", "labelled_by"])
HAVE_LABELS = not labels.empty
print(f"labels on file: {len(labels):,} from {labels['article_id'].nunique():,} articles" if HAVE_LABELS else "No labels yet: sections 10 to 14 wait for them.")

# %% [markdown]
# ### 8.4 Inter-annotator agreement
#
# For two passes, Cohen's κ [8] corrects the observed agreement $p_o$ for the agreement
# $p_e$ expected by chance from the marginal label frequencies:
#
# $$\kappa=\frac{p_o-p_e}{1-p_e}.$$
#
# For the three test passes, Fleiss' κ [9] generalises this to $m$ raters. With $n_{ic}$ the
# number of raters assigning item $i$ to class $c$,
#
# $$P_i=\frac{1}{m(m-1)}\Big(\sum_c n_{ic}^2-m\Big),\qquad \bar P=\frac{1}{N}\sum_i P_i,\qquad
# p_c=\frac{1}{Nm}\sum_i n_{ic},\qquad \kappa_F=\frac{\bar P-\sum_c p_c^2}{1-\sum_c p_c^2}.$$
#
# On the scale of Landis and Koch [19], values between 0.81 and 1.00 indicate almost
# perfect agreement. Agreement between passes is also a practical ceiling on measured
# accuracy: a model cannot be expected to agree with one pass more consistently than an
# independent pass does.

# %%
def fleiss_kappa(table: np.ndarray) -> float:
    n = table.sum(axis=1)[0]
    p_j = table.sum(axis=0) / table.sum()
    p_i = (np.square(table).sum(axis=1) - n) / (n * (n - 1))
    p_bar, p_e = p_i.mean(), np.square(p_j).sum()
    return float((p_bar - p_e) / (1 - p_e))


def resolve(labels: pd.DataFrame, sample: pd.DataFrame) -> pd.DataFrame:
    """One label per article: the majority of its passes; three-way ties are dropped."""
    wide = labels.pivot_table(index="article_id", columns="pass", values="label", aggfunc="first")
    def vote(row: pd.Series) -> float:
        counts = Counter(int(v) for v in row.dropna())
        (top, k), *rest = counts.most_common()
        return np.nan if rest and rest[0][1] == k else top
    out = sample.merge(wide.apply(vote, axis=1).rename("label").reset_index(), on="article_id")
    return out.dropna(subset=["label"]).astype({"label": int})


if HAVE_LABELS:
    wide = labels.pivot_table(index="article_id", columns="pass", values="label", aggfunc="first")
    stats = {}
    if {1, 2} <= set(wide.columns):
        both = wide[[1, 2]].dropna()
        stats["pairs labelled twice"] = len(both)
        stats["raw agreement, pass 1 vs 2"] = f"{(both[1] == both[2]).mean():.1%}"
        stats["Cohen's kappa, pass 1 vs 2"] = f"{cohen_kappa_score(both[1], both[2]):.3f}"
    test_ids = sample.loc[sample["split"] == "test", "article_id"]
    three = wide.loc[wide.index.isin(test_ids)].dropna(subset=[c for c in (1, 2, 3) if c in wide.columns])
    if {1, 2, 3} <= set(wide.columns) and len(three):
        table = np.stack([(three[[1, 2, 3]].to_numpy() == c).sum(axis=1) for c in range(3)], axis=1)
        stats["test articles with three passes"] = len(three)
        stats["Fleiss' kappa, test"] = f"{fleiss_kappa(table):.3f}"
    display(pd.Series(stats, name="value").to_frame())
    data = resolve(labels, sample)
    data = data.merge(clean[["id", "text"]].rename(columns={"id": "article_id"}), on="article_id", how="left")
    print(f"{len(data):,} articles with a resolved label; {int(data['text'].isna().sum())} could not be matched to the archive")
    data = data.dropna(subset=["text"])

# %% [markdown]
# ## 9. Stage A: Task-Adaptive Pre-Training
#
# Gururangan et al. [3] showed that continuing pre-training on the unlabelled text of the
# target task improves a classifier fine-tuned afterwards, even for models already
# pre-trained on the broader domain. FinBERT was adapted to corporate reports and analyst
# text [1]; this feed adds crypto-asset terminology, ticker shorthand and recurring
# templates.
#
# **Objective.** The masked-language-modelling objective of BERT [2] selects 15% of the
# token positions $\mathcal M$ of each headline $x$ (of which 80% are replaced by `[MASK]`,
# 10% by a random token and 10% left unchanged) and minimises
#
# $$\mathcal L_{\text{MLM}}(\theta)=-\,\mathbb E_x\sum_{i\in\mathcal M}\log p_\theta\big(x_i\mid x_{\setminus\mathcal M}\big).$$
#
# **Two corrections.**
#
# 1. *Missing prediction head.* The FinBERT checkpoint contains a classification head but no
#    masked-language-model head; loading it for masked-language modelling initialises that
#    head at random, and early updates would be spent fitting the head rather than adapting
#    the encoder. FinBERT uses the vocabulary of `bert-base-uncased` unchanged, so the
#    pretrained head of that model (transform layer, layer normalisation and output bias) is
#    transplanted; the output projection remains tied to FinBERT's own embeddings.
# 2. *Corpus composition.* The corpus contains training-period text only (§7) and at most
#    three headlines per template (§3).
#
# **Adaptation and memory.** Stage A applies LoRA (§11) to the attention and feed-forward
# projections and merges the adapters into the weights afterwards, so stage B starts from a
# standard encoder. The prediction head scores all 30,522 vocabulary entries at every
# position, so an optimiser step accumulates gradients over several sub-batches to reach the
# stated effective batch size within 6 GB.
#
# **Evaluation.** Perplexity on held-out validation-period headlines,
# $\mathrm{PPL}=\exp\!\big(\tfrac{1}{|\mathcal M|}\sum_{i\in\mathcal M}-\log p_\theta(x_i\mid x_{\setminus\mathcal M})\big)$,
# is computed before and after adaptation with identical masks, so that the two values are
# directly comparable.

# %%
TAPT = dict(epochs=1 if FAST_RUN else 3, batch=64, accumulate=4, lr=5e-4, r=16, alpha=32, dropout=0.05, mask=0.15, warmup=0.06)
corpus = clean[clean["period"] == "pool"].copy()
corpus = corpus[corpus.groupby("key").cumcount() < 3]
labelled_ids = set(sample["article_id"])
held = corpus[corpus["id"].isin(sample.loc[sample["split"] == "validation", "article_id"])]
corpus = corpus[~corpus["id"].isin(held["id"])]
if FAST_RUN:
    corpus = corpus.sample(min(4000, len(corpus)), random_state=SEED)
    held = held.sample(min(300, len(held)), random_state=SEED)
print(f"TAPT corpus: {len(corpus):,} headlines; perplexity measured on {len(held):,} validation-period headlines")


def mlm_model():
    model = AutoModelForMaskedLM.from_pretrained(BASE_MODEL)
    donor = AutoModelForMaskedLM.from_pretrained(MLM_HEAD_DONOR)
    head = {k: v for k, v in donor.state_dict().items() if k.startswith("cls.predictions.") and "decoder.weight" not in k}
    missing = model.load_state_dict(head, strict=False)
    assert not [k for k in missing.unexpected_keys], missing.unexpected_keys
    model.tie_weights()
    del donor
    return model


collator = DataCollatorForLanguageModeling(tokenizer, mlm_probability=TAPT["mask"])


def mlm_batches(texts: list[str], batch: int, shuffle: bool, seed: int = SEED):
    enc = tokenizer(texts, truncation=True, max_length=MAX_LEN)
    items = [{"input_ids": ids} for ids in enc["input_ids"]]
    gen = torch.Generator().manual_seed(seed)
    return DataLoader(items, batch_size=batch, shuffle=shuffle, collate_fn=collator, generator=gen)


@torch.no_grad()
def perplexity(model, texts: list[str]) -> float:
    model.eval()
    torch.manual_seed(SEED)  # the same masks for every model compared
    total, count = 0.0, 0
    for b in mlm_batches(texts, 16, shuffle=False):
        b = {k: v.to(DEVICE) for k, v in b.items()}
        with torch.autocast(DEVICE, dtype=torch.float16, enabled=USE_AMP):
            loss = model(**b).loss
        n = int((b["labels"] != -100).sum())
        total, count = total + float(loss) * n, count + n
    return math.exp(total / count)


seed_everything(SEED)
mlm = mlm_model().to(DEVICE)
ppl_before = perplexity(mlm, held["text"].tolist())
mlm = get_peft_model(
    mlm,
    LoraConfig(r=TAPT["r"], lora_alpha=TAPT["alpha"], lora_dropout=TAPT["dropout"], target_modules=["query", "key", "value", "dense"], bias="none"),
)
trainable = sum(p.numel() for p in mlm.parameters() if p.requires_grad)
print(f"trainable parameters in stage A: {trainable:,} of {sum(p.numel() for p in mlm.parameters()):,}")

# The masked-LM head scores all 30,522 vocabulary words at every position, so one batch
# of 64 long headlines needs more than the card's 6 GB. Each optimiser step therefore
# adds up the gradients of ACCUMULATE smaller batches: the same effective batch, less memory.
loader = mlm_batches(corpus["text"].tolist(), TAPT["batch"] // TAPT["accumulate"], shuffle=True)
per_epoch = len(loader) // TAPT["accumulate"]
steps = TAPT["epochs"] * per_epoch if not FAST_RUN else min(100, per_epoch)
optim = torch.optim.AdamW([p for p in mlm.parameters() if p.requires_grad], lr=TAPT["lr"], weight_decay=0.01)
sched = get_linear_schedule_with_warmup(optim, int(TAPT["warmup"] * steps), steps)
scaler = torch.amp.GradScaler(enabled=USE_AMP)
torch.cuda.reset_peak_memory_stats() if DEVICE == "cuda" else None
tapt_log, step, started = [], 0, time.time()
mlm.train()
while step < steps:
    for i, b in enumerate(loader):
        b = {k: v.to(DEVICE) for k, v in b.items()}
        with torch.autocast(DEVICE, dtype=torch.float16, enabled=USE_AMP):
            loss = mlm(**b).loss / TAPT["accumulate"]
        scaler.scale(loss).backward()
        if (i + 1) % TAPT["accumulate"]:
            continue
        scaler.unscale_(optim)
        torch.nn.utils.clip_grad_norm_(mlm.parameters(), 1.0)
        scaler.step(optim)
        scaler.update()
        optim.zero_grad(set_to_none=True)
        sched.step()
        tapt_log.append(float(loss) * TAPT["accumulate"])
        step += 1
        if step >= steps:
            break
mlm = mlm.merge_and_unload()
ppl_after = perplexity(mlm, held["text"].tolist())
tapt_minutes = (time.time() - started) / 60
tapt_peak = torch.cuda.max_memory_allocated() / 2**30 if DEVICE == "cuda" else float("nan")
encoder_state = {k.removeprefix("bert."): v.detach().cpu() for k, v in mlm.state_dict().items() if k.startswith("bert.")}
del mlm, optim
torch.cuda.empty_cache()

fig, ax = plt.subplots(figsize=(9, 3.4))
smooth = pd.Series(tapt_log).rolling(max(1, len(tapt_log) // 50), min_periods=1).mean()
ax.plot(tapt_log, color="#56B4E9", lw=0.6, alpha=0.5, label="per step")
ax.plot(smooth, color="#0072B2", lw=1.8, label="rolling mean")
ax.set_xlabel("optimiser step")
ax.set_ylabel("masked-LM loss (nats)")
ax.set_title("Stage A training loss")
ax.legend()
plt.show()
caption(
    f"{steps:,} steps of batch {TAPT['batch']} on {len(corpus):,} headlines in {tapt_minutes:.1f} min; peak GPU memory {tapt_peak:.2f} GB. "
    f"Held-out perplexity {ppl_before:.1f} before and {ppl_after:.1f} after ({len(held):,} validation-period headlines, identical masks)."
)

# %% [markdown]
# ## 10. Class and Ticker Imbalance
#
# The labelled data are imbalanced in two dimensions: neutral headlines dominate, and US
# equities contribute far more articles than gold. Common remedies are reviewed in [20].
#
# **Why SMOTE is not applicable.** SMOTE [6] synthesises minority examples by interpolating
# between the feature vectors of nearest neighbours. The input of a fine-tuned transformer
# is a sequence of discrete token identifiers, between which interpolation produces no
# valid text; interpolating fixed sentence embeddings would instead train a classifier on a
# frozen encoder, which is a different model from the one fine-tuned here.
#
# **Adopted procedure.**
#
# * The annotation sample is already enriched for the minority classes (§8.2).
# * During training, a weighted sampler draws each example $i$ with probability
#   proportional to $w_i=1/|C(t_i,y_i)|$, where $C(t,y)$ is the set of training examples of
#   ticker $t$ and class $y$. Every (ticker × class) cell is thus drawn equally often in
#   expectation.
# * The loss is not additionally class-weighted. Applying both corrections compensates the
#   imbalance twice and biases predictions towards the minority classes, a fault identified
#   in the previous version of this pipeline.
# * Validation and test sets are never resampled, and metrics are reported per class and
#   per ticker.

# %%
if HAVE_LABELS:
    cells = data.pivot_table(index="ticker", columns="label", values="article_id", aggfunc="size", fill_value=0)
    cells = cells.reindex(columns=range(3), fill_value=0)
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    for ax, split in zip(axes, ("train", "validation", "test")):
        part = data[data["split"] == split].pivot_table(index="ticker", columns="label", values="article_id", aggfunc="size", fill_value=0).reindex(index=list(TICKERS), columns=range(3), fill_value=0)
        im = ax.imshow(part.to_numpy(), cmap=SEQUENTIAL, aspect="auto")
        for (i, j), v in np.ndenumerate(part.to_numpy()):
            ax.text(j, i, f"{v:,}", ha="center", va="center", color="white" if v > part.to_numpy().max() * 0.55 else INK, fontsize=9)
        ax.set_xticks(range(3), [f"{c}\n({i})" for i, c in enumerate(CLASSES)])
        ax.set_yticks(range(3), [MARKET[t] for t in TICKERS])
        ax.set_title(f"{split} (n={int(part.to_numpy().sum()):,})")
        ax.grid(False)
    fig.colorbar(im, ax=axes, shrink=0.8, label="labelled headlines")
    plt.show()
    caption("Labelled headlines per ticker and tone in each split, after resolving passes. Train and validation were enriched for the rarer tones; test keeps the feed's natural mix.")

# %% [markdown]
# ## 11. Stage B: LoRA Fine-Tuning
#
# LoRA [4] freezes a pretrained weight matrix $W_0\in\mathbb R^{d\times k}$ and learns a
# low-rank update, so that a layer computes
#
# $$h=W_0x+\frac{\alpha}{r}BAx,\qquad A\in\mathbb R^{r\times k},\ B\in\mathbb R^{d\times r},\ r\ll\min(d,k),$$
#
# with $B$ initialised to zero so that training starts from the pretrained function. The
# classification head is trained in full. With a few thousand labelled examples, the
# restricted update also acts as a regulariser.
#
# **Fixed configuration, declared before any run.** Adapters on the query, key, value and
# both feed-forward projections; $\alpha=2r$; adapter dropout 0.1; batch size 32; AdamW
# [14] with weight decay 0.01; linear decay after a warm-up of 6% of the *actual* number of
# optimisation steps; gradient-norm clipping at 1.0; mixed precision [15]; at most eight
# epochs with early stopping (patience 2) on validation macro-F1, retaining the best epoch
# rather than the last. Macro-F1 averages the per-class F1 scores, so each class counts
# equally regardless of its frequency:
#
# $$\mathrm{F1}_{\text{macro}}=\frac{1}{3}\sum_{c}\frac{2P_cR_c}{P_c+R_c},$$
#
# with $P_c$ and $R_c$ the precision and recall of class $c$.
#
# **Hyperparameter search.** Four configurations, declared here and compared on the
# validation set only:
#
# | Configuration | Rank $r$ | Learning rate |
# |---|---|---|
# | a | 8 | 2 × 10⁻⁴ |
# | b | 16 | 2 × 10⁻⁴ |
# | c | 16 | 5 × 10⁻⁴ |
# | d | 32 | 1 × 10⁻⁴ |
#
# **Ablation (RQ2).** The selected configuration is trained from two encoders, the
# TAPT-adapted encoder and the original FinBERT, each with three random seeds. The encoder
# with the higher mean validation macro-F1 is used for the final model, trained with the seed
# that scored highest on validation. The encoder comparison is made on validation only.

# %%
GRID = {"a": (8, 2e-4), "b": (16, 2e-4), "c": (16, 5e-4), "d": (32, 1e-4)}
if FAST_RUN:
    GRID = {"b": GRID["b"]}
B = dict(batch=32, epochs=1 if FAST_RUN else 8, patience=2, dropout=0.1, weight_decay=0.01, warmup=0.06)
ABLATION_SEEDS = (13,) if FAST_RUN else (13, 17, 23)


def encode(frame: pd.DataFrame) -> list[dict]:
    enc = tokenizer(frame["text"].tolist(), truncation=True, max_length=MAX_LEN)
    return [{"input_ids": i, "attention_mask": m, "labels": int(y)} for i, m, y in zip(enc["input_ids"], enc["attention_mask"], frame["label"])]


def pad(items: list[dict]) -> dict:
    batch = tokenizer.pad([{k: v for k, v in x.items() if k != "labels"} for x in items], return_tensors="pt")
    batch["labels"] = torch.tensor([x["labels"] for x in items])
    return batch


def balanced_sampler(frame: pd.DataFrame, seed: int) -> WeightedRandomSampler:
    cell = frame["ticker"] + ":" + frame["label"].astype(str)
    weights = 1.0 / cell.map(cell.value_counts()).to_numpy()
    return WeightedRandomSampler(torch.tensor(weights, dtype=torch.double), num_samples=len(frame), replacement=True, generator=torch.Generator().manual_seed(seed))


def classifier(r: int, from_tapt: bool):
    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL)
    if from_tapt:
        result = model.bert.load_state_dict(encoder_state, strict=False)
        # The masked-LM model has no pooler; FinBERT's pooler is kept.
        assert set(result.missing_keys) <= {"pooler.dense.weight", "pooler.dense.bias"}, result.missing_keys
    config = LoraConfig(
        task_type=TaskType.SEQ_CLS, r=r, lora_alpha=2 * r, lora_dropout=B["dropout"],
        target_modules=["query", "key", "value", "dense"], modules_to_save=["classifier"], bias="none",
    )
    return get_peft_model(model, config).to(DEVICE)


def macro_f1(y: np.ndarray, p: np.ndarray) -> float:
    return float(f1_score(y, p, labels=[0, 1, 2], average="macro", zero_division=0))


def train(train_df: pd.DataFrame, val_df: pd.DataFrame, r: int, lr: float, seed: int, from_tapt: bool = True):
    seed_everything(seed)
    model = classifier(r, from_tapt)
    loader = DataLoader(encode(train_df), batch_size=B["batch"], sampler=balanced_sampler(train_df, seed), collate_fn=pad)
    steps = B["epochs"] * len(loader)
    optim = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=B["weight_decay"])
    sched = get_linear_schedule_with_warmup(optim, int(B["warmup"] * steps), steps)
    scaler = torch.amp.GradScaler(enabled=USE_AMP)
    history, best, best_state, waited = [], -1.0, None, 0
    for epoch in range(1, B["epochs"] + 1):
        model.train()
        losses = []
        for b in loader:
            b = {k: v.to(DEVICE) for k, v in b.items()}
            with torch.autocast(DEVICE, dtype=torch.float16, enabled=USE_AMP):
                loss = model(**b).loss
            scaler.scale(loss).backward()
            scaler.unscale_(optim)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optim)
            scaler.update()
            optim.zero_grad(set_to_none=True)
            sched.step()
            losses.append(float(loss))
        prob = predict_proba(model, val_df["text"].tolist())
        y = val_df["label"].to_numpy()
        val_loss = float(-np.mean(np.log(prob[np.arange(len(y)), y] + 1e-12)))
        score = macro_f1(y, prob.argmax(axis=1))
        history.append({"epoch": epoch, "train_loss": np.mean(losses), "val_loss": val_loss, "val_macro_f1": score})
        if score > best:
            best, waited = score, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items() if "lora_" in k or "classifier" in k}
        else:
            waited += 1
            if waited >= B["patience"]:
                break
    model.load_state_dict(best_state, strict=False)
    return model, pd.DataFrame(history), best


# %%
if HAVE_LABELS:
    train_df = data[data["split"] == "train"].reset_index(drop=True)
    val_df = data[data["split"] == "validation"].reset_index(drop=True)
    if FAST_RUN:
        train_df = train_df.sample(min(300, len(train_df)), random_state=SEED)
    torch.cuda.reset_peak_memory_stats() if DEVICE == "cuda" else None
    search, histories, started = [], {}, time.time()
    for name, (r, lr) in GRID.items():
        model, history, best = train(train_df, val_df, r, lr, SEED)
        search.append({"setting": name, "rank": r, "learning rate": lr, "best epoch": int(history["val_macro_f1"].idxmax()) + 1, "validation macro-F1": best})
        histories[name] = history
        del model
        torch.cuda.empty_cache()
    search = pd.DataFrame(search).set_index("setting")
    BEST = search["validation macro-F1"].idxmax()
    BEST_R, BEST_LR = GRID[BEST]
    stage_b_peak = torch.cuda.max_memory_allocated() / 2**30 if DEVICE == "cuda" else float("nan")
    display(search.style.format({"learning rate": "{:.0e}", "validation macro-F1": "{:.3f}"}))
    caption(f"Validation macro-F1 of each setting (seed {SEED}); {len(train_df):,} training and {len(val_df):,} validation headlines; "
            f"{(time.time() - started) / 60:.1f} min in all, peak GPU memory {stage_b_peak:.2f} GB. Chosen: setting {BEST}.")

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    palette = ["#0072B2", "#E69F00", "#009E73", "#CC79A7"]
    for colour, (name, h) in zip(palette, histories.items()):
        axes[0].plot(h["epoch"], h["train_loss"], color=colour, ls="--", lw=1.2)
        axes[0].plot(h["epoch"], h["val_loss"], color=colour, lw=1.8, label=f"{name}: r={GRID[name][0]}, lr={GRID[name][1]:.0e}")
        axes[1].plot(h["epoch"], h["val_macro_f1"], color=colour, marker="o", ms=4, lw=1.8)
    axes[0].set_title("Loss (dashed: train, solid: validation)")
    axes[0].set_xlabel("epoch")
    axes[0].set_ylabel("cross-entropy (nats)")
    axes[0].legend(fontsize=8)
    axes[1].set_title("Validation macro-F1")
    axes[1].set_xlabel("epoch")
    axes[1].set_ylabel("macro-F1")
    plt.tight_layout()
    plt.show()
    caption("Learning curves for each pre-declared setting. Early stopping keeps the epoch with the highest validation macro-F1.")

# %%
if HAVE_LABELS:
    ablation, models = [], {}
    for from_tapt in (True, False):
        for seed in ABLATION_SEEDS:
            model, _, best = train(train_df, val_df, BEST_R, BEST_LR, seed, from_tapt)
            ablation.append({"encoder": "TAPT + LoRA" if from_tapt else "FinBERT + LoRA (no TAPT)", "seed": seed, "validation macro-F1": best})
            key = ("tapt" if from_tapt else "plain", seed)
            models[key] = {k: v.cpu() for k, v in model.state_dict().items() if "lora_" in k or "classifier" in k}
            del model
            torch.cuda.empty_cache()
    ablation = pd.DataFrame(ablation)
    summary = ablation.groupby("encoder")["validation macro-F1"].agg(["mean", "std", "count"])
    display(summary.style.format({"mean": "{:.3f}", "std": "{:.3f}"}))
    TAPT_HELPED = summary.loc["TAPT + LoRA", "mean"] > summary.loc["FinBERT + LoRA (no TAPT)", "mean"]
    FINAL_TAPT = bool(TAPT_HELPED)
    FINAL_SEED = ablation[ablation["encoder"] == ("TAPT + LoRA" if FINAL_TAPT else "FinBERT + LoRA (no TAPT)")].sort_values("validation macro-F1").iloc[-1]["seed"]
    caption(f"Setting {BEST} (r={BEST_R}, lr={BEST_LR:.0e}) from each encoder, {len(ABLATION_SEEDS)} seed(s) each. "
            f"The final model uses the {'TAPT' if FINAL_TAPT else 'plain FinBERT'} encoder, chosen on validation; seed {int(FINAL_SEED)}.")

# %% [markdown]
# ## 12. Evaluation on the Test Period
#
# The test period is evaluated once, after every choice above was made on the validation
# set. Four classifiers are compared: a majority-class baseline; the untuned FinBERT, whose
# head already predicts the same three classes in the same order; LoRA fine-tuning of the
# plain FinBERT encoder (seed 13); and the final model. When the ablation of §11 selects the
# plain encoder, as it did in this run, the third and fourth rows share the same encoder and
# configuration and differ only in the random seed; their difference then measures seed
# variation, not the effect of TAPT.
#
# * **Confidence intervals.** Accuracy and macro-F1 are reported with 95% percentile
#   bootstrap intervals [12] over $B=2{,}000$ resamples of the test headlines.
# * **Paired significance test.** McNemar's exact test [10] compares the final model with
#   the untuned FinBERT on the headlines where exactly one of them is correct. With $n_{01}$
#   and $n_{10}$ the two discordant counts, the two-sided $p$-value is that of a binomial
#   test of $n_{01}$ successes in $n_{01}+n_{10}$ trials with probability ½.
# * **Confusion matrices,** normalised by row, because confusing positive with negative is
#   costlier than confusing either with neutral.
# * **Calibration.** Temperature scaling [11] rescales the logits $z$ as
#   $\mathrm{softmax}(z/T)$, with $T$ chosen on the validation set to minimise the negative
#   log-likelihood; it changes confidence but never the predicted class. Calibration is
#   summarised by the expected calibration error [16] over ten equal-width confidence bins
#   $B_b$:
#   $$\mathrm{ECE}=\sum_{b}\frac{|B_b|}{n}\,\big|\mathrm{acc}(B_b)-\mathrm{conf}(B_b)\big|.$$

# %%
def rebuild(key: tuple[str, int]):
    model = classifier(BEST_R, key[0] == "tapt")
    model.load_state_dict(models[key], strict=False)
    return model


def bootstrap(y: np.ndarray, p: np.ndarray, n: int = 2000) -> tuple[tuple[float, float], tuple[float, float]]:
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(y), (n, len(y)))
    acc = (y[idx] == p[idx]).mean(axis=1)
    f1s = np.array([macro_f1(y[i], p[i]) for i in idx])
    return tuple(np.percentile(acc, [2.5, 97.5])), tuple(np.percentile(f1s, [2.5, 97.5]))


def report(y: np.ndarray, p: np.ndarray) -> dict:
    prec, rec, f1, sup = precision_recall_fscore_support(y, p, labels=[0, 1, 2], zero_division=0)
    return {
        "n": int(len(y)),
        "accuracy": float((y == p).mean()),
        "macro_f1": macro_f1(y, p),
        "classes": [{"label": CLASSES[i], "precision": float(prec[i]), "recall": float(rec[i]), "f1": float(f1[i]), "support": int(sup[i])} for i in range(3)],
    }


def ece(prob: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = prob.max(axis=1), prob.argmax(axis=1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def fit_temperature(prob: np.ndarray, y: np.ndarray) -> float:
    logits = np.log(prob + 1e-12)
    grid = np.linspace(0.5, 5.0, 91)
    losses = [-np.mean(np.log(np.exp(logits / t)[np.arange(len(y)), y] / np.exp(logits / t).sum(axis=1))) for t in grid]
    return float(grid[int(np.argmin(losses))])


def scale(prob: np.ndarray, t: float) -> np.ndarray:
    z = np.exp(np.log(prob + 1e-12) / t)
    return z / z.sum(axis=1, keepdims=True)


if HAVE_LABELS and RUN_TEST:
    test_df = data[data["split"] == "test"].reset_index(drop=True)
    y = test_df["label"].to_numpy()
    base = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL).to(DEVICE)
    prob_base = predict_proba(base, test_df["text"].tolist())
    del base
    plain_key = ("plain", sorted(k[1] for k in models if k[0] == "plain")[0])
    final_key = ("tapt" if FINAL_TAPT else "plain", int(FINAL_SEED))
    plain = rebuild(plain_key)
    prob_plain = predict_proba(plain, test_df["text"].tolist())
    del plain
    final = rebuild(final_key)
    prob_final = predict_proba(final, test_df["text"].tolist())
    prob_val = predict_proba(final, val_df["text"].tolist())
    T = fit_temperature(prob_val, val_df["label"].to_numpy())
    majority = int(pd.Series(train_df["label"]).mode()[0])
    rows = {}
    for name, p in {
        "majority class": np.full(len(y), majority),
        "FinBERT, untuned": prob_base.argmax(1),
        "FinBERT + LoRA (no TAPT)": prob_plain.argmax(1),
        "final model": prob_final.argmax(1),
    }.items():
        (a_lo, a_hi), (f_lo, f_hi) = bootstrap(y, p)
        rows[name] = {"accuracy": (y == p).mean(), "accuracy 95%": f"{a_lo:.3f}–{a_hi:.3f}", "macro-F1": macro_f1(y, p), "macro-F1 95%": f"{f_lo:.3f}–{f_hi:.3f}"}
    results = pd.DataFrame(rows).T
    display(results.style.format({"accuracy": "{:.3f}", "macro-F1": "{:.3f}"}))
    pred, pred_base = prob_final.argmax(1), prob_base.argmax(1)
    only_final, only_base = int(((pred == y) & (pred_base != y)).sum()), int(((pred != y) & (pred_base == y)).sum())
    mcnemar_p = binomtest(only_final, only_final + only_base, 0.5).pvalue if only_final + only_base else 1.0
    caption(f"{len(y):,} test headlines, {test_df['created_at'].min().date()} to {test_df['created_at'].max().date()}. "
            f"McNemar against untuned FinBERT: final model alone right on {only_final}, FinBERT alone right on {only_base}, exact p = {mcnemar_p:.2g}.")

# %%
if HAVE_LABELS and RUN_TEST:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, (name, p) in zip(axes, {"FinBERT, untuned": pred_base, "final model": pred}.items()):
        cm = confusion_matrix(y, p, labels=[0, 1, 2], normalize="true")
        ax.imshow(cm, cmap=SEQUENTIAL, vmin=0, vmax=1)
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", color="white" if v > 0.55 else INK)
        ax.set_xticks(range(3), CLASSES)
        ax.set_yticks(range(3), CLASSES)
        ax.set_xlabel("predicted")
        ax.set_ylabel("labelled")
        ax.set_title(name)
        ax.grid(False)
    plt.tight_layout()
    plt.show()
    caption("Row-normalised confusion matrices on the test headlines: each row shows where headlines with that label went. The corners (positive↔negative) are the costly errors.")

    per = []
    for folder in TICKERS:
        m = test_df["ticker"].to_numpy() == folder
        if m.sum() == 0:
            continue
        _, (lo, hi) = bootstrap(y[m], pred[m])
        per.append({"ticker": folder, "n": int(m.sum()), "macro_f1": macro_f1(y[m], pred[m]), "lo": lo, "hi": hi, "accuracy": float((y[m] == pred[m]).mean())})
    per = pd.DataFrame(per)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    axes[0].bar([MARKET[t] for t in per["ticker"]], per["macro_f1"], color=[TICKER_COLOUR[t] for t in per["ticker"]],
                yerr=[per["macro_f1"] - per["lo"], per["hi"] - per["macro_f1"]], capsize=4, ecolor=INK)
    for i, row in per.iterrows():
        axes[0].text(i, 0.03, f"n={row['n']}", ha="center", color="white", fontsize=9)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("macro-F1 (95% bootstrap interval)")
    axes[0].set_title("Final model by ticker")
    t_prob = scale(prob_final, T)
    for prob, colour, name in ((prob_final, "#D55E00", f"before (ECE {ece(prob_final, y):.3f})"), (t_prob, "#0072B2", f"after T={T:.2f} (ECE {ece(t_prob, y):.3f})")):
        conf, hit = prob.max(1), prob.argmax(1) == y
        edges = np.linspace(1 / 3, 1, 8)
        mids, accs = [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (conf > lo) & (conf <= hi)
            if m.sum() >= 10:
                mids.append(conf[m].mean())
                accs.append(hit[m].mean())
        axes[1].plot(mids, accs, marker="o", color=colour, label=name)
    axes[1].plot([1 / 3, 1], [1 / 3, 1], color=MUTED, ls="--", lw=1, label="perfect calibration")
    axes[1].set_xlabel("confidence (top probability)")
    axes[1].set_ylabel("share correct")
    axes[1].set_title("Calibration on test")
    axes[1].legend(fontsize=8)
    plt.tight_layout()
    plt.show()
    caption("Left: test macro-F1 per ticker with bootstrap intervals; small n gives wide intervals. Right: reliability diagram (bins with at least 10 headlines), temperature fitted on validation only.")

# %% [markdown]
# ## 13. Error Analysis
#
# The remaining errors are examined against the hard cases the rubric anticipates: headlines
# containing a contrast marker (§8.1, rule 3), headlines phrased as questions or
# speculation (rule 2), and the rest. The *polarity-inversion rate*, the share of headlines
# labelled positive and predicted negative or the reverse, isolates the most consequential
# error. The committed copy reports counts only; executed locally with `SHOW_TEXT`, it also
# lists the most confident misclassifications.

# %%
CONTRAST = re.compile(r"\b(but|despite|even as|while|although|though|yet|however)\b", re.I)
OPINION = re.compile(r"\?|\b(could|may|might|should|top \d|\d+ (stocks|reasons|cryptos))\b", re.I)
if HAVE_LABELS and RUN_TEST:
    errors = test_df.assign(predicted=pred, confidence=prob_final.max(1))
    groups = {"contrast clause": errors["text"].str.contains(CONTRAST), "question or speculation": errors["text"].str.contains(OPINION)}
    rows = []
    for name, m in {**groups, "neither": ~(groups["contrast clause"] | groups["question or speculation"])}.items():
        part = errors[m]
        rows.append({"headlines": name, "n": len(part), "accuracy": (part["label"] == part["predicted"]).mean() if len(part) else np.nan})
    display(pd.DataFrame(rows).set_index("headlines").style.format({"accuracy": "{:.3f}"}))
    caption("Test accuracy on headlines with a contrast word, with a question or speculative wording, and on the rest.")
    polar = errors[(errors["label"] != 2) & (errors["predicted"] != 2) & (errors["label"] != errors["predicted"])]
    print(f"positive and negative swapped: {len(polar)} of {len(errors)} test headlines")
    if SHOW_TEXT:
        wrong = errors[errors["label"] != errors["predicted"]].sort_values("confidence", ascending=False).head(15)
        display(wrong.assign(label=wrong["label"].map(dict(enumerate(CLASSES))), predicted=wrong["predicted"].map(dict(enumerate(CLASSES))))[["ticker", "text", "label", "predicted", "confidence"]])

# %% [markdown]
# ## 14. Model Artefact
#
# The LoRA adapters are merged into the base weights ($W=W_0+\tfrac{\alpha}{r}BA$), so the
# saved model loads as a standard Hugging Face sequence classifier with no additional
# library. A `model_card.json` file records the base model, the method, the input
# definition, the token limit, the training and test windows, and the test metrics in full.
# The RADAR application loads this model to score incoming headlines and displays the test
# metrics from the card beside every sentiment reading; when the card is absent, no accuracy
# figure is shown.

# %%
if HAVE_LABELS and RUN_TEST:
    merged = final.merge_and_unload()
    merged.config.id2label = dict(enumerate(CLASSES))
    merged.config.label2id = {c: i for i, c in enumerate(CLASSES)}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(MODEL_DIR)
    tokenizer.save_pretrained(MODEL_DIR)
    train_like = data[data["split"] != "test"]
    polar_mask = (y != 2) & (pred != 2)
    card = {
        "version": MODEL_VERSION,
        "base_model": BASE_MODEL,
        "method": f"{'TAPT (LoRA, merged) + ' if FINAL_TAPT else ''}LoRA r={BEST_R}, lr={BEST_LR:g}, merged",
        "input": "headline",
        "max_length": MAX_LEN,
        "labelled_by": sorted(labels["labelled_by"].unique().tolist()),
        "train_window": [str(train_like["created_at"].min().date()), str(train_like["created_at"].max().date())],
        "test_window": [str(test_df["created_at"].min().date()), str(test_df["created_at"].max().date())],
        "test": report(y, pred),
        "base_test": report(y, pred_base),
        "direction": {
            "n": int(len(y)),
            "opposite_rate": float((((y == 0) & (pred == 1)) | ((y == 1) & (pred == 0))).mean()),
            "both_polar": int(polar_mask.sum()),
            "same_direction": float((y[polar_mask] == pred[polar_mask]).mean()) if polar_mask.any() else None,
        },
        "by_symbol": {TICKERS[r["ticker"]]: {"n": int(r["n"]), "accuracy": float(r["accuracy"]), "macro_f1": float(r["macro_f1"])} for _, r in per.iterrows()},
        "temperature": T,
        "mcnemar_p_vs_base": float(mcnemar_p),
    }
    (MODEL_DIR / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"saved to {MODEL_DIR}")
    display(pd.json_normalize(card, max_level=0)[["version", "method", "max_length", "train_window", "test_window"]].T.rename(columns={0: "value"}))

# %% [markdown]
# ## 15. Conclusions
#
# The findings below are generated from the quantities computed in this notebook, so the
# text cannot diverge from the results.

# %%
lines = [
    f"* The archive held {len(raw):,} stored rows; {len(clean):,} unique, cleaned headlines remained after the audit.",
    f"* A limit of {MAX_LEN} tokens keeps {(lengths <= MAX_LEN).mean():.2%} of headlines whole.",
    f"* Stage A changed held-out masked-LM perplexity from {ppl_before:.1f} to {ppl_after:.1f}.",
]
if HAVE_LABELS:
    lines.append(f"* Setting {BEST} (r = {BEST_R}, learning rate {BEST_LR:.0e}) scored best on validation; "
                 f"TAPT {'raised' if TAPT_HELPED else 'did not raise'} mean validation macro-F1 over the plain encoder.")
if HAVE_LABELS and RUN_TEST:
    f = results.loc["final model"]
    b = results.loc["FinBERT, untuned"]
    lines.append(f"* On {len(y):,} test headlines the final model reached accuracy {f['accuracy']:.3f} ({f['accuracy 95%']}) and macro-F1 "
                 f"{f['macro-F1']:.3f} ({f['macro-F1 95%']}), against {b['accuracy']:.3f} and {b['macro-F1']:.3f} for untuned FinBERT (McNemar p = {mcnemar_p:.2g}).")
if FAST_RUN:
    lines.append("* **Fast run:** small corpus and one short pass per stage; these figures are not results.")
display(Markdown("\n".join(lines)))



# %% [markdown]
# ### 15.1 Limitations and threats to validity
#
# * **Annotator type.** Labels were produced by a large language model following the
#   rubric. High agreement between passes indicates a consistently applied rubric, not
#   agreement with human experts.
# * **Rubric coverage.** The rubric has no explicit rule for macroeconomic releases reported
#   against consensus estimates (e.g. "Industrial Production 0.5% vs 0.7% Est"); annotators
#   treated them as neutral. A revised rubric should state the expected sign of a surprise.
# * **Ticker attribution.** News filed under the gold fund is largely general market
#   commentary (§5), and US-equity headlines are predominantly statements by officials. The
#   per-ticker results describe the feed as filed, not news about the asset alone.
# * **Single provider.** All articles come from one provider; generalisation to other news
#   sources is not tested.
# * **Sample size per ticker.** The test set contains at most 300 headlines per ticker, so
#   per-ticker intervals are wide.
# * **Temporal drift.** A single test period of six months is evaluated; performance on later
#   periods may differ as the language of the feed evolves.
#
# ### 15.2 Future work
#
# A human-annotated subset of the test set, to measure agreement between the model
# annotators and human judgement; stronger baselines (full fine-tuning, larger encoders, a
# zero-shot large language model) and an external benchmark such as the Financial PhraseBank
# [5]; length-grouped batching to shorten stage A; and a rubric revision for macroeconomic
# releases.

# %% [markdown]
# ## References
#
# [1] D. Araci, "FinBERT: Financial sentiment analysis with pre-trained language models," arXiv:1908.10063, 2019.
#
# [2] J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, "BERT: Pre-training of deep bidirectional transformers for language understanding," in *Proc. NAACL-HLT*, 2019, pp. 4171–4186.
#
# [3] S. Gururangan, A. Marasović, S. Swayamdipta, K. Lo, I. Beltagy, D. Downey, and N. A. Smith, "Don't stop pretraining: Adapt language models to domains and tasks," in *Proc. ACL*, 2020, pp. 8342–8360.
#
# [4] E. J. Hu, Y. Shen, P. Wallis, Z. Allen-Zhu, Y. Li, S. Wang, L. Wang, and W. Chen, "LoRA: Low-rank adaptation of large language models," in *Proc. ICLR*, 2022.
#
# [5] P. Malo, A. Sinha, P. Korhonen, J. Wallenius, and P. Takala, "Good debt or bad debt: Detecting semantic orientations in economic texts," *J. Assoc. Inf. Sci. Technol.*, vol. 65, no. 4, pp. 782–796, 2014.
#
# [6] N. V. Chawla, K. W. Bowyer, L. O. Hall, and W. P. Kegelmeyer, "SMOTE: Synthetic minority over-sampling technique," *J. Artif. Intell. Res.*, vol. 16, pp. 321–357, 2002.
#
# [7] B. L. Monroe, M. P. Colaresi, and K. M. Quinn, "Fightin' words: Lexical feature selection and evaluation for identifying the content of political conflict," *Political Anal.*, vol. 16, no. 4, pp. 372–403, 2008.
#
# [8] J. Cohen, "A coefficient of agreement for nominal scales," *Educ. Psychol. Meas.*, vol. 20, no. 1, pp. 37–46, 1960.
#
# [9] J. L. Fleiss, "Measuring nominal scale agreement among many raters," *Psychol. Bull.*, vol. 76, no. 5, pp. 378–382, 1971.
#
# [10] Q. McNemar, "Note on the sampling error of the difference between correlated proportions or percentages," *Psychometrika*, vol. 12, no. 2, pp. 153–157, 1947.
#
# [11] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. ICML*, 2017, pp. 1321–1330.
#
# [12] B. Efron and R. J. Tibshirani, *An Introduction to the Bootstrap*. New York, NY, USA: Chapman & Hall, 1993.
#
# [13] M. López de Prado, *Advances in Financial Machine Learning*. Hoboken, NJ, USA: Wiley, 2018.
#
# [14] I. Loshchilov and F. Hutter, "Decoupled weight decay regularization," in *Proc. ICLR*, 2019.
#
# [15] P. Micikevicius, S. Narang, J. Alben, G. Diamos, E. Elsen, D. Garcia, B. Ginsburg, M. Houston, O. Kuchaiev, G. Venkatesh, and H. Wu, "Mixed precision training," in *Proc. ICLR*, 2018.
#
# [16] M. P. Naeini, G. F. Cooper, and M. Hauskrecht, "Obtaining well calibrated probabilities using Bayesian binning," in *Proc. AAAI*, 2015, pp. 2901–2907.
#
# [17] Y. Wu, M. Schuster, Z. Chen, Q. V. Le, M. Norouzi *et al.*, "Google's neural machine translation system: Bridging the gap between human and machine translation," arXiv:1609.08144, 2016.
#
# [18] M. Okabe and K. Ito, "Color universal design (CUD): How to make figures and presentations that are friendly to colorblind people," J*FLY, 2008. [Online]. Available: https://jfly.uni-koeln.de/color/
#
# [19] J. R. Landis and G. G. Koch, "The measurement of observer agreement for categorical data," *Biometrics*, vol. 33, no. 1, pp. 159–174, 1977.
#
# [20] H. He and E. A. Garcia, "Learning from imbalanced data," *IEEE Trans. Knowl. Data Eng.*, vol. 21, no. 9, pp. 1263–1284, 2009.
