# %% [markdown]
# # News tone: a three-class classifier for financial headlines
#
# This notebook takes labelled financial news headlines and trains a model that says
# whether a headline is **positive**, **negative** or **neutral** for the asset it is
# about. It goes from the raw file to a saved, documented model, one stage at a time,
# in the order the work is done.
#
# **It is self-contained.** All the code is in the cells below. It needs one data file
# and nothing from the RADAR app or its database. Run it cell by cell, top to bottom.
#
# | Switch (third cell) | Default | What it does |
# |---|---|---|
# | `DATA_PATH` | local path | Where the data file is. Examples for Colab and Kaggle are beside it |
# | `FAST_RUN` | `True` | 200 headlines and one pass, so every cell runs in a few minutes. Its figures are a check that the code works, **not results** |
# | `SHOW_EXAMPLES` | on when you run it, off in the committed copy | Show real headlines the model got wrong in the error analysis |
# | `RUN_TEST` | `False` | Score the test set. Done once, by the owner of the project |
# | `PUSH_TO_HUB` | `False` | Upload the saved model to a private Hugging Face repository |
# | `MIN_TEST_ACCURACY` | `None` | The upload happens only if test accuracy is at least this |
#
# The plan, the two-model comparison and the rule that picks the winner were written
# down before any run (`docs/DECISIONS.md`, decisions 101 to 103).
#
# ## 1. Setup
#
# *Are the packages, the random seeds and the graphics card ready?*

# %%
# Install what is missing, at the versions this notebook was written with (the project's
# uv.lock). Packages already at these versions are skipped. If anything is installed
# here, restart the kernel before going on.
import importlib.metadata as metadata

from IPython import get_ipython

PINNED = {
    "torch": "2.14.1",
    "transformers": "5.18.0",
    "tokenizers": "0.23.2",
    "sentencepiece": "0.2.2",
    "huggingface-hub": "1.33.0",
    "pandas": "3.0.6",
    "numpy": "2.5.3",
    "pyarrow": "25.0.1",
    "matplotlib": "3.11.2",
}


def installed(package: str) -> str | None:
    """The installed version without its build tag ("2.14.1+cu126" is "2.14.1")."""
    try:
        return metadata.version(package).split("+")[0]
    except metadata.PackageNotFoundError:
        return None


to_install = [f"{name}=={version}" for name, version in PINNED.items() if installed(name) != version]
if to_install:
    get_ipython().run_line_magic("pip", "install -q " + " ".join(to_install))
print("installed now:", to_install or "nothing, all packages were already at the pinned versions")

# %%
import atexit
import os
import gc
import hashlib
import html
import inspect
import itertools
import json
import math
import random
import re
import shutil
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # before the libraries load, so their start-up notes stay out

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import transformers
from IPython.display import Markdown, display
from transformers import (
    AutoConfig,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

transformers.utils.logging.set_verbosity_error()
transformers.utils.logging.disable_progress_bar()

SEED = 13  # every training run sets its own seed too (section 10)
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if DEVICE == "cuda":
    card_memory = torch.cuda.get_device_properties(0).total_memory / 2**30
    print(f"graphics card: {torch.cuda.get_device_name(0)}, {card_memory:.1f} GB")
else:
    print("no graphics card found: training will be very slow; keep FAST_RUN = True")
print({name: installed(name) for name in PINNED})

# %%
# --- the switches. Change these lines; nothing else needs editing. ---
DATA_PATH = Path("data/research/tone5/tone_dataset.parquet")
# Colab:   DATA_PATH = Path("/content/drive/MyDrive/radar/tone_dataset.parquet")
# Kaggle:  DATA_PATH = Path("/kaggle/input/radar-tone/tone_dataset.parquet")
FAST_RUN = True  # 200 headlines, one pass: a check that every cell runs, not a result
# Real headlines are shown when you run the notebook yourself. The copy built for the
# repository (backend/scripts/build_notebooks.py sets TONE_COMMITTED_BUILD) shows made-up ones only.
SHOW_EXAMPLES = os.environ.get("TONE_COMMITTED_BUILD") != "1"
RUN_TEST = False  # True scores the test set, once (section 15)
PUSH_TO_HUB = False  # True uploads the saved model to a private repository (section 16)
MIN_TEST_ACCURACY = None  # set a number such as 0.70 before pushing; None never pushes
MODEL_VERSION = "tone-radar-2"  # the name the app loads the model by
HUB_NAME = None  # the repository's name; None gives "<base model>-financial-news-sentiment"

# --- where results go. A fast run never writes where a full run does. ---
WORK = Path("data/research/tone5") / ("fast" if FAST_RUN else "full")
MODEL_DIR = WORK / "model" if FAST_RUN else Path("data/models") / MODEL_VERSION
IN_USE = Path("data/models/finbert-radar-1")  # the model in the app today, if you have it
EARLIER = Path("data/research/tone5/earlier_candidates.json")  # figures of dropped models
TEMP = Path(tempfile.mkdtemp(prefix="tone_"))  # training checkpoints; deleted at the end
atexit.register(shutil.rmtree, TEMP, True)  # also deleted when a run fails

# --- the size of the run ---
ROWS = 200 if FAST_RUN else None  # None: every labelled headline
BLOCK, BLOCKS = (30, 2) if FAST_RUN else (300, 3)  # validation blocks (section 7)
COMPARE_SEEDS = (13, 17)  # each candidate is trained with each of these on every block
FINAL_SEEDS = (13, 17) if FAST_RUN else (13, 17, 23)  # the winner, on the last block
PUBLISH_SEED = 13  # the one model that is saved; fixed here, not picked afterwards
SETTINGS = {
    "epochs": 1 if FAST_RUN else 8,
    "early_stopping_patience": 2,
    "learning_rate": 2e-5,
    "weight_decay": 0.01,
    "batch_size": 16,
    "warmup_share": 0.1,
}
MAX_TOKENS = 256
LABELS = ["positive", "negative", "neutral"]

INK, MUTED, GOOD, BAD, ACCENT = "#1c2030", "#8a8fa3", "#2f9e6e", "#d9534f", "#1f9bb8"
TONE_COLOUR = {"positive": GOOD, "negative": BAD, "neutral": MUTED}
plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.size": 9.5,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlelocation": "left",
        "axes.titleweight": "bold",
        "legend.frameon": False,
    }
)
pd.set_option("display.float_format", lambda value: f"{value:,.3f}")
pd.set_option("display.max_colwidth", 120)
WORK.mkdir(parents=True, exist_ok=True)


def say(text: str) -> None:
    """Show a sentence built from variables as ordinary notebook text."""
    display(Markdown(text))


def caption(text: str) -> None:
    """A caption: what a table or figure shows, how many headlines, from when to when."""
    mark = "**Fast run on 200 headlines: not a result.** " if FAST_RUN else ""
    say(f"<small>{mark}*{text}*</small>")


def blank(table: pd.DataFrame) -> pd.DataFrame:
    """The same table with an empty cell where there is no value."""
    return table.map(lambda value: "" if isinstance(value, float) and np.isnan(value) else value)


def stored(name: str) -> dict | None:
    """A stored result of this notebook, or None if that cell has not been run."""
    path = WORK / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def store(name: str, found: dict) -> dict:
    (WORK / f"{name}.json").write_text(json.dumps(found, indent=1, default=str))
    return found


def window(frame: pd.DataFrame) -> str:
    return f"{frame['created_at'].min():%Y-%m-%d} to {frame['created_at'].max():%Y-%m-%d}"


say(
    f"**This is a {'fast run: its figures only show that the code works' if FAST_RUN else 'full run'}.** "
    f"Results are stored in `{WORK.as_posix()}` and the model is saved to `{MODEL_DIR.as_posix()}`."
)

# %% [markdown]
# ## Summary
#
# **Question.** Can the tone of a financial headline be read by a model more accurately
# than by the one the app uses today, without overfitting, and which of two base models
# does it best?
#
# This cell reads what the cells below stored the last time they ran. The first time
# through it says "not available"; run it again at the end.

# %%
compared, final_stored, test_stored = stored("comparison"), stored("final"), stored("test")
if FAST_RUN:
    say("- **Fast run.** Every figure below comes from 200 headlines and one pass. Do not read them as results.")
say(
    f"- **Model comparison.** not available: {(WORK / 'comparison.json').as_posix()}"
    if compared is None
    else f"- **Model comparison** (section 10). Winner: **{compared['winner']}**. {compared['why']}"
)
say(
    f"- **Validation.** not available: {(WORK / 'final.json').as_posix()}"
    if final_stored is None
    else f"- **Validation** (sections 12 and 13). The saved model ({final_stored['model']}, seed "
    f"{final_stored['seed']}) has accuracy {final_stored['validation']['accuracy']:.1%} and loss "
    f"{final_stored['validation']['loss']:.3f} on {final_stored['headlines']} validation headlines "
    f"({final_stored['window']}). Validation figures lean optimistic (section 10)."
)
say(
    f"- **Test.** not available: {(WORK / 'test.json').as_posix()}. The test has not been run."
    if test_stored is None
    else f"- **Test** (section 15). On {test_stored['headlines']} unseen headlines accuracy is "
    f"{test_stored['scores']['new']['accuracy']:.1%} (95% range "
    f"{test_stored['scores']['new']['from']:.1%} to {test_stored['scores']['new']['to']:.1%}). "
    + " ".join(
        f"{name}: **{'not available' if passed is None else 'pass' if passed else 'fail'}**."
        for name, passed in test_stored["bars"].items()
    )
)

# %% [markdown]
# ## 2. Problem and metric
#
# *What is predicted, and how is a good prediction measured?*
#
# The input is one piece of text about one asset. The output is a probability for each
# of three labels; the label with the highest probability is the answer. Terms used
# throughout, each with one meaning:
#
# | Term | Meaning |
# |---|---|
# | accuracy | Share of headlines whose answer matches the label |
# | loss | Log loss (cross-entropy): the average of minus the log of the probability given to the true label. A confident wrong answer costs more than an unsure one |
# | macro F1 | F1 worked out per label and averaged, so a rare label counts as much as a common one |
# | pass | One run through all training headlines (an "epoch") |
# | seed | The number that fixes the random order of training. The same recipe with another seed gives a slightly different model |
# | seed spread | How far two seeds of the same recipe on the same data differ. A lead smaller than this is **no measurable difference** |
# | block | A stretch of headlines, later in time than everything the model was trained on, used to validate |
# | validation | Headlines used to make choices. The test set is used for none |
# | overfitting | The model has memorised its training headlines: training loss keeps falling while validation loss rises |
#
# Accuracy is what a reader experiences. Loss is used to make choices because it uses
# the whole probability, not only which label came first, so it moves less from one run
# to the next.


# %%
def log_loss(truth: list[str], probabilities: np.ndarray) -> float:
    """Average of -log(probability given to the true label). Columns follow LABELS."""
    column = [LABELS.index(label) for label in truth]
    given = np.asarray(probabilities, dtype=float)[np.arange(len(truth)), column]
    return float(-np.log(np.clip(given, 1e-12, 1.0)).mean())


def answers(probabilities: np.ndarray) -> list[str]:
    return [LABELS[i] for i in probabilities.argmax(axis=1)]


def per_label(truth: list[str], said: list[str]) -> pd.DataFrame:
    """Precision, recall and F1 for each label."""
    rows = {}
    for label in LABELS:
        hit = sum(t == label and s == label for t, s in zip(truth, said))
        given, real = sum(s == label for s in said), sum(t == label for t in truth)
        precision, recall = (hit / given if given else 0.0), (hit / real if real else 0.0)
        f1 = 2 * precision * recall / (precision + recall) if hit else 0.0
        rows[label] = {"headlines": real, "precision": precision, "recall": recall, "f1": f1}
    return pd.DataFrame(rows).T


