# %% [markdown]
# # News tone: a three-class classifier for financial headlines
#
# This notebook builds the tone model from the data to the test, one stage at a time.
# **It is self-contained**: all the code is in the cells below, and it needs only two
# data files, not the RADAR app or its database. Run it cell by cell.
#
# **What you need**
#
# | | |
# |---|---|
# | Packages | `torch`, `transformers`, `sentencepiece`, `pandas`, `numpy`, `scipy`, `matplotlib` |
# | Data | `tone_dataset.csv` and `tone_pool.csv`, written by `uv run python backend/scripts/tone_export.py`. They hold the news provider's headlines, so they are not in the public repository: copy them next to the notebook, or to your Drive for Colab |
# | Hardware | A graphics card. On one 6 GB card the whole notebook takes several hours the first time |
#
# **Every training run is stored** in the work folder under a name made from its
# inputs, and each step stores its result as a small file. Running a cell again reads
# what is stored, so you can stop and come back, and a step is repeated by deleting its
# file. The test set is scored only by the cell in section 10, and only when you set
# `RUN_TEST = True`.
#
# The plan and its two pass marks were written down before any run
# (`docs/DECISIONS.md`, decisions 101 and 102). No real headline is printed here; the
# examples are made up.

# %%
# On Colab, run this first:  !pip -q install transformers sentencepiece
import gc
import hashlib
import html
import json
import random
import re
import shutil
import tempfile
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import transformers
from IPython.display import Markdown, display
from scipy.stats import binom, norm
from transformers import (
    AutoConfig,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

warnings.filterwarnings("ignore")
transformers.utils.logging.set_verbosity_error()
transformers.utils.logging.disable_progress_bar()

# --- where things are. Change these lines to run somewhere else. ---
WORK = Path("data/research/tone4")  # results are stored here, and read back from here
DATA = WORK / "tone_dataset.csv"  # the labelled headlines
POOL = WORK / "tone_pool.csv"  # unlabelled articles, for self-training
KEPT_MODELS = Path("data/models/tone-radar-2")  # the final models' files
IN_USE = Path("data/models/finbert-radar-1")  # the model in the app today, if you have it
RUN_TEST = False  # set to True to score the test set, once (section 10)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
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
WORK.mkdir(parents=True, exist_ok=True)


def say(text: str) -> None:
    """Show a sentence built from variables as ordinary notebook text."""
    display(Markdown(text))


def caption(text: str) -> None:
    """A caption: what a table or figure shows, how many headlines, from when to when."""
    say(f"<small>*{text}*</small>")


def blank(table: pd.DataFrame) -> pd.DataFrame:
    """The same table with an empty cell where there is no value."""
    return table.map(lambda value: "" if isinstance(value, float) and np.isnan(value) else value)


def stored(name: str) -> dict | None:
    """A step's stored result, or None if the step has not been run."""
    path = WORK / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def store(name: str, found: dict) -> dict:
    (WORK / f"{name}.json").write_text(json.dumps(found, indent=1, default=str))
    return found


def window(frame: pd.DataFrame) -> str:
    return f"{frame['created_at'].min():%Y-%m-%d} to {frame['created_at'].max():%Y-%m-%d}"


print(f"device: {DEVICE}; torch {torch.__version__}; transformers {transformers.__version__}")

# %% [markdown]
# ## 0. Summary
#
# **Question.** Can the tone of a headline (positive, negative or neutral) be read by a
# model more accurately than by the one the app uses today, without overfitting?
#
# This cell reads what earlier runs of the notebook stored. The first time through it
# says "not available"; run it again at the end.

# %%
final_stored, test_stored = stored("final"), stored("test")
say(
    f"- **Validation.** not available: {(WORK / 'final.json').as_posix()}"
    if final_stored is None
    else f"- **Validation.** The kept model ({final_stored['kept']}; "
    f"{final_stored['choice']['model_name']}) has accuracy "
    f"{final_stored['validation_after']['accuracy']:.1%} and loss "
    f"{final_stored['validation_after']['loss']:.3f} on the last validation block "
    f"({final_stored['validation']} headlines). Validation figures lean optimistic (section 6)."
)
say(
    f"- **Test.** not available: {(WORK / 'test.json').as_posix()}. The test has not been run."
    if test_stored is None
    else f"- **Test.** On {test_stored['headlines']} unseen headlines the new model's accuracy is "
    f"{test_stored['scores']['new']['accuracy']:.1%} (95% range "
    f"{test_stored['scores']['new']['from']:.1%} to {test_stored['scores']['new']['to']:.1%}). "
    + " ".join(
        f"{name}: **{'not available' if passed is None else 'pass' if passed else 'fail'}**."
        for name, passed in test_stored["bars"].items()
    )
)

# %% [markdown]
# ## 1. Problem and metric
#
# *What is predicted, and how is a good prediction measured?*
#
# The input is one headline. The output is a probability for each label; the label with
# the highest probability is the answer. Terms used throughout, each with one meaning:
#
# | Term | Meaning |
# |---|---|
# | accuracy | Share of headlines whose answer matches the label |
# | loss | Log loss (cross-entropy): the average of minus the log of the probability given to the true label. It counts how sure the model was, so a confident wrong answer costs more than an unsure one |
# | macro F1 | F1 worked out per label and averaged, so a rare label counts as much as a common one |
# | pass | One run through all training headlines (an "epoch") |
# | seed | The number that fixes the random order of training; the same recipe with another seed gives a slightly different model |
# | block | A stretch of headlines, later in time than everything the model was trained on, used to validate |
# | validation | Headlines used to make choices. The test set is used for none |
# | underfitting | The model has not learned enough: loss is high on training and validation alike |
# | overfitting | The model has memorised its training headlines: training loss keeps falling while validation loss rises |
#
# Accuracy is what a reader of the app experiences. Loss is used to make choices because
# it uses the whole probability, not only which label came first, so it moves less from
# one run to the next.


# %%
def log_loss(truth: list[str], probabilities: np.ndarray) -> float:
    """Average of -log(probability given to the true label). Columns follow LABELS."""
    column = [LABELS.index(label) for label in truth]
    given = np.asarray(probabilities, dtype=float)[np.arange(len(truth)), column]
    return float(-np.log(np.clip(given, 1e-12, 1.0)).mean())


def answers(probabilities: np.ndarray) -> list[str]:
    return [LABELS[i] for i in probabilities.argmax(axis=1)]


def macro_f1(truth: list[str], said: list[str]) -> float:
    scores = []
    for label in LABELS:
        hit = sum(t == label and s == label for t, s in zip(truth, said))
        given, real = sum(s == label for s in said), sum(t == label for t in truth)
        if real:
            precision, recall = (hit / given if given else 0.0), hit / real
            scores.append(2 * precision * recall / (precision + recall) if hit else 0.0)
    return float(np.mean(scores))


def measure(truth: list[str], probabilities: np.ndarray) -> dict[str, float]:
    said = answers(probabilities)
    return {
        "loss": log_loss(truth, probabilities),
        "accuracy": float(np.mean([t == s for t, s in zip(truth, said)])),
        "macro_f1": macro_f1(truth, said),
    }


def wilson(share: float, n: int, level: float = 0.95) -> tuple[float, float]:
    """The range a share measured on n items could plausibly be in (Wilson interval)."""
    z = norm.ppf(0.5 + level / 2)
    centre = (share + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return float(centre - half), float(centre + half)


def mcnemar(truth: list[str], first: list[str], second: list[str]) -> dict:
    """Are two models different? Uses only the headlines where one is right and one wrong."""
    only_first = sum(a == t and b != t for t, a, b in zip(truth, first, second))
    only_second = sum(a != t and b == t for t, a, b in zip(truth, first, second))
    differing = only_first + only_second
    p = 1.0
    if differing:
        p = min(1.0, 2.0 * float(binom.cdf(min(only_first, only_second), differing, 0.5)))
    return {"only_first_right": only_first, "only_second_right": only_second, "p_value": p}


# The two pass marks of decision 101, read on the test set.
P_BELOW, ACCURACY_GAP, LOSS_GAP = 0.05, 0.05, 0.10
KNOWS_NOTHING = float(np.log(len(LABELS)))

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
    f"There are {len(LABELS)} labels. A model that gives each the same probability has a loss of "
    f"{KNOWS_NOTHING:.3f} (the log of {len(LABELS)}): the mark an untrained model would score."
)
say(
    "**The two bars**, read on the test set: (1) *better than the model in use*: higher accuracy, "
    f"with McNemar's test giving p below {P_BELOW}; (2) *not overfitted*: test accuracy no more "
    f"than {ACCURACY_GAP * 100:.0f} points under validation accuracy, and test loss no more than "
    f"{LOSS_GAP:.2f} above validation loss."
)

# %% [markdown]
# ## 2. Data
#
# *What is there to learn from, and who labelled it?*
#
# One file holds every labelled headline. `part` says what a row is for: `labelled`
# (training and validation) or `test`. **The test rows' labels are not looked at
# anywhere before section 10**; below, the test set is described by its counts, dates
# and text only.

# %%
if not DATA.is_file():
    raise FileNotFoundError(f"{DATA} is missing: run backend/scripts/tone_export.py, or copy the file here")
everything = pd.read_csv(DATA, encoding="utf-8")
everything["created_at"] = pd.to_datetime(everything["created_at"], utc=True, format="ISO8601")
everything["summary"] = everything["summary"].fillna("")
labelled = everything[everything["part"] == "labelled"].reset_index(drop=True)
test = everything[everything["part"] == "test"].reset_index(drop=True)
TEST_FROM = pd.Timestamp("2026-08-01", tz="UTC")
print(f"{len(labelled):,} labelled headlines ({window(labelled)}); {len(test):,} test ({window(test)})")
print("columns:", list(everything.columns))

# %% [markdown]
# **The labelling rule** (decision 101). Every label was written by an AI model (Claude),
# not a person, from the headline alone:
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
# ### Exploring the data

# %%
by_class = pd.crosstab(labelled["market"], labelled["sentiment"])[LABELS]
ax = by_class.plot.barh(stacked=True, color=[TONE_COLOUR[l] for l in LABELS], figsize=(8, 2.2))
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
mix = pd.crosstab(year, labelled["sentiment"], normalize="index")[LABELS]
mix.plot.bar(stacked=True, ax=axes[1], color=[TONE_COLOUR[l] for l in LABELS], legend=False)
axes[1].set(title="Label mix a year (share)", xlabel="")
plt.show()
caption(f"The same {len(labelled):,} headlines by year published.")

# %%
words = labelled["headline"].str.split().str.len()
has_summary = labelled["summary"].str.len() > 0
markets = list(by_class.index)
fig, axes = plt.subplots(1, 2, figsize=(12, 2.8))
for label in LABELS:
    axes[0].hist(words[labelled["sentiment"] == label], bins=range(0, 80, 3), histtype="step",
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
            "median words": words.groupby(labelled["sentiment"]).median(),
            "share over 40 words": (words > 40).groupby(labelled["sentiment"]).mean(),
            "share with a summary": has_summary.groupby(labelled["sentiment"]).mean(),
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
    counts = {label: {} for label in LABELS}
    for words_in, label in zip(tokens, frame["sentiment"]):
        for word in words_in:
            counts[label][word] = counts[label].get(word, 0) + 1
    sizes = frame["sentiment"].value_counts()
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
    "Single words only; no headline is shown."
)

# %%
month = test["created_at"].dt.strftime("%Y-%m").rename("month")
display(pd.crosstab(month, test["market"]).T)
caption(f"The test set by market and month: {len(test):,} headlines, {window(test)}. Labels not read.")
gold_test = int((test["market"] == "Gold").sum())
say(
    f"**Found.** {len(labelled):,} headlines to train and choose on, {len(test):,} to test on. "
    f"Neutral is the largest label ({(labelled['sentiment'] == 'neutral').mean():.0%}), so the "
    "classes are not badly unbalanced and no resampling is used. The mix of markets and labels "
    f"shifts from year to year, which is why the split below is by time. Gold has {gold_test} "
    "test headlines, too few for a figure of its own."
)

# %% [markdown]
# ## 3. Data quality
#
# *Are there repeats, is the text clean, and how far can the labels be trusted?*
#
# **Near-copies.** Many headlines are templates that differ only in a number. Each is
# reduced to a key, and a key may appear only once across all the data. A near-copy in
# both training and test would let the model be scored on something it has seen.

# %%
_NUMBER = re.compile(r"\d[\d,.]*")
_NOT_WORD = re.compile(r"[^a-z#]+")


def headline_key(headline: str) -> str:
    """A headline with case, punctuation and every number removed."""
    return _NOT_WORD.sub(" ", _NUMBER.sub("#", headline.lower())).strip()


pair = ["Example Whale Moves 2,901 Coins Off Exchange", "example whale moves 1,112 coins off exchange!"]
display(pd.DataFrame({"headline (made up)": pair, "key": [headline_key(h) for h in pair]}))
keys = everything["headline"].map(headline_key)
say(
    f"All {len(everything):,} labelled headlines have {keys.nunique():,} distinct keys: "
    f"**{len(everything) - keys.nunique()} near-copies remain**."
)

# %% [markdown]
# **Cleaning** removes what carries no tone and leaves the words as they are, since
# case and punctuation carry tone in a headline.

# %%
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


made_up = [
    "Gold &amp; Silver   Rise As Dollar Slips (UPDATED)",
    "Analyst Praises Example Corp (NYSE:EXMP) After Earnings",
    "'Example Bank Cuts Its Forecast' - Example Wire",
]
display(pd.DataFrame({"as stored": made_up, "as cleaned": [clean_headline(h) for h in made_up]}))
evened = labelled["headline"].map(lambda h: " ".join(h.split()))
changed = (labelled["headline"].map(clean_headline) != evened).mean()
say(f"Cleaning changes more than white space in {changed:.1%} of the {len(labelled):,} headlines.")

# %% [markdown]
# **Inter-pass agreement.** A sample of the old headlines was labelled a second time,
# mixed among new ones so the labeller could not tell them apart (`first` and `second`
# in the data). Cohen's kappa is agreement beyond what two labellers would reach by
# chance: 1 is full agreement, 0 is chance.


# %%
def cohen_kappa(first: list[str], second: list[str]) -> float:
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    by_chance = sum((first.count(label) / n) * (second.count(label) / n) for label in LABELS)
    return (observed - by_chance) / (1 - by_chance)


twice = labelled.dropna(subset=["second"])
agreement = pd.DataFrame(
    {
        name: {
            "headlines": len(part),
            "agreement": (part["first"] == part["second"]).mean(),
            "kappa": cohen_kappa(part["first"].tolist(), part["second"].tolist()),
        }
        for name, part in [*twice.groupby("market"), ("all", twice)]
    }
).T
display(agreement)
grid = pd.crosstab(pd.Categorical(twice["first"], LABELS), pd.Categorical(twice["second"], LABELS))
display(grid.rename_axis(index="first pass", columns="second pass"))
caption(f"Two labelling passes on {len(twice)} headlines ({window(twice)}); per market, then as a grid.")

# %%
share = float(agreement.loc["all", "agreement"])
low, high = share, float(np.sqrt(share))
opposite = (grid.loc["positive", "negative"] + grid.loc["negative", "positive"]) / len(twice)
say(
    f"**What this bounds.** Inter-pass agreement is {share:.1%} (kappa "
    f"{agreement.loc['all', 'kappa']:.2f}). The best accuracy any model can reach on these labels "
    f"lies between **{low:.1%}** and **{high:.1%}**:"
)
say(
    f"- *Lower end, the agreement itself ({low:.1%})*: if every disagreement is a headline with "
    "no single right label, nothing can match the label on it more often than the two passes "
    "match each other."
)
say(
    f"- *Upper end, the square root of the agreement (√{share:.3f} = {high:.1%})*: if every "
    "headline has one right label and each pass misses it independently with the same chance, "
    "two passes agree when both are right, so agreement = accuracy × accuracy."
)
say(
    "A third pass is needed to tell which case holds. The two passes gave opposite tones on "
    f"{opposite:.1%} of headlines; the rest of the disagreement is between neutral and a tone. "
    "Where the passes differ, training counts the headline half for each label, and scoring uses "
    "the second pass, written under the same rule as the test set."
)


def shares(frame: pd.DataFrame) -> np.ndarray:
    """What a model is trained towards: per headline, a share for each label.

    One labelling pass gives its label everything; two that differ give half each.
    """
    out = np.zeros((len(frame), len(LABELS)))
    second = frame["second"].fillna(frame["first"])
    for given in (frame["first"], second):
        out[np.arange(len(frame)), [LABELS.index(label) for label in given]] += 0.5
    return out


# %% [markdown]
# ## 4. Splits
#
# *How is the data divided so that no score is flattered by something the model has seen?*
#
# The split is **by time, never at random**: a model is always scored on headlines
# later than all it was trained on, which is how it is used. Choices are made on
# **walk-forward blocks**: the last stretches of validation headlines, each scored by a
# model trained only on what came before it. The test set comes after all of them.

# %%
BLOCK, BLOCKS = 300, 3


def walk_forward(frame: pd.DataFrame) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """(train on, validate on) for each block; `frame` is in time order."""
    starts = [len(frame) - BLOCK * (BLOCKS - k) for k in range(BLOCKS)]
    return [(frame.iloc[:start], frame.iloc[start : start + BLOCK]) for start in starts]


blocks = walk_forward(labelled)
fig, ax = plt.subplots(figsize=(10, 2.3))
rows = [(f"block {i + 1}", train, validation) for i, (train, validation) in enumerate(blocks)]
for row, (name, train, validation) in enumerate(rows):
    for part, shade in ((train, MUTED), (validation, ACCENT)):
        start = part["created_at"].min()
        ax.barh(row, (part["created_at"].max() - start).days, left=start.tz_localize(None), color=shade, height=0.6)
ax.barh(len(rows), (test["created_at"].max() - test["created_at"].min()).days,
        left=test["created_at"].min().tz_localize(None), color=INK, height=0.6)  # fmt: skip
ax.set_yticks(range(len(rows) + 1), [name for name, _, _ in rows] + ["test"])
ax.invert_yaxis()
ax.set(title="Grey: trained on. Blue: validated on. Black: the test set")
plt.show()
display(
    pd.DataFrame(
        {
            name: {
                "trained on": len(train),
                "training to": f"{train['created_at'].max():%Y-%m-%d}",
                "validated on": len(validation),
                "validation": window(validation),
                **validation["sentiment"].value_counts(normalize=True).reindex(LABELS).round(2).to_dict(),
            }
            for name, train, validation in rows
        }
    ).T
)
caption(
    f"{BLOCKS} walk-forward blocks of {BLOCK} validation headlines, and the test set of {len(test)} "
    f"({window(test)}). The last columns are each validation part's label mix."
)

# %%
test_keys, train_keys = set(test["headline"].map(headline_key)), set(labelled["headline"].map(headline_key))
guards = {
    "articles in both training and test": len(set(labelled["article_id"]) & set(test["article_id"])),
    "near-copies in both training and test": len(train_keys & test_keys),
    "near-copies appearing twice in training": int(labelled["headline"].map(headline_key).duplicated().sum()),
    "training headlines dated inside the test period": int((labelled["created_at"] >= TEST_FROM).sum()),
    "test headlines dated before the test period": int((test["created_at"] < TEST_FROM).sum()),
    "rows out of time order in training": int((labelled["created_at"].diff().dt.total_seconds() < 0).sum()),
    "blocks whose training part reaches past their validation part": sum(
        train["created_at"].max() > validation["created_at"].min() for train, validation in blocks
    ),
}
display(pd.Series(guards, name="count").to_frame())
say(
    f"**Found.** {sum(v == 0 for v in guards.values())} of {len(guards)} leakage guards count zero. "
    f"The test period starts on {TEST_FROM:%Y-%m-%d}. The label mix differs between blocks (table "
    "above), so a model is asked to work on news that does not look like its training news."
)
if any(guards.values()):
    raise ValueError("A leakage guard is not zero: stop here")

# %% [markdown]
# ## 5. Features
#
# *What text does the model read?*
#
# A language model reads text directly, so the features are which text it is given.
# Stored summaries are cut at a fixed length, often mid-sentence, so only a summary's
# whole sentences are used.

# %%
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


def model_text(headline: str, summary: str, market: str, *, with_asset: bool, with_summary: bool) -> str:
    text = clean_headline(headline)
    if with_summary:
        extra = whole_sentences(summary)
        if extra and headline_key(extra) != headline_key(text):
            text = f"{text if text.endswith(('.', '!', '?')) else text + '.'} {extra}"
    return f"{market}: {text}" if with_asset and market else text


def texts(frame: pd.DataFrame, option: str) -> list[str]:
    return [
        model_text(str(h), str(s or ""), str(m), **TEXTS[option])
        for h, s, m in zip(frame["headline"], frame["summary"], frame["market"])
    ]


sample = ("Gold Rises", "Bullion gained on the day. Analysts said the move could", "Gold")
display(
    pd.Series({name: model_text(*sample, **parts) for name, parts in TEXTS.items()}, name="what the model reads").to_frame()
)
caption(f"The {len(TEXTS)} input-text options on one made-up headline and summary.")

# %%
MAX_TOKENS = 256
ROBERTA = "cardiffnlp/twitter-roberta-base-sentiment-latest"
counter = AutoTokenizer.from_pretrained(ROBERTA)
lengths = pd.DataFrame({name: [len(ids) for ids in counter(texts(labelled, name))["input_ids"]] for name in TEXTS})
ax = lengths.plot.box(vert=False, figsize=(9, 2.2), color=INK)
ax.axvline(MAX_TOKENS, color=BAD, ls="--", lw=0.9)
ax.set(title=f"Length in tokens of each input (red: the {MAX_TOKENS}-token limit)", xlabel="tokens")
plt.show()
display(lengths.describe().loc[["50%", "max"]].T.assign(cut_off=(lengths > MAX_TOKENS).mean()))
caption(f"Token counts for the {len(labelled):,} training and validation headlines; `cut_off` is the share over the limit.")
say(
    f"**Found.** The longest input is {int(lengths.max().max())} tokens against a limit of "
    f"{MAX_TOKENS}, and {(lengths > MAX_TOKENS).mean().max():.1%} of inputs at most are cut. "
    f"Adding the summary raises the median from {lengths['headline'].median():.0f} to "
    f"{lengths['headline + summary'].median():.0f} tokens."
)

# %% [markdown]
# ## 6. Model selection
#
# *Which input text, which base model, and which training settings?*
#
# ### The training function
#
# "Fine-tuning" means taking a language model already trained on a great deal of text
# and training it a little further on our headlines. One function does it:
#
# 1. show the model the training headlines in batches, in a random order fixed by the seed;
# 2. after each pass, measure loss on the validation headlines;
# 3. **keep the weights from the pass with the lowest validation loss**, and stop once
#    it has not improved for `early_stopping_patience` passes. This is the guard
#    against overfitting.
#
# | Setting | What it controls |
# |---|---|
# | learning rate | How big a change each batch makes |
# | layer decay | Under 1, lower layers (general language) change less than upper ones |
# | dropout | Share of the model switched off at random while training, so it cannot lean on any one part |
# | weight decay | Pulls the model's numbers towards zero |
# | label smoothing | Trains towards "mostly this label" instead of "certainly this label" |
#
# The last three are the standard guards against overfitting.


# %%
SAME_LABEL = {"bearish": "negative", "bullish": "positive"}


def free() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def label_order(model_name: str) -> list[str] | None:
    """The label order to give a base model whose own labels are not ours (None: keep its own)."""
    own = AutoConfig.from_pretrained(model_name).id2label
    plain = [own[i].lower() for i in sorted(own)]
    names = [SAME_LABEL.get(name, name) for name in plain]
    if sorted(names) != sorted(LABELS):
        return LABELS  # no usable classification head: a new one is trained
    return None if names == plain else names


def layer_rates(model, rate: float, weight_decay: float, decay: float) -> list[dict]:
    """A learning rate per parameter: each layer down gets `decay` times the one above."""
    named = list(model.named_parameters())
    depth = [int(n.split("encoder.layer.")[1].split(".")[0]) if "encoder.layer." in n else None for n, _ in named]
    top = max(d for d in depth if d is not None) + 1
    groups = []
    for (name, parameter), d in zip(named, depth):
        down = top - d if d is not None else top + 1 if "embeddings" in name else 0
        no_decay = "bias" in name or "LayerNorm.weight" in name
        groups.append({"params": [parameter], "lr": rate * decay**down, "weight_decay": 0.0 if no_decay else weight_decay})
    return groups


def fine_tune(
    train_texts: list[str],
    targets: np.ndarray,
    validation_texts: list[str],
    validation_labels: list[str],
    out_dir: Path,
    *,
    model_name: str,
    seed: int,
    epochs: int = 8,
    early_stopping_patience: int = 2,
    learning_rate: float = 2e-5,
    layer_wise_lr_decay: float = 1.0,
    dropout: float | None = None,
    weight_decay: float = 0.01,
    label_smoothing: float = 0.0,
    batch_size: int = 16,
    warmup_share: float = 0.1,
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
    extra = {} if dropout is None else {"hidden_dropout_prob": dropout, "attention_probs_dropout_prob": dropout}
    names = label_order(model_name)
    if names is not None:
        extra |= {"num_labels": len(names), "id2label": dict(enumerate(names)),
                  "label2id": {name: i for i, name in enumerate(names)}, "ignore_mismatched_sizes": True}  # fmt: skip
    # .float(): a model stored in half precision cannot be trained (its loss turns into
    # "not a number" after one step). For a model already in full precision it changes nothing.
    model = AutoModelForSequenceClassification.from_pretrained(model_name, **extra).float().to(DEVICE)
    order = [SAME_LABEL.get(model.config.id2label[i].lower(), model.config.id2label[i].lower()) for i in range(len(LABELS))]

    def encode(batch: list[str]) -> dict:
        return dict(tokenizer(batch, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt"))

    wanted_all = torch.tensor(np.asarray(targets, dtype=float)[:, [LABELS.index(n) for n in order]], dtype=torch.float)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    plain_loss = torch.nn.CrossEntropyLoss()  # validation loss never includes the smoothing
    parameters = (
        layer_rates(model, learning_rate, weight_decay, layer_wise_lr_decay)
        if layer_wise_lr_decay < 1.0
        else model.parameters()
    )
    optimiser = torch.optim.AdamW(parameters, lr=learning_rate, weight_decay=weight_decay)
    steps = epochs * int(np.ceil(len(train_texts) / batch_size))
    schedule = get_linear_schedule_with_warmup(optimiser, int(warmup_share * steps), steps)
    rng = np.random.default_rng(seed)
    truth = torch.tensor([order.index(label) for label in validation_labels])
    history, best, waited = [], np.inf, 0
    for epoch in range(1, epochs + 1):
        model.train()
        shuffled, total = rng.permutation(len(train_texts)), 0.0
        for start in range(0, len(shuffled), batch_size):
            rows = shuffled[start : start + batch_size]
            batch = {k: v.to(DEVICE) for k, v in encode([train_texts[i] for i in rows]).items()}
            loss = loss_fn(model(**batch).logits, wanted_all[rows].to(DEVICE))
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
        validation_loss = float(plain_loss(logits, truth))
        if not np.isfinite(validation_loss):
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


def predict(model_dir: Path | str, inputs: list[str]) -> np.ndarray:
    """Probabilities for each text, columns in LABELS order, from a saved or downloaded model."""
    where = str(model_dir).replace("\\", "/")
    tokenizer = AutoTokenizer.from_pretrained(where)
    model = AutoModelForSequenceClassification.from_pretrained(where).float().to(DEVICE)
    model.eval()
    own = [SAME_LABEL.get(model.config.id2label[i].lower(), model.config.id2label[i].lower()) for i in range(len(LABELS))]
    out = []
    with torch.no_grad():
        for start in range(0, len(inputs), 64):
            batch = tokenizer(inputs[start : start + 64], padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            logits = model(**{k: v.to(DEVICE) for k, v in batch.items()}).logits
            out.append(torch.softmax(logits, dim=-1)[:, [own.index(label) for label in LABELS]].cpu().numpy())
    del model
    free()
    return np.concatenate(out)


# %% [markdown]
# ### One stored run
#
# `run` trains one model and stores what it said about the validation headlines, under a
# name made from everything that went in (which headlines, which text, which model,
# which settings, which seed). Asking for the same run again reads the stored answer.


# %%
def run_name(*parts) -> str:
    written = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha1(written, usedforsecurity=False).hexdigest()[:10]


def run(train, validation, *, text, model, settings, seed, added=None, also=None, keep_model=None) -> dict:
    """Train one model, or read it back. `added`: extra rows with `text` and `sentiment`.

    `also`: further lists of texts to score with the kept model. The model's files are
    deleted afterwards unless `keep_model` says where to keep them.
    """
    name = run_name(list(train["article_id"]), list(validation["article_id"]), text, model, settings, seed,
                    None if added is None else list(added["text"]))  # fmt: skip
    folder = WORK / "runs" / name
    wanted = ["validation", *(also or {})]
    if not ((folder / "training.json").is_file() and all((folder / f"{k}.npy").is_file() for k in wanted)):
        folder.mkdir(parents=True, exist_ok=True)
        print(f"training {name}: {model}, seed {seed}, {len(train)} headlines", flush=True)
        model_dir = keep_model or Path(tempfile.mkdtemp(prefix="tone_"))
        train_texts, targets = texts(train, text), shares(train)
        if added is not None and len(added):
            one_hot = np.zeros((len(added), len(LABELS)))
            one_hot[np.arange(len(added)), [LABELS.index(label) for label in added["sentiment"]]] = 1.0
            train_texts, targets = train_texts + added["text"].tolist(), np.vstack([targets, one_hot])
        validation_texts = texts(validation, text)
        result = fine_tune(train_texts, targets, validation_texts, validation["sentiment"].tolist(),
                           model_dir, model_name=model, seed=seed, **settings)  # fmt: skip
        np.save(folder / "validation.npy", predict(model_dir, validation_texts))
        for key, inputs in (also or {}).items():
            np.save(folder / f"{key}.npy", predict(model_dir, inputs))
        if keep_model is None:
            shutil.rmtree(model_dir, ignore_errors=True)
        (folder / "training.json").write_text(json.dumps(result))
    out = {"name": name, "training": json.loads((folder / "training.json").read_text())}
    for key in wanted:
        out[key] = np.load(folder / f"{key}.npy")
    return out


CHOICE_SEEDS = (13, 17)
START = {"epochs": 8, "early_stopping_patience": 2, "learning_rate": 2e-5, "layer_wise_lr_decay": 1.0,
         "dropout": None, "weight_decay": 0.01, "label_smoothing": 0.0}  # fmt: skip


def on_blocks(*, text: str, model: str, settings: dict) -> dict:
    """One candidate, trained on every block with every choice seed: its means and each run."""
    rows = []
    for number, (train, validation) in enumerate(blocks, start=1):
        for seed in CHOICE_SEEDS:
            got = run(train, validation, text=text, model=model, settings=settings, seed=seed)
            passes = got["training"]["epochs"]
            kept = next(p for p in passes if p["epoch"] == got["training"]["best_epoch"])
            rows.append({"block": number, "seed": seed, **measure(validation["sentiment"].tolist(), got["validation"]),
                         "passes": len(passes), "kept": kept["epoch"], "training_loss": kept["train_loss"]})  # fmt: skip
    frame = pd.DataFrame(rows)
    return {"loss": float(frame["loss"].mean()), "accuracy": float(frame["accuracy"].mean()),
            "macro_f1": float(frame["macro_f1"].mean()), "training_loss": float(frame["training_loss"].mean()), "runs": rows}  # fmt: skip


def choose(file: str, candidates: dict[str, dict]) -> dict:
    """Train every candidate on the blocks (or read it back); the lowest mean loss wins."""
    found = stored(file)
    if found is None:
        options = {name: on_blocks(**arguments) for name, arguments in candidates.items()}
        found = store(file, {"options": options, "winner": min(options, key=lambda n: options[n]["loss"])})
    return found


# %% [markdown]
# ### Baselines: what a model has to beat
#
# Three answers that need no training here: always the commonest label; plain FinBERT
# as downloaded; and the model in the app today (`finbert-radar-1`: FinBERT trained
# further on an earlier, smaller set of these headlines, all dated before block 1's
# validation part). The last two read what they read in the app: headline plus summary.


# %%
def app_text(frame: pd.DataFrame) -> list[str]:
    """The text the app's model is given: the headline, then the summary if it adds anything."""
    out = []
    for headline, summary in zip(frame["headline"], frame["summary"]):
        headline, summary = " ".join(str(headline).split()), " ".join(str(summary or "").split())
        if not summary or summary == headline:
            out.append(headline[:2000])
        else:
            out.append(f"{headline if headline.endswith(('.', '!', '?')) else headline + '.'} {summary}"[:2000])
    return out


def baselines() -> dict:
    found = stored("baselines")
    if found is None:
        existing = {"plain FinBERT, not trained further": "ProsusAI/finbert"}
        if IN_USE.is_dir():
            existing["finbert-radar-1 (in the app)"] = IN_USE
        found = {
            name: {"blocks": [{"block": i, **measure(v["sentiment"].tolist(), predict(model, app_text(v)))}
                              for i, (_, v) in enumerate(blocks, start=1)]}  # fmt: skip
            for name, model in existing.items()
        }
        store("baselines", found)
    return found


def baseline_rows() -> pd.DataFrame:
    always = []
    for train, validation in blocks:
        mix = train["sentiment"].value_counts(normalize=True).reindex(LABELS).fillna(0.0)
        truth = validation["sentiment"].tolist()
        always.append({"loss": log_loss(truth, np.tile(mix.to_numpy(), (len(truth), 1))),
                       "accuracy": float(np.mean([label == mix.idxmax() for label in truth]))})  # fmt: skip
    rows = {"baseline: always the commonest label": pd.DataFrame(always).mean().to_dict()}
    for name, scores in baselines().items():
        rows[f"baseline: {name}"] = pd.DataFrame(scores["blocks"])[["loss", "accuracy"]].mean().to_dict()
    return pd.DataFrame(rows).T.rename(columns={"loss": "validation loss"})


display(baseline_rows())
caption(
    f"Baselines: mean over the {BLOCKS} validation blocks of {BLOCK} headlines "
    f"({blocks[0][1]['created_at'].min():%Y-%m-%d} to {blocks[-1][1]['created_at'].max():%Y-%m-%d})."
)
if not IN_USE.is_dir():
    say(f"The model in the app: not available: {IN_USE.as_posix()}")

# %% [markdown]
# ### How a choice is read
#
# Each candidate is trained on every block with every choice seed. The table gives its
# mean and the spread between its runs. The **seed spread** is how far two seeds of the
# same candidate on the same block differ, on average: a lead smaller than that is
# called **no measurable difference**.
#
# **Validation figures lean optimistic.** In every run the validation headlines do two
# jobs: they pick which pass is kept, and they score the candidate. A score picked as
# the best of several passes is better than the same model would get on new headlines.
# The lean is the same for every candidate, so it does not favour one, but the level of
# every validation figure in this notebook is flattered.


# %%
VERDICTS: dict[str, dict] = {}


def show_choice(found: dict, what: str) -> None:
    """One choice: the candidates with their spread, the baselines, every run, and the verdict."""
    options = found["options"]
    table = pd.DataFrame(
        {
            name: {
                "validation loss": np.mean([r["loss"] for r in each["runs"]]),
                "loss spread (sd)": np.std([r["loss"] for r in each["runs"]], ddof=1),
                "accuracy": np.mean([r["accuracy"] for r in each["runs"]]),
                "accuracy spread (sd)": np.std([r["accuracy"] for r in each["runs"]], ddof=1),
                "training loss": each["training_loss"],
                "pass kept": np.mean([r["kept"] for r in each["runs"]]),
            }
            for name, each in options.items()
        }
    ).T.sort_values("validation loss")
    display(blank(pd.concat([table, baseline_rows()])))
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(table) + 1.1))
    for place, name in enumerate(table.index[::-1]):
        runs = [r["loss"] for r in options[name]["runs"]]
        ax.scatter(runs, [place] * len(runs), color=MUTED, s=14, zorder=2)
        ax.scatter([np.mean(runs)], [place], color=ACCENT, s=70, zorder=3)
    ax.set_yticks(range(len(table)), table.index[::-1])
    ax.set(title=f"{what}: validation loss, each run (grey) and the mean (blue)")
    ax.grid(axis="y", visible=False)
    plt.show()
    all_runs = pd.concat([pd.DataFrame(each["runs"]).assign(option=name) for name, each in options.items()])
    per_block = all_runs.groupby(["option", "block"])["loss"]
    seed_spread = float((per_block.max() - per_block.min()).mean())
    gap = float(table["validation loss"].iloc[1] - table["validation loss"].iloc[0])
    caption(
        f"{what}. Each candidate: {len(options[table.index[0]]['runs'])} runs ({BLOCKS} blocks × "
        f"{len(CHOICE_SEEDS)} seeds), {BLOCK} validation headlines a block. Baselines: mean of the blocks."
    )
    say(
        f"**Found.** Lowest validation loss: *{table.index[0]}*, ahead of *{table.index[1]}* by "
        f"{gap:.3f}. Seed spread is {seed_spread:.3f}, so this is "
        f"**{'a measurable difference' if gap > seed_spread else 'no measurable difference'}**. "
        "The lowest mean is taken either way."
    )
    VERDICTS[what] = {"chosen": table.index[0], "runner-up": table.index[1], "gap": gap, "seed spread": seed_spread}


# %% [markdown]
# ### Step 1: the input text
#
# Compared with one base model, the social-media RoBERTa, so the text chosen is the one
# that suited that model.

# %%
step1 = choose("step1_text", {name: {"text": name, "model": ROBERTA, "settings": START} for name in TEXTS})
TEXT = step1["winner"]
show_choice(step1, "Input text")

# %% [markdown]
# ### Step 2: the base model
#
# | Model | First trained on |
# |---|---|
# | RoBERTa (social media) | Social-media posts, then the tone of posts |
# | FinBERT | Financial news sentences and their tone |
# | DeBERTa-v3 | General text; a newer design, with no tone training |
# | DeBERTa-v3 (finance) | The same, then the tone of financial sentences |

# %%
MODELS = {
    "RoBERTa (social media)": ROBERTA,
    "FinBERT": "ProsusAI/finbert",
    "DeBERTa-v3": "microsoft/deberta-v3-base",
    "DeBERTa-v3 (finance)": "nickmuchi/deberta-v3-base-finetuned-finance-text-classification",
}
configs = {name: AutoConfig.from_pretrained(model) for name, model in MODELS.items()}
display(
    pd.DataFrame(
        {
            name: {"model": MODELS[name], "dropout in the encoder": c.hidden_dropout_prob,
                   "dropout on attention": c.attention_probs_dropout_prob, "its own labels": list(c.id2label.values())}  # fmt: skip
            for name, c in configs.items()
        }
    ).T
)
caption(f"The {len(MODELS)} base models, read from their configurations. A dropout of `None` below means the value shown here.")

# %%
step2 = choose("step2_model", {name: {"text": TEXT, "model": model, "settings": START} for name, model in MODELS.items()})
MODEL_NAME, MODEL = step2["winner"], MODELS[step2["winner"]]
show_choice(step2, "Base model")

# %% [markdown]
# ### Step 3: the settings
#
# Three groups, in order; each is tried with everything else held at the winner so far.

# %%
SETTINGS = dict(START)
GROUPS = {
    "learning rate and layer decay": [
        {"learning_rate": rate, "layer_wise_lr_decay": decay} for rate in (1e-5, 2e-5, 3e-5) for decay in (1.0, 0.85)
    ],
    "dropout and weight decay": [{"dropout": drop, "weight_decay": decay} for drop in (None, 0.2) for decay in (0.01, 0.1)],
    "label smoothing": [{"label_smoothing": 0.0}, {"label_smoothing": 0.1}],
}


def settings_step(number: int, title: str) -> None:
    """Try one group of settings, show it, and carry the winner forward."""
    named = {", ".join(f"{k} {v}" for k, v in change.items()): change for change in GROUPS[title]}
    found = choose(
        f"step3_{number}",
        {name: {"text": TEXT, "model": MODEL, "settings": {**SETTINGS, **change}} for name, change in named.items()},
    )
    SETTINGS.update(named[found["winner"]])
    show_choice(found, f"Settings: {title}")


settings_step(1, "learning rate and layer decay")

# %%
settings_step(2, "dropout and weight decay")

# %%
settings_step(3, "label smoothing")
display(pd.Series(SETTINGS, name="value").to_frame())
caption("The settings every later stage uses.")

# %% [markdown]
# ## 7. Training diagnostics
#
# *Does the model overfit, and where does it start?*
#
# The chosen recipe is trained once per final seed on the last block, and the models'
# files are kept. Training loss is always below validation loss, so a gap between them
# is not by itself overfitting; the sign is **validation loss turning upwards** while
# training loss keeps falling.

# %%
FINAL_SEEDS = (13, 17, 23, 29, 31)
train, validation = blocks[-1]
truth = validation["sentiment"].tolist()
if not POOL.is_file():
    raise FileNotFoundError(f"{POOL} is missing: run backend/scripts/tone_export.py, or copy the file here")
pool = pd.read_csv(POOL, encoding="utf-8")
pool["created_at"] = pd.to_datetime(pool["created_at"], utc=True, format="ISO8601")
pool["summary"] = pool["summary"].fillna("")
pool["text"] = texts(pool, TEXT)


def five(stage: str, added=None, also=None) -> dict:
    """The chosen recipe on the last block, once per final seed; each model's files are kept."""
    runs = [
        run(train, validation, text=TEXT, model=MODEL, settings=SETTINGS, seed=seed, added=added, also=also,
            keep_model=KEPT_MODELS / stage / str(seed))  # fmt: skip
        for seed in FINAL_SEEDS
    ]
    out = {
        "passes": [r["training"]["epochs"] for r in runs],
        "kept": [r["training"]["best_epoch"] for r in runs],
        "single": [measure(truth, r["validation"]) for r in runs],
        "validation": np.mean([r["validation"] for r in runs], axis=0),
    }
    out["together"] = measure(truth, out["validation"])
    for key in also or {}:
        out[key] = np.mean([r[key] for r in runs], axis=0)
    return out


def show_curves(stage: dict, title: str) -> pd.DataFrame:
    fig, axes = plt.subplots(1, len(FINAL_SEEDS), figsize=(13, 2.8), sharey=True)
    rows = {}
    for ax, passes, kept, seed in zip(axes, stage["passes"], stage["kept"], FINAL_SEEDS):
        frame = pd.DataFrame(passes).set_index("epoch")
        ax.plot(frame.index, frame["train_loss"], marker="o", color=MUTED, label="training")
        ax.plot(frame.index, frame["validation_loss"], marker="o", color=ACCENT, label="validation")
        ax.axvline(kept, color=INK, ls="--", lw=0.9)
        ax.set(title=f"seed {seed}", xlabel="pass", xticks=frame.index)
        rows[f"seed {seed}"] = {
            "pass kept": kept,
            "passes run": len(passes),
            "validation loss, kept pass": frame.loc[kept, "validation_loss"],
            "validation loss, last pass": frame["validation_loss"].iloc[-1],
            "training loss, kept pass": frame.loc[kept, "train_loss"],
            "training loss, last pass": frame["train_loss"].iloc[-1],
        }
    axes[0].set_ylabel("loss")
    axes[0].legend()
    plt.show()
    caption(
        f"{title}: loss by pass for {len(FINAL_SEEDS)} seeds; {len(train):,} training headlines to "
        f"{train['created_at'].max():%Y-%m-%d}, {len(validation)} validation headlines ({window(validation)}). "
        "Dashed: the pass kept."
    )
    return pd.DataFrame(rows).T


plain = five("plain", also={"pool": pool["text"].tolist()})
curves = show_curves(plain, "Five models")
display(curves)

# %%
rise = curves["validation loss, last pass"] - curves["validation loss, kept pass"]
fall = curves["training loss, kept pass"] - curves["training loss, last pass"]
say(
    f"**Found.** Validation loss is lowest at pass {curves['pass kept'].astype(int).tolist()} for "
    f"the {len(curves)} seeds. In {int((rise > 0).sum())} of {len(curves)} runs it is higher at "
    f"the last pass run than at the kept pass, by {rise.mean():.3f} on average, while training "
    f"loss fell a further {fall.mean():.3f}: **overfitting starts at the pass after the kept one**, "
    "and those passes are thrown away. At the kept pass training loss is "
    f"{(curves['validation loss, kept pass'] - curves['training loss, kept pass']).mean():.3f} "
    f"below validation loss, and validation loss ({curves['validation loss, kept pass'].mean():.3f}) "
    f"is under the {KNOWS_NOTHING:.3f} of a model that has learned nothing, so it is not "
    "underfitting either. The kept pass is itself picked on these validation headlines, so its "
    "validation loss leans optimistic."
)

# %% [markdown]
# ## 8. Ensemble and self-training
#
# *Does averaging the seeds help, and does adding unlabelled articles help?*
#
# **Ensemble.** The probabilities of the final seeds are averaged. Averaging can never
# give a higher loss than the seeds have on average, but it is not guaranteed to beat
# the best single seed, so both are shown.
#
# **Self-training.** The averaged model labels a pool of stored articles nobody has
# labelled, drawn at random from the whole training period. Those it is sure enough
# about are added to the training headlines with the label it gave, and the seeds are
# trained again. The stage with the lower validation loss is kept.

# %%
SURE_IS_RIGHT, ADD_AT_MOST, DRAW_SEED = 0.80, 12_000, 20261010


def sure_from(labels: list[str], probabilities: np.ndarray) -> float | None:
    """The lowest confidence at which the headlines kept are right SURE_IS_RIGHT of the time.

    None when no confidence that keeps at least a fifth of the headlines reaches it.
    """
    confidence = probabilities.max(axis=1)
    right = np.array(answers(probabilities)) == np.array(labels)
    for level in np.sort(np.unique(confidence)):
        kept = confidence >= level
        if kept.mean() < 0.2:
            return None
        if right[kept].mean() >= SURE_IS_RIGHT:
            return float(level)
    return None


level = sure_from(truth, plain["validation"])
added = pool.iloc[0:0].assign(sentiment=[])
if level is not None:
    sure = pool.assign(sentiment=answers(plain["pool"]))[plain["pool"].max(axis=1) >= level]
    rng, parts = np.random.default_rng(DRAW_SEED), []
    for label, share_of in train["sentiment"].value_counts(normalize=True).items():
        part = sure[sure["sentiment"] == label]
        parts.append(part.iloc[rng.choice(len(part), size=min(len(part), int(ADD_AT_MOST * share_of)), replace=False)])
    added = pd.concat(parts).sort_values("article_id")
fig, ax = plt.subplots(figsize=(9, 2.2))
ax.hist(pool["created_at"].dt.year, bins=range(2015, 2028), color=MUTED, label="pool")
if len(added):
    ax.hist(added["created_at"].dt.year, bins=range(2015, 2028), color=ACCENT, label="added")
ax.set(title="The unlabelled pool by year, and what was added from it")
ax.legend()
plt.show()
say(
    f"**Pool.** {len(pool):,} unlabelled articles, {window(pool)}, none newer than the newest "
    f"training headline ({train['created_at'].max():%Y-%m-%d}). Confidence level for \"sure\": "
    f"{'none qualified' if level is None else f'{level:.3f}'} (the lowest at which the validation "
    f"headlines kept are right {SURE_IS_RIGHT:.0%} of the time while keeping at least a fifth of them). "
    f"Pseudo-labels added: **{len(added):,}** {added['sentiment'].value_counts().to_dict()}."
)

# %%
stages = {"five models": plain}
if len(added):
    stages["five models, self-trained"] = five("self", added=added)
    display(show_curves(stages["five models, self-trained"], "Five models, self-trained"))
KEPT = min(stages, key=lambda name: stages[name]["together"]["loss"])
rows = {}
for name, stage in stages.items():
    single = pd.DataFrame(stage["single"])
    rows[f"{name}: one seed, mean of five"] = {
        "validation loss": single["loss"].mean(), "loss spread (sd)": single["loss"].std(),
        "accuracy": single["accuracy"].mean(), "accuracy spread (sd)": single["accuracy"].std(),
        "best seed, accuracy": single["accuracy"].max(), "worst seed, accuracy": single["accuracy"].min(),
    }  # fmt: skip
    rows[f"{name}: averaged"] = {"validation loss": stage["together"]["loss"], "accuracy": stage["together"]["accuracy"]}
display(blank(pd.DataFrame(rows).T))
caption(f"Last validation block: {len(validation)} headlines ({window(validation)}). Seeds {list(FINAL_SEEDS)}.")
one, together = stages[KEPT]["single"], stages[KEPT]["together"]
say(
    f"**Found.** Kept: *{KEPT}*. Averaged, its accuracy is {together['accuracy']:.1%} against "
    f"{np.mean([s['accuracy'] for s in one]):.1%} for one seed on average (best seed "
    f"{max(s['accuracy'] for s in one):.1%}, worst {min(s['accuracy'] for s in one):.1%}); its loss "
    f"is {together['loss']:.3f} against {np.mean([s['loss'] for s in one]):.3f}."
)

# %% [markdown]
# ## 9. Calibration
#
# *When the model says how sure it is, is it right that often?*
#
# One number, a temperature, divides the model's scores before they become
# probabilities. It changes no answer, only how sure the model says it is. It is fitted
# on the last validation block and scored on the same block, so the improvement shown
# here is the most favourable case.


# %%
def with_temperature(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / temperature
    scaled = np.exp(logits - logits.max(axis=1, keepdims=True))
    return scaled / scaled.sum(axis=1, keepdims=True)


def reliability(labels: list[str], probabilities: np.ndarray) -> pd.DataFrame:
    """Headlines grouped by stated confidence, with how often each group was right."""
    frame = pd.DataFrame(
        {"said": probabilities.max(axis=1), "right": np.array(answers(probabilities)) == np.array(labels)}
    )
    frame["group"] = pd.cut(frame["said"], [1 / 3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], include_lowest=True)
    grouped = frame.groupby("group", observed=True)
    return pd.DataFrame({"headlines": grouped.size(), "said": grouped["said"].mean(), "right": grouped["right"].mean()})


def calibration_gap(labels: list[str], probabilities: np.ndarray) -> float:
    table = reliability(labels, probabilities)
    return float((table["headlines"] / table["headlines"].sum() * (table["said"] - table["right"]).abs()).sum())


before = stages[KEPT]["validation"]
tried = np.arange(0.5, 5.0001, 0.05)
TEMPERATURE = float(tried[int(np.argmin([log_loss(truth, with_temperature(before, t)) for t in tried]))])
after = with_temperature(before, TEMPERATURE)
fig, ax = plt.subplots(figsize=(4.8, 3.6))
ax.plot([1 / 3, 1], [1 / 3, 1], color=MUTED, ls="--", label="perfectly calibrated")
for name, given, shade in (("before", before, INK), ("after", after, ACCENT)):
    table = reliability(truth, given)
    ax.plot(table["said"], table["right"], marker="o", color=shade, label=name)
ax.set(xlabel="how sure it said it was", ylabel="how often it was right")
ax.legend()
plt.show()
display(reliability(truth, after))
caption(f"Reliability before and after the temperature, {len(truth)} validation headlines ({window(validation)}).")
say(
    f"**Found.** Temperature {TEMPERATURE:.2f}. The average distance between stated confidence and "
    f"accuracy goes from {calibration_gap(truth, before):.3f} to {calibration_gap(truth, after):.3f}; "
    f"validation loss from {log_loss(truth, before):.3f} to {log_loss(truth, after):.3f}; accuracy is "
    f"unchanged at {measure(truth, after)['accuracy']:.1%}."
)
final = store(
    "final",
    {
        "choice": {"text": TEXT, "model_name": MODEL_NAME, "model": MODEL, "settings": SETTINGS},
        "kept": KEPT,
        "folder": "plain" if KEPT == "five models" else "self",
        "temperature": TEMPERATURE,
        "train": len(train),
        "validation": len(validation),
        "added": len(added),
        "validation_after": measure(truth, after),
    },
)

# %% [markdown]
# ## 10. Test results
#
# *How good is the kept model on headlines it never saw, against the two bars?*
#
# The test set holds headlines from the test period on, newer than anything trained or
# chosen on, labelled before any of these models existed. **This cell scores it only
# when `RUN_TEST` is True, and only once**: the result is stored and read back after
# that, so the test set cannot be used to try something else.
#
# Because validation figures lean optimistic (sections 6, 7 and 9), the distance from
# validation to test is wider than it would be against an untouched validation set.
# That makes the "not overfitted" bar harder to pass, not easier.

# %%
result = stored("test")
if result is None and RUN_TEST:
    labels_test = test["sentiment"].tolist()
    folder = KEPT_MODELS / final["folder"]
    new = with_temperature(
        np.mean([predict(folder / str(seed), texts(test, TEXT)) for seed in FINAL_SEEDS], axis=0), TEMPERATURE
    )
    said_by = {"new": answers(new)}
    scores = {"new": measure(labels_test, new)}
    if IN_USE.is_dir():
        in_use = predict(IN_USE, app_text(test))
        said_by["in use"], scores["in use"] = answers(in_use), measure(labels_test, in_use)
    for score in scores.values():
        score["from"], score["to"] = wilson(score["accuracy"], len(test))
    check = mcnemar(labels_test, said_by["in use"], said_by["new"]) if "in use" in said_by else None
    gap = final["validation_after"]["accuracy"] - scores["new"]["accuracy"]
    loss_gap = scores["new"]["loss"] - final["validation_after"]["loss"]
    better = None
    if check is not None:
        better = bool(scores["new"]["accuracy"] > scores["in use"]["accuracy"] and check["p_value"] < P_BELOW)
    result = store(
        "test",
        {
            "headlines": len(test),
            "from": str(test["created_at"].min()),
            "to": str(test["created_at"].max()),
            "scores": scores,
            "comparison": check,
            "table": pd.crosstab(
                pd.Categorical(labels_test, LABELS), pd.Categorical(said_by["new"], LABELS), dropna=False
            ).to_numpy().tolist(),
            "by_market": {
                market: {
                    "headlines": len(part),
                    **{name: float(np.mean([said[i] == labels_test[i] for i in part.index])) for name, said in said_by.items()},
                }
                for market, part in test.groupby("market")
            },
            "validation": final["validation_after"],
            "accuracy_gap": gap,
            "loss_gap": loss_gap,
            "bars": {
                "better than the model in use": better,
                "not overfitted": bool(gap <= ACCURACY_GAP and loss_gap <= LOSS_GAP),
            },
        },
    )

if result is None:
    say(
        f"Test results: not available: {(WORK / 'test.json').as_posix()}. "
        "Set `RUN_TEST = True` in the first cell and run this cell."
    )
else:
    per_label = np.array(result["table"]).sum(axis=1)
    rows = {"baseline: always the commonest label": {"accuracy": per_label.max() / per_label.sum()}}
    for key, shown in (("in use", "finbert-radar-1 (in the app)"), ("new", "the new model")):
        if key in result["scores"]:
            s = result["scores"][key]
            rows[shown] = {"accuracy": s["accuracy"], "95% from": s["from"], "95% to": s["to"],
                           "loss": s["loss"], "macro F1": s["macro_f1"]}  # fmt: skip
    display(blank(pd.DataFrame(rows).T))
    caption(
        f"Test set: {result['headlines']} headlines, {result['from'][:10]} to {result['to'][:10]}. "
        "95% range: Wilson interval."
    )
    new_score = result["scores"]["new"]
    if result["comparison"] is None:
        say(f"**Bar 1, better than the model in use.** not available: {IN_USE.as_posix()}")
    else:
        check, old = result["comparison"], result["scores"]["in use"]
        say(
            f"**Bar 1, better than the model in use.** Accuracy {new_score['accuracy']:.1%} against "
            f"{old['accuracy']:.1%}. Only the new model was right on {check['only_second_right']} headlines "
            f"and only the model in use on {check['only_first_right']}; McNemar p = {check['p_value']:.2g} "
            f"(bar: below {P_BELOW}). **{'Pass' if result['bars']['better than the model in use'] else 'Fail'}.**"
        )
    say(
        f"**Bar 2, not overfitted.** Validation accuracy {result['validation']['accuracy']:.1%}, test "
        f"accuracy {new_score['accuracy']:.1%}: a gap of {result['accuracy_gap'] * 100:.1f} points (bar: at "
        f"most {ACCURACY_GAP * 100:.0f}). Validation loss {result['validation']['loss']:.3f}, test loss "
        f"{new_score['loss']:.3f}: a gap of {result['loss_gap']:.3f} (bar: at most {LOSS_GAP:.2f}). "
        f"**{'Pass' if result['bars']['not overfitted'] else 'Fail'}.**"
    )
    say(
        f"Against the labels' own limit: test accuracy {new_score['accuracy']:.1%}; reachable range "
        f"{low:.1%} to {high:.1%} (section 3)."
    )
    display(
        pd.DataFrame(result["table"], index=LABELS, columns=LABELS).rename_axis(
            index="the label", columns="the new model said"
        )
    )
    display(pd.DataFrame(result["by_market"]).T)
    caption(f"Confusion matrix and accuracy by market, {result['headlines']} test headlines.")

# %% [markdown]
# ## 11. Error analysis
#
# *Where is the kept model wrong?* On the last validation block, so that the test set
# stays read once.

# %%
checked = pd.DataFrame(
    {"label": truth, "said": answers(after), "market": validation["market"].tolist(), "sure": after.max(axis=1)}
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
pairs["share of all errors"] = pairs["headlines"] / len(wrong)
display(pairs)
display(by_market.rename(columns={"size": "headlines", "mean": "accuracy"}))
caption(f"Last validation block, {len(checked)} headlines ({window(validation)}), {len(wrong)} of them wrong.")
(top_label, top_said), worst = pairs.index[0], by_market["mean"].idxmin()
tones = {"positive", "negative"}
backwards = float((checked["label"].isin(tones) & checked["said"].isin(tones) & ~checked["right"]).mean())
say(
    f"**Found.** The commonest error is *{top_label}* called *{top_said}* ({int(pairs['headlines'].iloc[0])} "
    f"headlines, {pairs['share of all errors'].iloc[0]:.0%} of errors). The opposite tone is given on "
    f"{backwards:.1%} of headlines. The weakest market is {worst} ({by_market.loc[worst, 'mean']:.1%} of "
    f"{int(by_market.loc[worst, 'size'])}). Wrong answers are less sure than right ones: mean confidence "
    f"{wrong['sure'].mean():.2f} against {checked.loc[checked['right'], 'sure'].mean():.2f}."
)

# %% [markdown]
# ## 12. Limitations and next steps
#
# *What should a reader not conclude from this?*

# %%
made = pd.DataFrame(VERDICTS).T
made["verdict"] = np.where(made["gap"] > made["seed spread"], "measurable", "no measurable difference")
display(made)
caption("Every choice made: the winner's lead in validation loss beside the seed spread.")
unclear = int((made["verdict"] == "no measurable difference").sum())
say("- **The labels are written by a model**, not a person. Scores here are agreement with that labeller.")
say(
    f"- **The labels limit the score.** Reachable accuracy lies between {low:.1%} and {high:.1%} "
    "(section 3). Narrowing that needs a third labelling pass; raising it needs firmer labels, for "
    "example keeping only headlines two passes agree on."
)
say(
    f"- **Seed noise is larger than most gaps between options.** In {unclear} of {len(made)} choices "
    "the winner's lead is smaller than the seed spread."
)
say(f"- **The training set is small**: {len(labelled):,} labelled headlines, and {BLOCK} in each validation block.")
say(f"- **Gold is thin**: {gold_test} test headlines.")
say(
    "- **Validation is used more than once** (to pick the pass, the candidate, the stage and the "
    "temperature), so validation figures lean optimistic. Only section 10 is untouched."
)
say(
    "- **Next steps.** No further model is tried on these labels (decision 102): each would be scored "
    "against the same inter-pass agreement. Tone describes the news around a holding; it drives no "
    "forecast and no alert."
)

# %% [markdown]
# ## 13. Reproducibility
#
# *How is every figure above produced again?* Run the notebook top to bottom with the
# two data files in place. The same steps exist as tested package code in
# `backend/src/radar/pipelines/tone.py`; the two use one naming of stored runs, so
# either can read what the other trained.

# %%
facts = {
    "work folder": WORK.as_posix(),
    "kept model files": (KEPT_MODELS / final["folder"]).as_posix(),
    "choice seeds": list(CHOICE_SEEDS),
    "final seeds": list(FINAL_SEEDS),
    "draw seed for pseudo-labels": DRAW_SEED,
    "test period starts": f"{TEST_FROM:%Y-%m-%d}",
    "blocks": f"{BLOCKS} of {BLOCK}",
    "input text": TEXT,
    "base model": MODEL,
    "settings": SETTINGS,
    "kept stage": KEPT,
    "temperature": TEMPERATURE,
    "training runs stored": len(list((WORK / "runs").glob("*/training.json"))),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
    "device": DEVICE,
}
display(pd.Series(facts, name="value").to_frame())