def measure(truth: list[str], probabilities: np.ndarray) -> dict[str, float]:
    said = answers(probabilities)
    table = per_label(truth, said)
    return {
        "loss": log_loss(truth, probabilities),
        "accuracy": float(np.mean([t == s for t, s in zip(truth, said)])),
        "macro_f1": float(table.loc[table["headlines"] > 0, "f1"].mean()),
    }


# %%
def wilson(share: float, n: int) -> tuple[float, float]:
    """The 95% range a share measured on n items could plausibly be in (Wilson interval)."""
    z = 1.959964
    centre = (share + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def mcnemar(truth: list[str], first: list[str], second: list[str]) -> dict:
    """Are two models different? Uses only the headlines where one is right and one wrong.

    Exact two-sided test: if the two were equally good, each such headline would be a
    coin toss between them.
    """
    only_first = sum(a == t and b != t for t, a, b in zip(truth, first, second))
    only_second = sum(a != t and b == t for t, a, b in zip(truth, first, second))
    n, fewer = only_first + only_second, min(only_first, only_second)
    p = min(1.0, 2.0 * sum(math.comb(n, k) for k in range(fewer + 1)) / 2**n) if n else 1.0
    return {"only_first_right": only_first, "only_second_right": only_second, "p_value": p}


# %%
# The two pass marks of decision 101, read on the test set.
P_BELOW, ACCURACY_GAP, LOSS_GAP = 0.05, 0.05, 0.10
KNOWS_NOTHING = math.log(len(LABELS))

example = np.array([[0.90, 0.05, 0.05], [0.40, 0.35, 0.25], [0.05, 0.90, 0.05]])
display(
    pd.DataFrame(
        {
            "probabilities (positive, negative, neutral)": [str(row.tolist()) for row in example],
            "answer": answers(example),
            "loss if the label is positive": [log_loss(["positive"], row[None, :]) for row in example],
        },
        index=["sure and right", "unsure and right", "sure and wrong"],
    )
)
caption("Three made-up predictions for a headline whose label is positive.")
say(
    f"**Found.** There are {len(LABELS)} labels. A model that gives each the same probability has a "
    f"loss of {KNOWS_NOTHING:.3f} (the log of {len(LABELS)}): the mark of a model that knows nothing. "
    "The trained model is judged on the test set against two bars: (1) *better than the model in "
    f"use*: higher accuracy, with McNemar's test giving p below {P_BELOW}; (2) *not overfitted*: "
    f"test accuracy no more than {ACCURACY_GAP * 100:.0f} points under validation accuracy, and test "
    f"loss no more than {LOSS_GAP:.2f} above validation loss."
)

# %% [markdown]
# ## 3. Data loading
#
# *What data is there, and what is each column?*
#
# One Parquet file holds every labelled headline. It is written by
# `backend/scripts/tone_export.py` and holds the news provider's text, so it is not in
# the public repository.
#
# | Column | Meaning |
# |---|---|
# | `article_id` | The article's number at the provider |
# | `symbol`, `market` | The asset the article is filed under, as a ticker and as a plain name |
# | `created_at` | When it was published (UTC) |
# | `headline`, `summary` | The text. The summary may be empty |
# | `label_1`, `label_2`, ... | One column per labelling pass. A pass that did not cover the headline is empty |
# | `label` | The label used for scoring |
# | `labelled_by`, `rule` | Who wrote the labels and under which written rule |
# | `part` | `labelled` (training and validation) or `test` |

# %%
if not DATA_PATH.is_file():
    raise FileNotFoundError(f"not available: {DATA_PATH.as_posix()} (run backend/scripts/tone_export.py, or copy the file here)")
everything = pd.read_parquet(DATA_PATH).sort_values(["created_at", "article_id"]).reset_index(drop=True)
everything["summary"] = everything["summary"].fillna("")
PASSES = sorted(column for column in everything.columns if column.startswith("label_"))
labelled = everything[everything["part"] == "labelled"].reset_index(drop=True)

# The test set's labels are put aside here and used by one cell only (section 15).
# Everywhere else `test` has no label column, so nothing can read them by accident.
_test_part = everything[everything["part"] == "test"].reset_index(drop=True)
_test_labels = _test_part["label"].tolist()
test = _test_part.drop(columns=[*PASSES, "label"])
TEST_FROM = test["created_at"].min().normalize()

display(
    pd.DataFrame(
        {
            "headlines": [len(labelled), len(test)],
            "period": [window(labelled), window(test)],
            "labelling passes": [", ".join(f"{p}: {int(labelled[p].notna().sum()):,}" for p in PASSES), "not read"],
            "labelled by": [", ".join(sorted(labelled["labelled_by"].unique())), ", ".join(sorted(test["labelled_by"].unique()))],
        },
        index=["training and validation", "test"],
    )
)
caption(f"The two parts of {DATA_PATH.name}: {len(everything):,} rows, columns {list(everything.columns)}.")
say(
    f"**Found.** {len(labelled):,} headlines to train and validate on ({window(labelled)}) and "
    f"{len(test):,} to test on ({window(test)}). The test period starts on {TEST_FROM:%Y-%m-%d}; "
    "its labels are not read before section 15."
)

# %% [markdown]
# ## 4. Data quality
#
# *Is anything missing or repeated, and how far can the labels be trusted?*

# %%
checks = {
    "rows with an empty headline": int((everything["headline"].str.strip() == "").sum()),
    "rows with no summary": int((everything["summary"].str.strip() == "").sum()),
    "rows with no market": int(everything["market"].isna().sum()),
    "rows with no date": int(everything["created_at"].isna().sum()),
    "article numbers appearing twice": int(everything["article_id"].duplicated().sum()),
    "training rows with a label outside the three": int((~labelled["label"].isin(LABELS)).sum()),
}
display(pd.Series(checks, name="count").to_frame())
caption(f"Basic checks on all {len(everything):,} rows.")

# %% [markdown]
# **Near-copies.** Many headlines are templates that differ only in a number. Each is
# reduced to a key, and a key may appear only once across all the data. A near-copy in
# both training and test would let the model be scored on something it has seen.

# %% app-parity
import re

_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")


def headline_key(headline: str) -> str:
    """A headline with case, punctuation and every number removed."""
    return _NOT_WORD.sub(" ", _NUMBER.sub("#", headline.lower())).strip()


# %%
pair = ["Example Whale Moves 2,901 Coins Off Exchange", "example whale moves 1,112 coins off exchange!"]
display(pd.DataFrame({"headline (made up)": pair, "key": [headline_key(h) for h in pair]}))
keys = everything["headline"].map(headline_key)
near_copies = len(everything) - keys.nunique()
say(f"All {len(everything):,} headlines have {keys.nunique():,} distinct keys: **{near_copies} near-copies remain**.")

# %% [markdown]
# **The labelling rule** (decision 101). Every label was written by an AI model
# (Claude), not a person, from the headline alone:
#
# > - *positive*: it reports or expects something good for prices or holders (gains, a
# >   beat, inflows, approval, adoption, a bullish call, easing of a threat);
# > - *negative*: the opposite (falls, a miss, outflows, a ban, a hack, a lawsuit,
# >   conflict, a central banker leaning towards higher rates, a bearish call);
# > - *neutral*: no clear direction (a plain fact or scheduled figure without a stated
# >   surprise, procedure, a mixed wrap with one thing up and another down, a question,
# >   or something off the subject);
# > - when the headline names the asset it is filed under, what it says about that asset
# >   decides; otherwise its overall tone does.
#
# **Inter-pass agreement.** Some headlines were labelled more than once, mixed among
# new ones so the labeller could not tell them apart. Cohen's kappa is agreement beyond
# what two labellers would reach by chance: 1 is full agreement, 0 is chance.


# %%
def cohen_kappa(first: list[str], second: list[str]) -> float:
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    by_chance = sum((first.count(label) / n) * (second.count(label) / n) for label in LABELS)
    return (observed - by_chance) / (1 - by_chance)


def agreement_table(frame: pd.DataFrame, one: str, two: str) -> pd.DataFrame:
    """Agreement between two labelling passes, per market and over all, on rows both cover."""
    both = frame.dropna(subset=[one, two])
    return pd.DataFrame(
        {
            name: {
                "headlines": len(part),
                "agreement": (part[one] == part[two]).mean(),
                "kappa": cohen_kappa(part[one].tolist(), part[two].tolist()),
            }
            for name, part in [*both.groupby("market"), ("all", both)]
        }
    ).T


pass_pairs = [pair for pair in itertools.combinations(PASSES, 2) if len(labelled.dropna(subset=list(pair)))]
if not pass_pairs:
    raise ValueError("No headline was labelled twice: agreement cannot be measured")
for one, two in pass_pairs:
    twice = labelled.dropna(subset=[one, two])
    agreement = agreement_table(labelled, one, two)
    grid = pd.crosstab(pd.Categorical(twice[one], LABELS), pd.Categorical(twice[two], LABELS), dropna=False)
    display(agreement)
    display(grid.rename_axis(index=one, columns=two))
    caption(f"{one} against {two} on {len(twice)} headlines ({window(twice)}): per market, then as a grid.")

# %%
# The figures below use the last pair of passes shown above.
share = float(agreement.loc["all", "agreement"])
low, high = share, math.sqrt(share)
differ = int(len(twice) - np.trace(grid.to_numpy()))
with_neutral = differ - int(grid.loc["positive", "negative"] + grid.loc["negative", "positive"])
weakest = agreement.drop(index="all")["agreement"].idxmin()
say(
    f"**Found.** Inter-pass agreement is {share:.1%} (kappa {agreement.loc['all', 'kappa']:.2f}) on "
    f"{len(twice)} headlines; the weakest market is {weakest} ({agreement.loc[weakest, 'agreement']:.1%} "
    f"of {int(agreement.loc[weakest, 'headlines'])}). Of the {differ} disagreements, {with_neutral} "
    "are between neutral and a tone."
)
say(
    f"**What this bounds.** The best accuracy any model can reach on these labels lies between "
    f"**{low:.1%}** and **{high:.1%}**. *Lower end, the agreement itself*: if every disagreement is "
    "a headline with no single right label, nothing can match the label on it more often than the "
    f"two passes match each other. *Upper end, its square root (√{share:.3f})*: if every headline "
    "has one right label and each pass misses it independently with the same chance, two passes "
    "agree when both are right, so agreement = accuracy × accuracy. Which case holds is not known "
    "from two passes."
)


# %%
def shares(frame: pd.DataFrame) -> np.ndarray:
    """What a model is trained towards: per headline, the share of passes that gave each label.

    One pass gives its label everything; two that differ give half each; two of three give 0.67.
    """
    out = np.zeros((len(frame), len(LABELS)))
    for column in PASSES:
        for row, label in enumerate(frame[column]):
            if isinstance(label, str):
                out[row, LABELS.index(label)] += 1.0
    return out / out.sum(axis=1, keepdims=True)


made_up_passes = pd.DataFrame({column: ["positive", "positive"] for column in PASSES})
made_up_passes.loc[0, PASSES[-1]] = "neutral"
display(pd.concat([made_up_passes, pd.DataFrame(shares(made_up_passes), columns=[f"target: {label}" for label in LABELS])], axis=1))
caption("Two made-up headlines: one the passes disagree on, one they agree on, and the target each gives.")

# %% [markdown]
# ## 5. Cleaning
#
# *What is removed from the text, and what is left alone?*
#
# Cleaning removes what carries no tone (exchange tags, revision tags, the source's
# name, HTML entities, extra spaces) and leaves the words as they are, since case and
# punctuation carry tone in a headline. The same function must be applied to any text
# given to the saved model.

# %% app-parity
import html

_EXCHANGE_TAG = re.compile(r"\s*\((?:NYSE|NASDAQ|AMEX|ARCA|OTC|CRYPTO|BATS|TSX)\b[^)]*\)?", re.I)
_REVISION_TAG = re.compile(r"\s*\((?:UPDATED|CORRECTED)\)", re.I)
_SOURCE_TAIL = re.compile(r"(?<=['\"’”])\s*-\s*[A-Z@][^-]{1,40}$")
_SENTENCE_END = re.compile(r"[.!?][\"'’”)]*(?=\s|$)")


def clean_headline(headline: str) -> str:
    """Even out white space, read HTML entities, drop revision, exchange and source tags."""
    text = " ".join(html.unescape(headline).split())
    for pattern in (_REVISION_TAG, _EXCHANGE_TAG, _SOURCE_TAIL):
        text = pattern.sub("", text)
    return " ".join(text.split())


# %%
made_up = [
    "Gold &amp; Silver   Rise As Dollar Slips (UPDATED)",
    "Analyst Praises Example Corp (NYSE:EXMP) After Earnings",
    "'Example Bank Cuts Its Forecast' - Example Wire",
]
display(pd.DataFrame({"as stored (made up)": made_up, "as cleaned": [clean_headline(h) for h in made_up]}))
evened = labelled["headline"].map(lambda h: " ".join(h.split()))
cleaned = labelled["headline"].map(clean_headline)
emptied = int((cleaned == "").sum())
say(
    f"**Found.** Cleaning changes more than white space in {(cleaned != evened).mean():.1%} of the "
    f"{len(labelled):,} training and validation headlines, and leaves {emptied} of them empty. "
    "No row is dropped."
)

# %% [markdown]
# ## 6. Exploration
#
# *What do the headlines look like by label, market, time and length?*

# %%
by_class = pd.crosstab(labelled["market"], labelled["label"])[LABELS]
ax = by_class.plot.barh(stacked=True, color=[TONE_COLOUR[label] for label in LABELS], figsize=(8, 2.2))
ax.set(title="Labels by market", ylabel="")
ax.legend(ncol=3, loc="lower right")
plt.show()
display(by_class.assign(all=by_class.sum(axis=1), share_neutral=by_class["neutral"] / by_class.sum(axis=1)))
caption(f"Training and validation headlines by market and label: {len(labelled):,}, {window(labelled)}.")

# %%
year = labelled["created_at"].dt.year.rename("year")
fig, axes = plt.subplots(1, 2, figsize=(12, 2.8))
pd.crosstab(year, labelled["market"]).plot.bar(stacked=True, ax=axes[0], color=[ACCENT, "#c9952b", INK])
axes[0].set(title="Headlines a year, by market", xlabel="")
mix = pd.crosstab(year, labelled["label"], normalize="index")[LABELS]
mix.plot.bar(stacked=True, ax=axes[1], color=[TONE_COLOUR[label] for label in LABELS], legend=False)
axes[1].set(title="Label mix a year (share)", xlabel="")
plt.show()
caption(f"The same {len(labelled):,} headlines by year published.")

# %%
words = labelled["headline"].str.split().str.len()
has_summary = labelled["summary"].str.len() > 0
markets = list(by_class.index)
fig, axes = plt.subplots(1, 2, figsize=(12, 2.8))
for label in LABELS:
    axes[0].hist(words[labelled["label"] == label], bins=range(0, 80, 3), histtype="step",
                 color=TONE_COLOUR[label], label=label, density=True)  # fmt: skip
axes[0].set(title="Headline length in words, by label", xlabel="words", yticks=[])
axes[0].legend()
axes[1].boxplot([words[labelled["market"] == market] for market in markets], vert=False)
axes[1].set_yticks(range(1, len(markets) + 1), markets)
axes[1].set(title="Headline length in words, by market", xlabel="words")
plt.show()
display(
    pd.DataFrame(
        {
            "median words": words.groupby(labelled["label"]).median(),
            "share over 40 words": (words > 40).groupby(labelled["label"]).mean(),
            "share with a summary": has_summary.groupby(labelled["label"]).mean(),
        }
    )
)
caption(f"Headline length and how often a summary is stored, by label: {len(labelled):,} headlines.")


# %%
def telling_words(frame: pd.DataFrame, top: int = 12) -> pd.DataFrame:
    """Words that appear much more under one label than under the other two.

    For each word: the share of that label's headlines containing it, divided by the
    share of all other headlines containing it. Words in fewer than 15 headlines are left out.
    """
    tokens = frame["headline"].str.lower().str.findall(r"[a-z']{3,}").map(set)
    counts: dict[str, dict[str, int]] = {label: {} for label in LABELS}
    for words_in, label in zip(tokens, frame["label"]):
        for word in words_in:
            counts[label][word] = counts[label].get(word, 0) + 1
    sizes = frame["label"].value_counts()
    out = {}
    for label in LABELS:
        rows = []
        for word, n in counts[label].items():
            others = sum(counts[other].get(word, 0) for other in LABELS if other != label)
            if n + others >= 15:
                ratio = (n / sizes[label]) / ((others + 1) / (len(frame) - sizes[label]))
                rows.append((ratio, f"{word} ({n})"))
        out[label] = [word for _, word in sorted(rows, reverse=True)[:top]]
    return pd.DataFrame(out)


display(telling_words(labelled))
caption(
    "Words most tied to each label (in brackets: headlines with that label containing the word). "
    f"Single words only; no headline is shown. {len(labelled):,} headlines, {window(labelled)}."
)

# %%
month = test["created_at"].dt.strftime("%Y-%m").rename("month")
display(pd.crosstab(month, test["market"]).T)
caption(f"The test set by market and month: {len(test):,} headlines, {window(test)}. Labels not read.")
smallest = test["market"].value_counts().idxmin()
say(
    f"**Found.** Neutral is the largest label ({(labelled['label'] == 'neutral').mean():.0%}) and the "
    f"smallest is {labelled['label'].value_counts().idxmin()} "
    f"({labelled['label'].value_counts(normalize=True).min():.0%}), so the classes are not badly "
    "unbalanced and no resampling is used. The mix of markets and labels shifts from year to year, "
    f"which is why the split below is by time. {smallest} has {int((test['market'] == smallest).sum())} "
    "test headlines, the fewest."
)

# %% [markdown]
# ## 7. Time-ordered split and leakage checks
#
# *How is the data divided so that no score is flattered by something the model has seen?*
#
# The split is **by time, never at random**: a model is always scored on headlines
# later than all it was trained on, which is how it is used. Models are compared on
# **walk-forward blocks**: the last stretches of headlines before the test period, each
# scored by a model trained only on what came before it. The winner is then trained on
# the last block's training part. The test set comes after all of it.

# %%
rows_used = labelled if ROWS is None else labelled.tail(ROWS).reset_index(drop=True)


def walk_forward(frame: pd.DataFrame) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """(train on, validate on) for each block; `frame` is in time order."""
    starts = [len(frame) - BLOCK * (BLOCKS - k) for k in range(BLOCKS)]
    return [(frame.iloc[:start], frame.iloc[start : start + BLOCK]) for start in starts]


blocks = walk_forward(rows_used)
train, validation = blocks[-1]  # what the winner is trained and validated on
fig, ax = plt.subplots(figsize=(10, 2.3))
for row, (block_train, block_validation) in enumerate(blocks):
    for part, shade in ((block_train, MUTED), (block_validation, ACCENT)):
        start = part["created_at"].min()
        ax.barh(row, (part["created_at"].max() - start).days, left=start.tz_localize(None), color=shade, height=0.6)
ax.barh(len(blocks), (test["created_at"].max() - test["created_at"].min()).days,
        left=test["created_at"].min().tz_localize(None), color=INK, height=0.6)  # fmt: skip
ax.set_yticks(range(len(blocks) + 1), [f"block {i + 1}" for i in range(len(blocks))] + ["test"])
ax.invert_yaxis()
ax.set(title="Grey: trained on. Blue: validated on. Black: the test set")
plt.show()
display(
    pd.DataFrame(
        {
            f"block {i + 1}": {
                "trained on": len(block_train),
                "training": window(block_train),
                "validated on": len(block_validation),
                "validation": window(block_validation),
                **block_validation["label"].value_counts(normalize=True).reindex(LABELS).fillna(0.0).round(2).to_dict(),
            }
            for i, (block_train, block_validation) in enumerate(blocks)
        }
    ).T
)
caption(
    f"{BLOCKS} walk-forward blocks of {BLOCK} validation headlines out of {len(rows_used):,} used, and the "
    f"test set of {len(test)} ({window(test)}). The last columns are each validation part's label mix."
)

# %%
test_keys, train_keys = set(test["headline"].map(headline_key)), set(rows_used["headline"].map(headline_key))
guards = {
    "articles in both training and test": len(set(rows_used["article_id"]) & set(test["article_id"])),
    "near-copies in both training and test": len(train_keys & test_keys),
    "near-copies appearing twice in training": int(rows_used["headline"].map(headline_key).duplicated().sum()),
    "training headlines dated inside the test period": int((rows_used["created_at"] >= TEST_FROM).sum()),
    "rows out of time order in training": int((rows_used["created_at"].diff().dt.total_seconds() < 0).sum()),
    "blocks whose training part reaches past their validation part": sum(
        block_train["created_at"].max() > block_validation["created_at"].min() for block_train, block_validation in blocks
    ),
    "blocks sharing an article between training and validation": sum(
        len(set(block_train["article_id"]) & set(block_validation["article_id"])) > 0 for block_train, block_validation in blocks
    ),
}
display(pd.Series(guards, name="count").to_frame())
say(
    f"**Found.** {sum(v == 0 for v in guards.values())} of {len(guards)} leakage checks count zero. "
    f"The winner is trained on {len(train):,} headlines ({window(train)}) and validated on "
    f"{len(validation)} ({window(validation)}); the test period starts on {TEST_FROM:%Y-%m-%d}."
)
if any(guards.values()):
    raise ValueError("A leakage check is not zero: stop here")

# %% [markdown]
# ## 8. Tokenisation
#
# *What text does a model read, and does it fit?*
#
# A language model reads text directly, so the "features" are which text it is given.
# The text is the asset's plain name, the cleaned headline, and the summary's whole
# sentences (stored summaries are cut at a fixed length, often mid-sentence). **This
# exact preparation is part of the model**: text given to the saved model must be
# built the same way, and section 16 saves the settings beside the model's files.

# %% app-parity
TEXTS = {
    "headline": {"with_asset": False, "with_summary": False},
    "asset + headline": {"with_asset": True, "with_summary": False},
    "headline + summary": {"with_asset": False, "with_summary": True},
    "asset + headline + summary": {"with_asset": True, "with_summary": True},
}


def whole_sentences(summary: str) -> str:
    """A summary up to its last complete sentence, or nothing if it has none."""
    text = clean_headline(summary)
    ends = [found.end() for found in _SENTENCE_END.finditer(text)]
    return text[: ends[-1]] if ends else ""


def model_text(headline: str, summary: str = "", market: str = "", *, with_asset: bool = False, with_summary: bool = False) -> str:
    """The text a tone model reads, built from the parts chosen."""
    text = clean_headline(headline)
    if with_summary:
        extra = whole_sentences(summary)
        if extra and headline_key(extra) != headline_key(text):
            text = f"{text if text.endswith(('.', '!', '?')) else text + '.'} {extra}"
    return f"{market}: {text}" if with_asset and market else text


# %%
TEXT = "asset + headline + summary"  # lowest validation loss in round 4; kept by the user (decisions 102, 104)


def texts(frame: pd.DataFrame, option: str = TEXT) -> list[str]:
    return [
        model_text(str(h), str(s or ""), str(m), **TEXTS[option])
        for h, s, m in zip(frame["headline"], frame["summary"], frame["market"])
    ]


sample = ("Gold Rises", "Bullion gained on the day. Analysts said the move could", "Gold")
display(pd.Series({name: model_text(*sample, **parts) for name, parts in TEXTS.items()}, name="what the model reads").to_frame())
caption(f"The {len(TEXTS)} ways to build the input on one made-up headline and summary. Used here: {TEXT}.")

# %%
ROBERTA = "cardiffnlp/twitter-roberta-base-sentiment-latest"
DEBERTA = "microsoft/deberta-v3-base"
CANDIDATES = {"RoBERTa (social media)": ROBERTA, "DeBERTa-v3": DEBERTA}
tokenizers = {name: AutoTokenizer.from_pretrained(model) for name, model in CANDIDATES.items()}
made_up_text = model_text("Example Corp Shares Slide After Profit Warning", "", "US stocks", **TEXTS["asset + headline"])
display(
    pd.DataFrame(
        {
            name: {
                "tokenizer": type(tokenizer).__name__,
                "vocabulary": tokenizer.vocab_size,
                "tokens for the made-up text": len(tokenizer(made_up_text)["input_ids"]),
                "first tokens": " | ".join(tokenizer.tokenize(made_up_text)[:8]),
            }
            for name, tokenizer in tokenizers.items()
        }
    ).T
)
caption(f"Both tokenizers load and split one made-up text: “{made_up_text}”.")

# %%
lengths = pd.DataFrame({name: [len(ids) for ids in tokenizer(texts(rows_used))["input_ids"]] for name, tokenizer in tokenizers.items()})
ax = lengths.plot.box(vert=False, figsize=(9, 1.8), color=INK)
ax.axvline(MAX_TOKENS, color=BAD, ls="--", lw=0.9)
ax.set(title=f"Length in tokens of each input (red: the {MAX_TOKENS}-token limit)", xlabel="tokens")
plt.show()
display(lengths.describe().loc[["50%", "max"]].T.assign(cut_off=(lengths > MAX_TOKENS).mean()))
caption(f"Token counts for the {len(rows_used):,} training and validation inputs; `cut_off` is the share over the limit.")
say(
    f"**Found.** Both tokenizers load. The longest input is {int(lengths.max().max())} tokens against a "
    f"limit of {MAX_TOKENS}, and at most {(lengths > MAX_TOKENS).mean().max():.1%} of inputs are cut."
)

# %% [markdown]
# ## 9. Baselines
#
# *What does a model have to beat?*
#
# Answers that need no training here: always the commonest label; the social-media
# RoBERTa exactly as downloaded (it already has a tone head); and the model in the app
# today, `finbert-radar-1` (FinBERT trained further on an earlier, smaller set of these
# headlines), if its files are on this machine. DeBERTa-v3 as downloaded has no tone
# head, so it cannot be scored before training.


# %%
SAME_LABEL = {"bearish": "negative", "bullish": "positive"}


def free() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def own_labels(config) -> list[str]:
    """A model's own label for each output, in our words."""
    return [SAME_LABEL.get(config.id2label[i].lower(), config.id2label[i].lower()) for i in sorted(config.id2label)]


def predict(model_dir: Path | str, inputs: list[str]) -> np.ndarray:
    """Probabilities for each text, columns in LABELS order, from a saved or downloaded model."""
    where = model_dir.as_posix() if isinstance(model_dir, Path) else model_dir
    tokenizer = AutoTokenizer.from_pretrained(where)
    model = AutoModelForSequenceClassification.from_pretrained(where).float().to(DEVICE)
    model.eval()
    own = own_labels(model.config)
    out = []
    with torch.no_grad():
        for start in range(0, len(inputs), 64):
            batch = tokenizer(inputs[start : start + 64], padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            logits = model(**{k: v.to(DEVICE) for k, v in batch.items()}).logits
            out.append(torch.softmax(logits, dim=-1)[:, [own.index(label) for label in LABELS]].cpu().numpy())
    del model
    free()
    return np.concatenate(out)


def app_text(frame: pd.DataFrame) -> list[str]:
    """The text the app's model is given today: the headline, then the summary if it adds anything."""
    out = []
    for headline, summary in zip(frame["headline"], frame["summary"]):
        headline, summary = " ".join(str(headline).split()), " ".join(str(summary or "").split())
        if not summary or summary == headline:
            out.append(headline[:2000])
        else:
            out.append(f"{headline if headline.endswith(('.', '!', '?')) else headline + '.'} {summary}"[:2000])
    return out


# %%
def baselines() -> dict:
    """Each baseline on each block's validation part; stored, so it is scored once."""
    found = stored("baselines")
    if found is None:
        found = {}
        always = []
        for block_train, block_validation in blocks:
            mix = block_train["label"].value_counts(normalize=True).reindex(LABELS).fillna(0.0)
            truth = block_validation["label"].tolist()
            always.append({"loss": log_loss(truth, np.tile(mix.to_numpy(), (len(truth), 1))),
                           "accuracy": float(np.mean([label == mix.idxmax() for label in truth]))})  # fmt: skip
        found["always the commonest label"] = always
        found["RoBERTa (social media), as downloaded"] = [
            measure(v["label"].tolist(), predict(ROBERTA, texts(v))) for _, v in blocks
        ]
        if IN_USE.is_dir():
            found["finbert-radar-1 (in the app)"] = [measure(v["label"].tolist(), predict(IN_USE, app_text(v))) for _, v in blocks]
        store("baselines", found)
    return found


def baseline_rows() -> pd.DataFrame:
    rows = {f"baseline: {name}": pd.DataFrame(each)[["loss", "accuracy"]].mean() for name, each in baselines().items()}
    return pd.DataFrame(rows).T.rename(columns={"loss": "validation loss"})


baseline_table = baseline_rows()
display(baseline_table)
caption(
    f"Baselines: mean over the {BLOCKS} validation blocks of {BLOCK} headlines "
    f"({blocks[0][1]['created_at'].min():%Y-%m-%d} to {blocks[-1][1]['created_at'].max():%Y-%m-%d})."
)
if not IN_USE.is_dir():
    say(f"The model in the app: not available: {IN_USE.as_posix()}")
to_beat = baseline_table["accuracy"].idxmax()
say(
    f"**Found.** The best baseline by accuracy is *{to_beat.removeprefix('baseline: ')}* at "
    f"{baseline_table.loc[to_beat, 'accuracy']:.1%} (loss {baseline_table.loc[to_beat, 'validation loss']:.3f}); "
    f"always answering the commonest label gives "
    f"{baseline_table.loc['baseline: always the commonest label', 'accuracy']:.1%}."
)

# %% [markdown]
# ## 10. Model comparison
#
# *Which of the two base models reads these headlines better?*
#
# | Candidate | First trained on |
# |---|---|
# | RoBERTa (social media) | Social-media posts, then the tone of posts |
# | DeBERTa-v3 | General text; a newer design, with no tone training |
#
# Both get the same headlines, the same input text and the same settings, on every
# block with every comparison seed.
#
# **The rule that picks the winner, written before any run (decision 103).** DeBERTa-v3
# wins only if, on the mean across blocks and seeds, it has **both** a lower validation
# loss **and** a higher validation accuracy, **and** its lead in loss is larger than the
# seed spread. Otherwise RoBERTa wins, because it is the smaller model.
#
# **Validation figures lean optimistic.** In every run the validation headlines do two
# jobs: they pick which pass is kept, and they score the model. A score picked as the
# best of several passes is better than the same model would get on new headlines. The
# lean is the same for both candidates, so it does not favour one, but the level of
# every validation figure in this notebook is flattered.
#
# ### The training function
#
# "Fine-tuning" takes a language model already trained on a great deal of text and
# trains it a little further on our headlines:
#
# 1. show the model the training headlines in batches, in a random order fixed by the seed;
# 2. after each pass, measure loss on the validation headlines;
# 3. **keep the weights from the pass with the lowest validation loss**, and stop once
#    it has not improved for `early_stopping_patience` passes. This is the guard
#    against overfitting.


# %%
def new_head(model_name: str) -> dict:
    """Arguments that give a base model our three labels, when its own are not usable as they are."""
    own = AutoConfig.from_pretrained(model_name).id2label
    plain = [own[i].lower() for i in sorted(own)]
    names = [SAME_LABEL.get(name, name) for name in plain]
    if sorted(names) != sorted(LABELS):
        names = LABELS  # no usable tone head: a new one is trained
    elif names == plain:
        return {}
    return {"num_labels": len(names), "id2label": dict(enumerate(names)),
            "label2id": {name: i for i, name in enumerate(names)}, "ignore_mismatched_sizes": True}  # fmt: skip


def fine_tune(
    train_texts: list[str],
    targets: np.ndarray,
    validation_texts: list[str],
    validation_labels: list[str],
    out_dir: Path,
    *,
    model_name: str,
    seed: int,
    epochs: int,
    early_stopping_patience: int,
    learning_rate: float,
    weight_decay: float,
    batch_size: int,
    warmup_share: float,
) -> dict:
    """Train on the training texts; save the pass with the lowest validation loss to `out_dir`.

    `targets` has one row per training text: a share for each label, in LABELS order.
    Returns the loss and accuracy after every pass, and which pass was kept.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    # .float(): a model stored in half precision cannot be trained (its loss turns into
    # "not a number" after one step). For a model already in full precision it changes nothing.
    model = AutoModelForSequenceClassification.from_pretrained(model_name, **new_head(model_name)).float().to(DEVICE)
    order = own_labels(model.config)

    def encode(batch: list[str]) -> dict:
        return dict(tokenizer(batch, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt"))

    wanted = torch.tensor(np.asarray(targets, dtype=float)[:, [LABELS.index(n) for n in order]], dtype=torch.float)
    loss_fn = torch.nn.CrossEntropyLoss()
    optimiser = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    steps = epochs * math.ceil(len(train_texts) / batch_size)
    schedule = get_linear_schedule_with_warmup(optimiser, int(warmup_share * steps), steps)
    rng = np.random.default_rng(seed)
    truth = torch.tensor([order.index(label) for label in validation_labels])
    history, best, waited = [], math.inf, 0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffled, total = rng.permutation(len(train_texts)), 0.0
        for start in range(0, len(shuffled), batch_size):
            rows = shuffled[start : start + batch_size]
            batch = {k: v.to(DEVICE) for k, v in encode([train_texts[i] for i in rows]).items()}
            loss = loss_fn(model(**batch).logits, wanted[rows].to(DEVICE))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            schedule.step()
            optimiser.zero_grad()
            total += float(loss) * len(rows)
        model.eval()
        logits = []
        with torch.no_grad():
            for start in range(0, len(validation_texts), 64):
                batch = {k: v.to(DEVICE) for k, v in encode(validation_texts[start : start + 64]).items()}
                logits.append(model(**batch).logits.cpu())
        logits = torch.cat(logits)
        validation_loss = float(loss_fn(logits, truth))
        if not math.isfinite(validation_loss):
            raise ValueError(f"{model_name}: the loss is not a number after pass {epoch}")
        history.append(
            {
                "epoch": epoch,
                "train_loss": total / len(train_texts),
                "validation_loss": validation_loss,
                "validation_accuracy": float((logits.argmax(dim=-1) == truth).float().mean()),
            }
        )
        if validation_loss < best:
            best, waited = validation_loss, 0
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
        else:
            waited += 1
            if waited >= early_stopping_patience:
                break
    del model, optimiser
    free()
    return {"epochs": history, "best_epoch": min(history, key=lambda e: e["validation_loss"])["epoch"]}


# %% [markdown]
# ### One stored run
#
# `run` trains one model and stores what it said about the validation headlines, under
# a name made from everything that went in (which headlines, their targets, the text,
# the model, the settings, the seed). Asking for the same run again reads the stored
# answer, so a stopped notebook picks up where it left off. The model's files go to a
# temporary folder that is deleted when the run ends, also when it fails; they are
# copied out only when `keep_model` says where.


# %%
def run_name(*parts) -> str:
    written = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha1(written, usedforsecurity=False).hexdigest()[:10]


def run(block_train: pd.DataFrame, block_validation: pd.DataFrame, *, model: str, seed: int, keep_model: Path | None = None) -> dict:
    """Train one model on one block, or read it back."""
    targets = shares(block_train)
    name = run_name(list(block_train["article_id"]), targets.round(3).tolist(), list(block_validation["article_id"]),
                    block_validation["label"].tolist(), TEXT, model, SETTINGS, seed, MAX_TOKENS)  # fmt: skip
    folder = WORK / "runs" / name
    done = (folder / "training.json").is_file() and (folder / "validation.npy").is_file()
    if not done or (keep_model is not None and not (keep_model / "config.json").is_file()):
        folder.mkdir(parents=True, exist_ok=True)
        print(f"training {name}: {model}, seed {seed}, {len(block_train)} headlines", flush=True)
        model_dir, started = TEMP / name, time.time()
        try:
            result = fine_tune(texts(block_train), targets, texts(block_validation), block_validation["label"].tolist(),
                               model_dir, model_name=model, seed=seed, **SETTINGS)  # fmt: skip
            np.save(folder / "validation.npy", predict(model_dir, texts(block_validation)))
            if keep_model is not None:
                shutil.rmtree(keep_model, ignore_errors=True)
                shutil.copytree(model_dir, keep_model)
        finally:
            shutil.rmtree(model_dir, ignore_errors=True)
        result["seconds"] = time.time() - started
        (folder / "training.json").write_text(json.dumps(result))
    return {"name": name, "training": json.loads((folder / "training.json").read_text()),
            "validation": np.load(folder / "validation.npy")}  # fmt: skip


def on_blocks(model: str) -> list[dict]:
    """One candidate on every block with every comparison seed: one row per run."""
    rows = []
    for number, (block_train, block_validation) in enumerate(blocks, start=1):
        for seed in COMPARE_SEEDS:
            got = run(block_train, block_validation, model=model, seed=seed)
            passes = got["training"]["epochs"]
            kept = next(p for p in passes if p["epoch"] == got["training"]["best_epoch"])
            rows.append({"block": number, "seed": seed, **measure(block_validation["label"].tolist(), got["validation"]),
                         "passes": len(passes), "kept": kept["epoch"], "training_loss": kept["train_loss"],
                         "minutes": got["training"]["seconds"] / 60})  # fmt: skip
    return rows


# %%
runs = pd.concat([pd.DataFrame(on_blocks(model)).assign(candidate=name) for name, model in CANDIDATES.items()])
display(runs.set_index(["candidate", "block", "seed"])[["loss", "accuracy", "macro_f1", "training_loss", "kept", "passes", "minutes"]])
caption(
    f"Every run: {len(CANDIDATES)} candidates × {BLOCKS} blocks × {len(COMPARE_SEEDS)} seeds, {BLOCK} validation "
    f"headlines a block ({blocks[0][1]['created_at'].min():%Y-%m-%d} to {blocks[-1][1]['created_at'].max():%Y-%m-%d})."
)

# %%
by_candidate = runs.groupby("candidate")
comparison = pd.DataFrame(
    {
        "validation loss": by_candidate["loss"].mean(),
        "loss spread (sd)": by_candidate["loss"].std(),
        "accuracy": by_candidate["accuracy"].mean(),
        "accuracy spread (sd)": by_candidate["accuracy"].std(),
        "macro F1": by_candidate["macro_f1"].mean(),
        "training loss": by_candidate["training_loss"].mean(),
        "pass kept": by_candidate["kept"].mean(),
        "minutes a run": by_candidate["minutes"].mean(),
    }
).loc[list(CANDIDATES)]
display(blank(pd.concat([comparison, baseline_table])))
fig, ax = plt.subplots(figsize=(9, 1.6))
for place, name in enumerate(reversed(list(CANDIDATES))):
    losses = runs.loc[runs["candidate"] == name, "loss"]
    ax.scatter(losses, [place] * len(losses), color=MUTED, s=14, zorder=2)
    ax.scatter([losses.mean()], [place], color=ACCENT, s=70, zorder=3)
ax.set_yticks(range(len(CANDIDATES)), list(reversed(list(CANDIDATES))))
ax.set(title="Validation loss: each run (grey) and the mean (blue)")
ax.grid(axis="y", visible=False)
plt.show()
caption(
    f"Mean and spread over {len(runs) // len(CANDIDATES)} runs a candidate ({BLOCKS} blocks × {len(COMPARE_SEEDS)} "
    f"seeds, {BLOCK} validation headlines a block). Baselines: mean of the blocks."
)

# %%
per_block = runs.groupby(["candidate", "block"])
SEED_SPREAD = {
    "loss": float((per_block["loss"].max() - per_block["loss"].min()).mean()),
    "accuracy": float((per_block["accuracy"].max() - per_block["accuracy"].min()).mean()),
}
roberta_row, deberta_row = comparison.loc["RoBERTa (social media)"], comparison.loc["DeBERTa-v3"]
loss_lead = float(roberta_row["validation loss"] - deberta_row["validation loss"])  # above zero: DeBERTa is ahead
accuracy_lead = float(deberta_row["accuracy"] - roberta_row["accuracy"])
rule = {
    "DeBERTa-v3 has the lower validation loss": loss_lead > 0,
    "DeBERTa-v3 has the higher validation accuracy": accuracy_lead > 0,
    "its lead in loss is larger than the seed spread": loss_lead > SEED_SPREAD["loss"],
}
WINNER = "DeBERTa-v3" if all(rule.values()) else "RoBERTa (social media)"
MODEL = CANDIDATES[WINNER]
display(pd.Series(rule, name="holds").to_frame())
why = (
    f"DeBERTa-v3 against RoBERTa: validation loss {deberta_row['validation loss']:.3f} against "
    f"{roberta_row['validation loss']:.3f} (a lead of {loss_lead:+.3f}; seed spread {SEED_SPREAD['loss']:.3f}), "
    f"accuracy {deberta_row['accuracy']:.1%} against {roberta_row['accuracy']:.1%} (a lead of "
    f"{accuracy_lead * 100:+.1f} points; seed spread {SEED_SPREAD['accuracy'] * 100:.1f}). "
    + (
        "All three parts of the written rule hold, so DeBERTa-v3 wins."
        if WINNER == "DeBERTa-v3"
        else f"{sum(rule.values())} of the {len(rule)} parts of the written rule hold, so RoBERTa wins as the smaller model."
    )
)
say(f"**Found.** {why} The other candidate is not trained further and is not saved.")
store("comparison", {"winner": WINNER, "model": MODEL, "why": why, "rule": rule, "seed_spread": SEED_SPREAD,
                     "table": comparison.to_dict("index"), "runs": runs.to_dict("records")})  # fmt: skip
minutes_spent = float(runs["minutes"].sum())
say(f"The {len(runs)} runs took {minutes_spent:.0f} minutes of training in all on this machine ({DEVICE}).")

# %% [markdown]
# ### Earlier candidates
#
# Round 4 (decisions 101 and 102) also trained FinBERT and began a finance-tuned
# DeBERTa-v3. Both were dropped from this notebook (decision 103). Their figures are
# kept here as they were stored then: full-size blocks, labels as they stood in round 4.
# They are not comparable with a fast run above.

# %%
if not EARLIER.is_file():
    say(f"Earlier candidates: not available: {EARLIER.as_posix()}")
else:
    earlier = json.loads(EARLIER.read_text())
    rows = {}
    for name, each in earlier["models"].items():
        frame = pd.DataFrame(each["runs"])
        rows[name] = {
            "model": each["model"],
            "runs stored": len(frame),
            "validation loss": frame["loss"].mean() if len(frame) else np.nan,
            "loss spread (sd)": frame["loss"].std() if len(frame) > 1 else np.nan,
            "accuracy": frame["accuracy"].mean() if len(frame) else np.nan,
            "status": "in the comparison above" if each["model"] in CANDIDATES.values() else "dropped",
        }
    display(blank(pd.DataFrame(rows).T))
    caption(
        f"Round 4, read from stored runs: {earlier['blocks']} blocks of {earlier['block']} validation headlines, seeds "
        f"{earlier['seeds']}, input “{earlier['input text']}”, labels: {earlier['labels']}. A full set is "
        f"{earlier['blocks'] * len(earlier['seeds'])} runs; a model with fewer was stopped before it finished."
    )

# %% [markdown]
# ## 11. Training of the winner
#
# *How does loss move pass by pass, and where does overfitting start?*
#
# The winner is trained on the last block's training part, once per final seed, to see
# how much one training differs from the next. **One model is saved**: the one with the
# seed fixed in the switches (`PUBLISH_SEED`), not the best of them, so that the saved
# model's validation figure is not picked from several.
#
# Training loss is always below validation loss, so a gap between them is not by itself
# overfitting; the sign is **validation loss turning upwards** while training loss
# keeps falling.

# %%
truth = validation["label"].tolist()
final_runs = {
    seed: run(train, validation, model=MODEL, seed=seed, keep_model=MODEL_DIR if seed == PUBLISH_SEED else None)
    for seed in FINAL_SEEDS
}
fig, axes = plt.subplots(1, len(FINAL_SEEDS), figsize=(4.3 * len(FINAL_SEEDS), 2.8), sharey=True, squeeze=False)
curve_rows = {}
for ax, (seed, got) in zip(axes[0], final_runs.items()):
    frame, kept = pd.DataFrame(got["training"]["epochs"]).set_index("epoch"), got["training"]["best_epoch"]
    ax.plot(frame.index, frame["train_loss"], marker="o", color=MUTED, label="training")
    ax.plot(frame.index, frame["validation_loss"], marker="o", color=ACCENT, label="validation")
    ax.axvline(kept, color=INK, ls="--", lw=0.9)
    ax.set(title=f"seed {seed}{' (saved)' if seed == PUBLISH_SEED else ''}", xlabel="pass", xticks=frame.index)
    curve_rows[f"seed {seed}"] = {
        "pass kept": kept,
        "passes run": len(frame),
        "validation loss, kept pass": frame.loc[kept, "validation_loss"],
        "validation loss, last pass": frame["validation_loss"].iloc[-1],
        "training loss, kept pass": frame.loc[kept, "train_loss"],
        "training loss, last pass": frame["train_loss"].iloc[-1],
    }
axes[0][0].set_ylabel("loss")
axes[0][0].legend()
plt.show()
curves = pd.DataFrame(curve_rows).T
display(curves)
caption(
    f"{WINNER}: loss by pass for {len(FINAL_SEEDS)} seeds; {len(train):,} training headlines ({window(train)}), "
    f"{len(validation)} validation headlines ({window(validation)}). Dashed: the pass kept."
)

# %%
rise = curves["validation loss, last pass"] - curves["validation loss, kept pass"]
fall = curves["training loss, kept pass"] - curves["training loss, last pass"]
under = curves["validation loss, kept pass"] - curves["training loss, kept pass"]
say(
    f"**Found.** Validation loss is lowest at pass {curves['pass kept'].astype(int).tolist()} for the "
    f"{len(curves)} seeds. In {int((rise > 0).sum())} of {len(curves)} runs it is higher at the last pass "
    f"run than at the kept pass (by {rise.mean():.3f} on average) while training loss fell a further "
    f"{fall.mean():.3f}; passes after the kept one are thrown away. At the kept pass training loss is "
    f"{curves['training loss, kept pass'].mean():.3f} and validation loss "
    f"{curves['validation loss, kept pass'].mean():.3f} (validation minus training: {under.mean():+.3f}); "
    f"validation loss is {'under' if curves['validation loss, kept pass'].mean() < KNOWS_NOTHING else 'not under'} "
    f"the {KNOWS_NOTHING:.3f} of a model that knows nothing."
)

# %% [markdown]
# ## 12. Validation results
#
# *How good is the saved model on the validation headlines, and how much is luck of the seed?*

# %%
per_seed = pd.DataFrame({f"seed {seed}": measure(truth, got["validation"]) for seed, got in final_runs.items()}).T
display(pd.concat([per_seed, per_seed.agg(["mean", "std"]).rename(index={"std": "spread (sd)"})]))
caption(f"{WINNER} on the last validation block: {len(truth)} headlines ({window(validation)}), seeds {list(FINAL_SEEDS)}.")

# %%
raw = final_runs[PUBLISH_SEED]["validation"]  # the saved model's probabilities, before calibration
saved = measure(truth, raw)
saved_low, saved_high = wilson(saved["accuracy"], len(truth))
last_block = {name.removeprefix("baseline: "): each[-1] for name, each in baselines().items()}
display(
    pd.DataFrame(
        {"the saved model": {"loss": saved["loss"], "accuracy": saved["accuracy"]},
         **{f"baseline: {name}": {"loss": each["loss"], "accuracy": each["accuracy"]} for name, each in last_block.items()}}
    ).T  # fmt: skip
)
display(per_label(truth, answers(raw)))
by_market_validation = pd.DataFrame(
    {
        market: {"headlines": len(part), "accuracy": float(np.mean(np.array(answers(raw))[part.index] == np.array(truth)[part.index]))}
        for market, part in validation.reset_index(drop=True).groupby("market")
    }
).T
display(by_market_validation)
caption(
    f"The saved model (seed {PUBLISH_SEED}) on {len(truth)} validation headlines ({window(validation)}): against "
    "the baselines on the same headlines, then per label, then per market."
)
weakest_label = per_label(truth, answers(raw))["f1"].idxmin()
say(
    f"**Found.** The saved model's validation accuracy is {saved['accuracy']:.1%} (95% range {saved_low:.1%} to "
    f"{saved_high:.1%} on {len(truth)} headlines) and its loss is {saved['loss']:.3f}. Across the "
    f"{len(FINAL_SEEDS)} seeds accuracy is {per_seed['accuracy'].mean():.1%} with a spread of "
    f"{per_seed['accuracy'].std() * 100:.1f} points, so a difference smaller than that is no measurable "
    f"difference. Its weakest label is {weakest_label}. These figures lean optimistic (section 10); "
    f"the reachable range from the labels is {low:.1%} to {high:.1%} (section 4)."
)

# %% [markdown]
# ## 13. Calibration
#
# *When the model says how sure it is, is it right that often?*
#
# One number, a temperature, divides the model's scores before they become
# probabilities. It changes no answer, only how sure the model says it is. It is fitted
# on the validation block and scored on the same block, so the improvement shown here
# is the most favourable case.


# %%
def with_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / temperature
    scaled = np.exp(logits - logits.max(axis=1, keepdims=True))
    return scaled / scaled.sum(axis=1, keepdims=True)


def reliability(labels: list[str], probabilities: np.ndarray) -> pd.DataFrame:
    """Headlines grouped by stated confidence, with how often each group was right."""
    frame = pd.DataFrame({"said": probabilities.max(axis=1), "right": np.array(answers(probabilities)) == np.array(labels)})
    frame["group"] = pd.cut(frame["said"], [1 / 3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], include_lowest=True)
    grouped = frame.groupby("group", observed=True)
    return pd.DataFrame({"headlines": grouped.size(), "said": grouped["said"].mean(), "right": grouped["right"].mean()})


def calibration_gap(labels: list[str], probabilities: np.ndarray) -> float:
    """The average distance between stated confidence and accuracy, weighted by group size."""
    table = reliability(labels, probabilities)
    return float((table["headlines"] / table["headlines"].sum() * (table["said"] - table["right"]).abs()).sum())


# %%
tried = np.arange(0.5, 5.0001, 0.05)
TEMPERATURE = float(tried[int(np.argmin([log_loss(truth, with_temperature(raw, t)) for t in tried]))])
calibrated = with_temperature(raw, TEMPERATURE)
fig, ax = plt.subplots(figsize=(4.8, 3.6))
ax.plot([1 / 3, 1], [1 / 3, 1], color=MUTED, ls="--", label="perfectly calibrated")
for name, given, shade in (("before", raw, INK), ("after", calibrated, ACCENT)):
    table = reliability(truth, given)
    ax.plot(table["said"], table["right"], marker="o", color=shade, label=name)
ax.set(xlabel="how sure it said it was", ylabel="how often it was right")
ax.legend()
plt.show()
display(reliability(truth, calibrated))
caption(f"Reliability before and after the temperature, {len(truth)} validation headlines ({window(validation)}).")
validation_after = measure(truth, calibrated)
say(
    f"**Found.** Temperature {TEMPERATURE:.2f}. The average distance between stated confidence and accuracy "
    f"goes from {calibration_gap(truth, raw):.3f} to {calibration_gap(truth, calibrated):.3f}; validation loss "
    f"from {saved['loss']:.3f} to {validation_after['loss']:.3f}; accuracy is unchanged at "
    f"{validation_after['accuracy']:.1%}."
)
final = store(
    "final",
    {
        "winner": WINNER,
        "model": MODEL,
        "seed": PUBLISH_SEED,
        "text": TEXT,
        "settings": SETTINGS,
        "temperature": TEMPERATURE,
        "train": len(train),
        "headlines": len(validation),
        "window": window(validation),
        "validation": validation_after,
        "seed_spread_accuracy": float(per_seed["accuracy"].std()),
    },
)

# %% [markdown]
# ## 14. Error analysis
#
# *Where is the saved model wrong?* On the validation block, so that the test set stays
# read once.

# %%
checked = pd.DataFrame(
    {"label": truth, "said": answers(calibrated), "market": validation["market"].tolist(), "sure": calibrated.max(axis=1)}
)
checked["right"] = checked["label"] == checked["said"]
confusion = pd.crosstab(pd.Categorical(checked["label"], LABELS), pd.Categorical(checked["said"], LABELS), dropna=False)
fig, axes = plt.subplots(1, 3, figsize=(13, 3.1))
axes[0].imshow(confusion, cmap="GnBu")
axes[0].set(xticks=range(3), yticks=range(3), xticklabels=LABELS, yticklabels=LABELS,
            xlabel="the model said", ylabel="the label", title="Labels against answers")  # fmt: skip
axes[0].grid(False)
for r in range(3):
    for c in range(3):
        dark = confusion.iloc[r, c] > confusion.to_numpy().max() / 2
        axes[0].text(c, r, int(confusion.iloc[r, c]), ha="center", va="center", color="white" if dark else INK)
by_market = checked.groupby("market")["right"].agg(["size", "mean"])
axes[1].barh(by_market.index, by_market["mean"], color=ACCENT)
axes[1].set(title="Accuracy by market", xlim=(0, 1))
axes[2].hist([checked.loc[checked["right"], "sure"], checked.loc[~checked["right"], "sure"]],
             bins=10, color=[GOOD, BAD], label=["right", "wrong"])  # fmt: skip
axes[2].set(title="Stated confidence, right against wrong")
axes[2].legend()
plt.show()
wrong = checked[~checked["right"]]
pairs = wrong.groupby(["label", "said"]).size().sort_values(ascending=False).rename("headlines").to_frame()
pairs["share of all errors"] = pairs["headlines"] / max(len(wrong), 1)
display(pairs)
caption(f"Validation block, {len(checked)} headlines ({window(validation)}), {len(wrong)} of them wrong.")

# %%
# Made-up headlines, with the label the written rule gives each. They show how the saved
# model behaves without printing any of the provider's text.
MADE_UP = [
    ("Bitcoin", "Example Fund Reports Record Inflows Into Its Bitcoin Product", "positive"),
    ("Bitcoin", "Exchange Halts Withdrawals After Reported Hack", "negative"),
    ("Bitcoin", "Bitcoin Trades Near $60,000 Ahead Of Fed Minutes", "neutral"),
    ("Gold", "Gold Climbs To A Three-Week High As Dollar Weakens", "positive"),
    ("Gold", "Gold Slips As Treasury Yields Rise", "negative"),
    ("Gold", "What To Watch In Metals This Week", "neutral"),
    ("US stocks", "Stocks Rally After Inflation Cools More Than Expected", "positive"),
    ("US stocks", "Example Corp Cuts Its Full-Year Forecast, Shares Slide", "negative"),
    ("US stocks", "Example Corp To Report Third-Quarter Results On Thursday", "neutral"),
    ("US stocks", "Tech Shares Rise While Energy Falls In Mixed Session", "neutral"),
]
made_up_frame = pd.DataFrame(MADE_UP, columns=["market", "headline", "label under the rule"]).assign(summary="")
made_up_said = with_temperature(predict(MODEL_DIR, texts(made_up_frame)), TEMPERATURE)
display(
    made_up_frame.drop(columns="summary").assign(
        **{"the model said": answers(made_up_said), "how sure": made_up_said.max(axis=1)}
    )
)
made_up_right = int(sum(a == b for a, b in zip(answers(made_up_said), made_up_frame["label under the rule"])))
caption(f"{len(MADE_UP)} made-up headlines read by the saved model. {made_up_right} match the label the rule gives.")
if SHOW_EXAMPLES:
    shown = validation.reset_index(drop=True).assign(said=checked["said"], sure=checked["sure"])[~checked["right"]]
    display(shown.sort_values("sure", ascending=False)[["market", "headline", "label", "said", "sure"]].head(15))
    caption(f"The real validation headlines the model was most sure about and got wrong (up to 15 of {len(wrong)}), {window(validation)}.")
else:
    say("Real headlines are not shown (`SHOW_EXAMPLES = False`).")

# %%
tones = {"positive", "negative"}
backwards = float((checked["label"].isin(tones) & checked["said"].isin(tones) & ~checked["right"]).mean())
worst = by_market["mean"].idxmin()
if len(wrong):
    (top_label, top_said) = pairs.index[0]
    say(
        f"**Found.** The commonest error is *{top_label}* called *{top_said}* ({int(pairs['headlines'].iloc[0])} "
        f"headlines, {pairs['share of all errors'].iloc[0]:.0%} of errors). The opposite tone is given on "
        f"{backwards:.1%} of headlines. The weakest market is {worst} ({by_market.loc[worst, 'mean']:.1%} of "
        f"{int(by_market.loc[worst, 'size'])}). Mean stated confidence is {wrong['sure'].mean():.2f} on wrong "
        f"answers against {checked.loc[checked['right'], 'sure'].mean():.2f} on right ones."
    )
else:
    say(f"**Found.** No validation headline is wrong ({len(checked)} headlines).")

# %% [markdown]
# ## 15. Test
#
# *How good is the saved model on headlines it never saw, against the two bars?*
#
# The test set holds headlines from the test period on, newer than anything trained or
# chosen on, labelled before any of these models existed. **This cell scores it only
# when `RUN_TEST` is True, and only once**: the result is stored and read back after
# that, so the test set cannot be used to try something else.
#
# Because validation figures lean optimistic (sections 10 to 13), the distance from
# validation to test is wider than it would be against an untouched validation set.
# That makes the "not overfitted" bar harder to pass, not easier.

# %%
result = stored("test")
if result is None and RUN_TEST:
    new = with_temperature(predict(MODEL_DIR, texts(test)), TEMPERATURE)
    said_by, scores = {"new": answers(new)}, {"new": measure(_test_labels, new)}
    if IN_USE.is_dir():
        in_use = predict(IN_USE, app_text(test))
        said_by["in use"], scores["in use"] = answers(in_use), measure(_test_labels, in_use)
    for score in scores.values():
        score["from"], score["to"] = wilson(score["accuracy"], len(test))
    check = mcnemar(_test_labels, said_by["in use"], said_by["new"]) if "in use" in said_by else None
    gap = validation_after["accuracy"] - scores["new"]["accuracy"]
    loss_gap = scores["new"]["loss"] - validation_after["loss"]
    better = None if check is None else bool(scores["new"]["accuracy"] > scores["in use"]["accuracy"] and check["p_value"] < P_BELOW)
    by_market_test = {}
    for market, part in test.groupby("market"):
        right = float(np.mean([said_by["new"][i] == _test_labels[i] for i in part.index]))
        by_market_test[market] = {"headlines": len(part), "accuracy": right, "from": wilson(right, len(part))[0], "to": wilson(right, len(part))[1]}
    result = store(
        "test",
        {
            "model": MODEL,
            "headlines": len(test),
            "window": window(test),
            "scores": scores,
            "comparison": check,
            "table": pd.crosstab(pd.Categorical(_test_labels, LABELS), pd.Categorical(said_by["new"], LABELS), dropna=False).to_numpy().tolist(),
            "per_label": per_label(_test_labels, said_by["new"]).to_dict("index"),
            "by_market": by_market_test,
            "validation": validation_after,
            "accuracy_gap": gap,
            "loss_gap": loss_gap,
            "bars": {"better than the model in use": better, "not overfitted": bool(gap <= ACCURACY_GAP and loss_gap <= LOSS_GAP)},
        },
    )

if result is None:
    say(f"Test results: not available: {(WORK / 'test.json').as_posix()}. Set `RUN_TEST = True` in the switches and run this cell.")
else:
    counts = np.array(result["table"]).sum(axis=1)
    rows = {"baseline: always the commonest label": {"accuracy": counts.max() / counts.sum()}}
    for key, shown in (("in use", "finbert-radar-1 (in the app)"), ("new", "the saved model")):
        if key in result["scores"]:
            s = result["scores"][key]
            rows[shown] = {"accuracy": s["accuracy"], "95% from": s["from"], "95% to": s["to"], "loss": s["loss"], "macro F1": s["macro_f1"]}
    display(blank(pd.DataFrame(rows).T))
    caption(f"Test set: {result['headlines']} headlines, {result['window']}. 95% range: Wilson interval.")
    new_score = result["scores"]["new"]
    if result["comparison"] is None:
        say(f"**Bar 1, better than the model in use.** not available: {IN_USE.as_posix()}")
    else:
        check, old = result["comparison"], result["scores"]["in use"]
        say(
            f"**Bar 1, better than the model in use.** Accuracy {new_score['accuracy']:.1%} against "
            f"{old['accuracy']:.1%}. Only the saved model was right on {check['only_second_right']} headlines "
            f"and only the model in use on {check['only_first_right']}; McNemar p = {check['p_value']:.2g} "
            f"(bar: below {P_BELOW}). **{'Pass' if result['bars']['better than the model in use'] else 'Fail'}.**"
        )
    say(
        f"**Bar 2, not overfitted.** Validation accuracy {result['validation']['accuracy']:.1%}, test accuracy "
        f"{new_score['accuracy']:.1%}: a gap of {result['accuracy_gap'] * 100:.1f} points (bar: at most "
        f"{ACCURACY_GAP * 100:.0f}). Validation loss {result['validation']['loss']:.3f}, test loss "
        f"{new_score['loss']:.3f}: a gap of {result['loss_gap']:.3f} (bar: at most {LOSS_GAP:.2f}). "
        f"**{'Pass' if result['bars']['not overfitted'] else 'Fail'}.**"
    )
    display(pd.DataFrame(result["table"], index=LABELS, columns=LABELS).rename_axis(index="the label", columns="the saved model said"))
    display(pd.DataFrame(result["by_market"]).T)
    caption(f"Confusion matrix and accuracy by market with its 95% range, {result['headlines']} test headlines ({result['window']}).")
    say(
        f"**Found.** Test accuracy is {new_score['accuracy']:.1%} (95% range {new_score['from']:.1%} to "
        f"{new_score['to']:.1%}); the reachable range from the labels is {low:.1%} to {high:.1%} (section 4)."
    )

# %% [markdown]
# ## 16. Save and publish
#
# *What is saved, where, and what does someone else need to use it?*
#
# The saved model is one folder: the model's weights, its tokenizer, a small settings
# file (label order, temperature, how the input text is built), a Python file holding
# the text preparation, and a model card (`README.md`) written from this run's
# numbers. The app loads the folder from disk by its version name. The same folder can
# be uploaded to a **private** Hugging Face repository.
#
# The upload needs a Hugging Face token. It is read by the library from the `HF_TOKEN`
# environment variable or from an earlier `hf auth login`. **It is never typed into a
# cell and never printed.**

# %%
SHORT_NAME = {ROBERTA: "twitter-roberta-base", DEBERTA: "deberta-v3-base"}
KNOWN_LICENCE = {ROBERTA: "cc-by-4.0", DEBERTA: "mit"}
hub_name = HUB_NAME or f"{SHORT_NAME[MODEL]}-financial-news-sentiment"
saved_config = AutoConfig.from_pretrained(MODEL_DIR.as_posix())
tone_config = {
    "model_version": MODEL_VERSION,
    "base_model": MODEL,
    "labels": [saved_config.id2label[i] for i in sorted(saved_config.id2label)],
    "temperature": TEMPERATURE,
    "max_tokens": MAX_TOKENS,
    "text": TEXT,
    "text_options": TEXTS[TEXT],
    "markets": sorted(train["market"].unique()),
    "trained_on": {"headlines": len(train), "window": window(train)},
    "validated_on": {"headlines": len(validation), "window": window(validation)},
    "fast_run": FAST_RUN,
}
(MODEL_DIR / "tone_config.json").write_text(json.dumps(tone_config, indent=1))
display(pd.Series(tone_config, name="value").to_frame())
caption(f"`tone_config.json`, saved beside the model in {MODEL_DIR.as_posix()}.")

# %%
# The text preparation as one Python file, written from the functions defined above so
# the two cannot differ. It is checked by running it on made-up text.
patterns = {"_NUMBER": _NUMBER, "_NOT_WORD": _NOT_WORD, "_EXCHANGE_TAG": _EXCHANGE_TAG,
            "_REVISION_TAG": _REVISION_TAG, "_SOURCE_TAIL": _SOURCE_TAIL, "_SENTENCE_END": _SENTENCE_END}  # fmt: skip
preparation = "\n".join(
    [
        f'"""Build the text {MODEL_VERSION} expects. Use prepare(headline, summary, market)."""',
        "",
        "import html",
        "import re",
        "",
        *[f"{name} = re.compile({pattern.pattern!r}, {int(pattern.flags & re.IGNORECASE)})" for name, pattern in patterns.items()],
        "",
        "",
        *[inspect.getsource(function).rstrip() + "\n\n" for function in (headline_key, clean_headline, whole_sentences, model_text)],
        'def prepare(headline: str, summary: str = "", market: str = "") -> str:',
        f'    """The input text: {TEXT}."""',
        f"    return model_text(headline, summary, market, with_asset={TEXTS[TEXT]['with_asset']}, with_summary={TEXTS[TEXT]['with_summary']})",
        "",
    ]
)
(MODEL_DIR / "text_preparation.py").write_text(preparation, encoding="utf-8")
written: dict = {}
exec(compile(preparation, "text_preparation.py", "exec"), written)  # noqa: S102
probe = [(h, "Shares fell on the news. Analysts said the", m) for m, h, _ in MADE_UP] + [(h, "", "Gold") for h in made_up]
same = sum(written["prepare"](h, s, m) == model_text(h, s, m, **TEXTS[TEXT]) for h, s, m in probe)
say(f"`text_preparation.py` gives the same text as this notebook on {same} of {len(probe)} made-up inputs.")
if same != len(probe):
    raise ValueError("The saved text preparation differs from the notebook's")


# %%
def licence_of(model: str) -> str:
    """The base model's licence as its own repository states it, else the one noted here."""
    try:
        from huggingface_hub import model_info

        return str(model_info(model).card_data.license or KNOWN_LICENCE[model])
    except Exception:  # noqa: BLE001 (no network, or no licence stated)
        return KNOWN_LICENCE[model]


def percent_range(score: dict) -> str:
    return f"{score['accuracy']:.1%} (95% range {score['from']:.1%} to {score['to']:.1%})"


def build_card(repo_id: str) -> str:
    """The model card, written from this run's numbers."""
    tested = result is not None
    label_mix = ", ".join(f"{label} {share_of:.0%}" for label, share_of in train["label"].value_counts(normalize=True).items())
    head = [
        "---",
        "language: en",
        f"license: {licence_of(MODEL)}",
        "library_name: transformers",
        "pipeline_tag: text-classification",
        f"base_model: {MODEL}",
        "tags:",
        "- financial-news",
        "- sentiment-analysis",
        "- finance",
        "- news-headlines",
        "metrics:",
        "- accuracy",
        "- f1",
        "---",
    ]
    if tested:
        test_lines = [
            f"- **Accuracy: {percent_range(result['scores']['new'])}** on {result['headlines']} headlines, {result['window']}.",
            f"- Log loss {result['scores']['new']['loss']:.3f}, macro F1 {result['scores']['new']['macro_f1']:.3f}.",
            "",
            "| Market | Headlines | Accuracy | 95% range |",
            "|---|---|---|---|",
            *[f"| {market} | {each['headlines']} | {each['accuracy']:.1%} | {each['from']:.1%} to {each['to']:.1%} |" for market, each in result["by_market"].items()],
            "",
            "| Label | Headlines | Precision | Recall | F1 |",
            "|---|---|---|---|---|",
            *[f"| {label} | {int(each['headlines'])} | {each['precision']:.2f} | {each['recall']:.2f} | {each['f1']:.2f} |" for label, each in result["per_label"].items()],
        ]
        if "in use" in result["scores"]:
            test_lines.append("")
            test_lines.append(f"The model this one replaces scored {percent_range(result['scores']['in use'])} on the same headlines (McNemar p = {result['comparison']['p_value']:.2g}).")
    else:
        test_lines = ["Not run yet. This card was written before the test."]
    body = f"""
# {hub_name}

{"**This card comes from a fast run on 200 headlines. Its numbers are not results.**" if FAST_RUN else ""}

A three-class tone classifier for English financial news headlines: **positive**,
**negative** or **neutral** for the asset the headline is about. It is
[`{MODEL}`](https://huggingface.co/{MODEL}) trained further on {len(train):,} headlines about
{", ".join(tone_config["markets"])}. Version `{MODEL_VERSION}`, from the
[RADAR](https://github.com/LouSens/RADAR) project.

## Intended use

Reading the tone of a news headline about a traded asset, as a description of the news.
It is not a price forecast and was not tested as one: in the project it comes from, news
tone improved no forecast. Do not use it to make trading decisions.

## How to use

The model expects text built in one fixed way: **{TEXT}**, that is
`"<asset's plain name>: <cleaned headline>. <the summary's whole sentences>"`. The file
`text_preparation.py` in this repository builds it; `tone_config.json` holds the settings.
The asset names seen in training are {", ".join(f"`{m}`" for m in tone_config["markets"])}; another
asset's plain name can be given, but that was not tested. The summary may be empty.

```python
import torch
from huggingface_hub import hf_hub_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer

repo = "{repo_id}"
tokenizer = AutoTokenizer.from_pretrained(repo)
model = AutoModelForSequenceClassification.from_pretrained(repo).eval()

# text_preparation.py is a small file in this repository: read it before running it.
namespace = {{}}
exec(open(hf_hub_download(repo, "text_preparation.py"), encoding="utf-8").read(), namespace)
text = namespace["prepare"]("Gold climbs to a three-week high as the dollar weakens", market="Gold")

batch = tokenizer([text], truncation=True, max_length={MAX_TOKENS}, return_tensors="pt")
with torch.no_grad():
    logits = model(**batch).logits
probabilities = torch.softmax(logits / {TEMPERATURE:.2f}, dim=-1)[0]  # {TEMPERATURE:.2f}: the temperature
print({{model.config.id2label[i]: round(float(p), 3) for i, p in enumerate(probabilities)}})
```

Output order: {", ".join(f"{i} = {name}" for i, name in enumerate(tone_config["labels"]))}. Dividing the
scores by the temperature ({TEMPERATURE:.2f}) changes no answer, only how sure the model says it is.

## Training data

- {len(train):,} training headlines ({window(train)}) and {len(validation)} validation headlines
  ({window(validation)}), from one commercial news feed, about {", ".join(tone_config["markets"])}.
  Label mix in training: {label_mix}.
- **The labels were written by an AI model (Claude), not by people**, from the headline alone,
  under a written rule. Where two labelling passes exist and differ, the training target is
  split between the two labels.
- Two passes over {len(twice)} headlines gave the same label on {share:.1%} of them (Cohen's kappa
  {float(agreement.loc["all", "kappa"]):.2f}). On labels like these the best reachable accuracy lies between
  {low:.1%} and {high:.1%}.
- The headlines belong to the news provider and are not published with this model.

## Training procedure

Chosen between two base models on {BLOCKS} walk-forward blocks of {BLOCK} validation headlines with
{len(COMPARE_SEEDS)} seeds each, by a rule written before the runs. {why}

| Setting | Value |
|---|---|
| Passes (epochs) | up to {SETTINGS["epochs"]}, keeping the pass with the lowest validation loss; this model kept pass {final_runs[PUBLISH_SEED]["training"]["best_epoch"]} |
| Learning rate | {SETTINGS["learning_rate"]}, linear warm-up over {SETTINGS["warmup_share"]:.0%} of steps, then linear decay |
| Batch size | {SETTINGS["batch_size"]} |
| Weight decay | {SETTINGS["weight_decay"]} |
| Longest input | {MAX_TOKENS} tokens |
| Seed | {PUBLISH_SEED} (fixed before training, not picked from several) |
| Libraries | torch {installed("torch")}, transformers {installed("transformers")} |

The split is by time: every validation and test headline is newer than every training headline,
and no near-copy of a test headline (same words, different numbers) is in training.

## Evaluation

**Validation** ({len(validation)} headlines, {window(validation)}): accuracy {validation_after["accuracy"]:.1%}, log loss
{validation_after["loss"]:.3f}, macro F1 {validation_after["macro_f1"]:.3f}. Across {len(FINAL_SEEDS)} training seeds accuracy
varies by {per_seed["accuracy"].std() * 100:.1f} points (standard deviation). Validation figures lean
optimistic: the same headlines picked the pass that was kept and the temperature.

**Test** (headlines newer than all training and validation data, scored once):

{chr(10).join(test_lines)}

## Limitations

- Scores are agreement with one AI labeller, not with people.
- English only; three markets; one news feed. Other sources, assets and languages are untested.
- Most disagreement between labelling passes, and most of the model's errors, are between
  *neutral* and a tone.
- News changes over time: expect accuracy to fall on headlines far from the training period.

## Reproducing

The notebook `notebooks/04_news.ipynb` in the RADAR repository holds every step, from the data
file to this card.
"""
    return "\n".join(head) + "\n" + body


(MODEL_DIR / "README.md").write_text(build_card(f"<owner>/{hub_name}"), encoding="utf-8")
files = pd.DataFrame(
    {"megabytes": {path.name: path.stat().st_size / 2**20 for path in sorted(MODEL_DIR.iterdir()) if path.is_file()}}
)
display(files)
caption(f"The saved folder {MODEL_DIR.as_posix()}: {len(files)} files, {files['megabytes'].sum():,.0f} MB.")

# %%
# Before anything is uploaded: no file in the folder may hold something shaped like a token.
TOKEN_SHAPE = re.compile(r"hf_[A-Za-z0-9]{20,}")
text_files = [path for path in MODEL_DIR.iterdir() if path.suffix in {".json", ".md", ".py", ".txt"}]
with_token = [path.name for path in text_files if TOKEN_SHAPE.search(path.read_text(encoding="utf-8", errors="ignore"))]
blockers = []
if not PUSH_TO_HUB:
    blockers.append("`PUSH_TO_HUB` is False")
if FAST_RUN:
    blockers.append("a fast run is never uploaded")
if result is None:
    blockers.append("the test has not been run")
elif MIN_TEST_ACCURACY is None:
    blockers.append("`MIN_TEST_ACCURACY` is not set")
elif result["scores"]["new"]["accuracy"] < MIN_TEST_ACCURACY:
    blockers.append(f"test accuracy {result['scores']['new']['accuracy']:.1%} is under `MIN_TEST_ACCURACY` ({MIN_TEST_ACCURACY:.1%})")
if with_token:
    blockers.append(f"something shaped like a token is in {with_token}")

if blockers:
    say(f"**Not uploaded**: {'; '.join(blockers)}. The model is saved locally in `{MODEL_DIR.as_posix()}`.")
else:
    from huggingface_hub import HfApi

    try:
        api = HfApi()  # the token comes from HF_TOKEN or the saved login; it is never printed
        repo_id = f"{api.whoami()['name']}/{hub_name}"
        api.create_repo(repo_id, repo_type="model", private=True, exist_ok=True)
        if not api.model_info(repo_id).private:
            raise PermissionError("the repository exists and is public")
        (MODEL_DIR / "README.md").write_text(build_card(repo_id), encoding="utf-8")
        api.upload_folder(repo_id=repo_id, folder_path=MODEL_DIR.as_posix(), commit_message=f"{MODEL_VERSION}: model, tokenizer, settings and card")
        say(f"**Uploaded** to the private repository `{repo_id}` ({len(files)} files).")
    except Exception as error:  # noqa: BLE001 (only the kind of error is shown, never its text)
        say(f"**Upload failed** ({type(error).__name__}). Nothing else in this notebook depends on it.")

# %% [markdown]
# ## 17. Limitations
#
# *What should a reader not conclude from this?*

# %%
say("- **The labels are written by a model**, not a person. Every score here is agreement with that labeller.")
say(
    f"- **The labels limit the score.** Inter-pass agreement is {share:.1%}, so reachable accuracy lies between "
    f"{low:.1%} and {high:.1%} (section 4). It is weakest for {weakest} ({agreement.loc[weakest, 'agreement']:.1%})."
)
say(
    f"- **Seed noise.** Two seeds of the same recipe differ by {SEED_SPREAD['loss']:.3f} in validation loss "
    f"and {SEED_SPREAD['accuracy'] * 100:.1f} points of accuracy on average (section 10); the lead between the two "
    f"candidates was {abs(loss_lead):.3f} and {abs(accuracy_lead) * 100:.1f} points."
)
say(f"- **The data is small**: {len(train):,} training headlines and {len(validation)} validation headlines for the saved model.")
say(
    f"- **Few headlines for some markets**: the test set has {int((test['market'] == smallest).sum())} for {smallest}, "
    "so its per-market figure has a wide range."
)
say(
    "- **Validation is used more than once** (to pick the pass, the candidate and the temperature), so validation "
    "figures lean optimistic. Only section 15 is untouched."
)
say("- **One news feed, three markets, English.** Nothing here says how the model reads other sources.")
if TEXTS[TEXT]["with_summary"]:
    say("- **The labels were written from the headline alone**, while the model also reads the summary where there is one.")
say("- **Tone describes the news; it forecasts nothing.** In this project news tone improved no forecast and drives no alert.")
if FAST_RUN:
    say("- **This was a fast run.** None of its figures is a result.")

# %% [markdown]
# ## 18. Reproducibility
#
# *How is every figure above produced again?*
#
# 1. `uv sync --extra nlp` (or let the first cell install the pinned packages).
# 2. `uv run python backend/scripts/tone_export.py` writes the data file from the app's
#    database. Elsewhere, copy the file and set `DATA_PATH`.
# 3. Set `FAST_RUN = False` and run every cell from the top.
# 4. `uv run python backend/scripts/build_notebooks.py 04_news` does the same from the
#    notebook's source, `notebooks/src/04_news.py`.
#
# Training on a graphics card is not bit-for-bit repeatable, so a rerun gives figures
# within the seed spread of these, not identical ones. Stored runs are read back, not
# trained again; delete `runs/` in the work folder to train afresh.


# %%
def megabytes(folder: Path) -> float:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file()) / 2**20


shutil.rmtree(TEMP, ignore_errors=True)
facts = {
    "data file": DATA_PATH.as_posix(),
    "data file sha256": hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
    "rows used": f"{len(rows_used):,} of {len(labelled):,} labelled; {len(test):,} test",
    "fast run": FAST_RUN,
    "blocks": f"{BLOCKS} of {BLOCK}",
    "comparison seeds": list(COMPARE_SEEDS),
    "final seeds": list(FINAL_SEEDS),
    "saved seed": PUBLISH_SEED,
    "input text": TEXT,
    "winner": f"{WINNER} ({MODEL})",
    "settings": SETTINGS,
    "temperature": TEMPERATURE,
    "work folder": f"{WORK.as_posix()} ({megabytes(WORK):,.0f} MB, of which stored runs {megabytes(WORK / 'runs'):,.1f} MB)",
    "saved model": f"{MODEL_DIR.as_posix()} ({megabytes(MODEL_DIR):,.0f} MB)",
    "temporary checkpoints": f"deleted: {not TEMP.exists()}",
    "free disk": f"{shutil.disk_usage('.').free / 2**30:,.1f} GB",
    "device": DEVICE,
    **{name: metadata.version(name) for name in PINNED},
}
display(pd.Series(facts, name="value").to_frame())
caption("Everything needed to repeat this run, and the disk it used.")
