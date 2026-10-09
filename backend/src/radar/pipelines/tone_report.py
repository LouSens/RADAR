"""Reading what the tone pipeline stored, as tables for notebook 04.

Nothing here trains a model, scores one, or writes a file. Every function reads the
labelled data handed to it or a file under `data/research/tone4/`, and returns `None`
when that file is not there, so the notebook can say "not available" and name it.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from radar.models import classification, dataset
from radar.pipelines import tone

LABELS = tone.LABELS
# The error (log loss) of a model that says one third for each label.
KNOWS_NOTHING = float(np.log(len(LABELS)))


def path(name: str) -> Path:
    return tone.OUT / f"{name}.json"


def stored(name: str) -> dict[str, Any] | None:
    """A step's stored result, or None when the step has not finished."""
    return tone._stored(name)


def not_available(name: str) -> str:
    return f"not available: {path(name).as_posix()}"


# --- data ---


def counts(data: tone.Data) -> dict[str, pd.DataFrame]:
    """How many headlines there are, cut three ways. The test set's labels are not read."""
    labelled = data.labelled
    year = labelled["created_at"].dt.year.rename("year")
    by_class = pd.crosstab(labelled["market"], labelled["sentiment"])[LABELS]
    by_class["all"] = by_class.sum(axis=1)
    by_class.loc["all"] = by_class.sum()
    month = data.test["created_at"].dt.strftime("%Y-%m").rename("month")
    return {
        "by market and label": by_class,
        "by year": pd.crosstab(year, labelled["market"]),
        "test by month": pd.crosstab(month, data.test["market"]),
    }


def agreement(data: tone.Data) -> pd.DataFrame:
    """Per market: how often two labelling passes agreed, and Cohen's kappa."""
    both = data.labelled.dropna(subset=["second"])
    rows = {}
    for market, part in [*both.groupby("market"), ("all", both)]:
        first, second = part["first"].tolist(), part["second"].tolist()
        rows[str(market)] = {
            "headlines": len(part),
            "agreement": float(np.mean([a == b for a, b in zip(first, second, strict=True)])),
            "kappa": classification.cohen_kappa(first, second, LABELS),
        }
    return pd.DataFrame(rows).T.astype({"headlines": int})


def agreement_grid(data: tone.Data) -> pd.DataFrame:
    """First pass (rows) against second pass (columns), in headlines."""
    both = data.labelled.dropna(subset=["second"])
    grid = pd.crosstab(
        pd.Categorical(both["first"], LABELS), pd.Categorical(both["second"], LABELS), dropna=False
    )
    return grid.rename_axis(index="first pass", columns="second pass")


def reachable(share: float) -> tuple[float, float]:
    """The range the best possible score lies in, given how often two passes agree.

    Lower end, `share`: every disagreement is a headline with no single right label, so
    nothing can be scored right on it more often than the passes agree.
    Upper end, `sqrt(share)`: every headline has one right label and each pass misses it
    independently, so two passes agree when both are right, with chance `a * a`; then
    `a = sqrt(share)`. (Two passes agreeing on the same wrong label is left out, which
    puts the true upper end slightly lower.)
    """
    return share, float(np.sqrt(share))


def near_copies(data: tone.Data) -> dict[str, int]:
    """Headline keys in each part, and how many headlines share a key with another."""
    out = {}
    for name, part in (("training and validation", data.labelled), ("test", data.test)):
        keys = part["headline"].map(dataset.headline_key)
        out[f"{name}: headlines"] = len(part)
        out[f"{name}: distinct keys"] = int(keys.nunique())
    return out


def dropout_defaults() -> pd.DataFrame:
    """The dropout each base model ships with, read from its own configuration."""
    from transformers import AutoConfig

    rows = {}
    for name, model in tone.MODELS.items():
        config = AutoConfig.from_pretrained(model)
        rows[name] = {
            "model": model,
            "inside the encoder": config.hidden_dropout_prob,
            "on attention": config.attention_probs_dropout_prob,
        }
    return pd.DataFrame(rows).T


# --- choices on the blocks ---


def _majority(data: tone.Data) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number, (train, validation) in enumerate(tone.blocks(data), start=1):
        mix = train["sentiment"].value_counts(normalize=True).reindex(LABELS).fillna(0.0)
        answer = str(mix.idxmax())
        truth = validation["sentiment"].tolist()
        given = np.tile(mix.to_numpy(dtype=float), (len(truth), 1))
        rows[f"block {number}"] = {
            "answer": answer,
            "accuracy": float(np.mean([label == answer for label in truth])),
            "loss": classification.log_loss(truth, given, LABELS),
        }
    rows["mean"] = {
        "answer": "",
        "accuracy": float(np.mean([row["accuracy"] for row in rows.values()])),
        "loss": float(np.mean([row["loss"] for row in rows.values()])),
    }
    return rows


def majority(data: tone.Data) -> pd.DataFrame:
    """Per block, the score of always answering the commonest training label.

    Its loss is that of always giving the training part's label mix as probabilities.
    """
    return pd.DataFrame(_majority(data)).T


def baseline_rows(data: tone.Data) -> pd.DataFrame:
    """Baselines on the three blocks, in the columns of `options`.

    The two FinBERT rows come from `baselines.json` and are absent until it exists.
    """
    always = _majority(data)["mean"]
    rows: dict[str, dict[str, float]] = {
        "baseline: always the commonest label": {
            "validation loss": always["loss"],
            "accuracy": always["accuracy"],
        }
    }
    found = stored("baselines")
    for name, scores in (found or {}).items():
        rows[f"baseline: {name}"] = {
            "validation loss": float(np.mean([block["loss"] for block in scores["blocks"]])),
            "accuracy": float(np.mean([block["accuracy"] for block in scores["blocks"]])),
        }
    return pd.DataFrame(rows).T


def options(found: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """One row per candidate: its mean over the six runs and the spread between them."""
    rows = {}
    for name, each in found.items():
        runs = pd.DataFrame(each["runs"])
        rows[name] = {
            "validation loss": runs["loss"].mean(),
            "spread (sd of runs)": runs["loss"].std(),
            "accuracy": runs["accuracy"].mean(),
            "accuracy spread": runs["accuracy"].std(),
            "training loss": runs["training_loss"].mean(),
            "pass kept": runs["kept"].mean(),
            "runs": len(runs),
        }
    return pd.DataFrame(rows).T.sort_values("validation loss").astype({"runs": int})


def seed_spread(found: dict[str, dict[str, Any]]) -> dict[str, float]:
    """How far two seeds of the same candidate on the same block typically differ.

    The mean absolute difference between the seeds, over every candidate and block.
    """
    runs = pd.concat(
        [pd.DataFrame(each["runs"]).assign(option=name) for name, each in found.items()]
    )
    grouped = runs.groupby(["option", "block"])[["loss", "accuracy"]]
    gaps = grouped.max() - grouped.min()
    return {"loss": float(gaps["loss"].mean()), "accuracy": float(gaps["accuracy"].mean())}


def difference(found: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The winner against the runner-up, and whether the gap is larger than seed spread."""
    table = options(found)
    spread = seed_spread(found)["loss"]
    gap = float(table["validation loss"].iloc[1] - table["validation loss"].iloc[0])
    return {
        "winner": str(table.index[0]),
        "runner_up": str(table.index[1]),
        "gap": gap,
        "seed_spread": spread,
        "measurable": bool(gap > spread),
    }


# --- the last block ---


def curves(final: dict[str, Any]) -> pd.DataFrame:
    """Per seed of the kept stage: which pass was kept, and the loss there and at the end."""
    stage = final["stages"][final["kept"]]
    rows = {}
    for seed, passes, kept in zip(tone.FINAL_SEEDS, stage["passes"], stage["kept"], strict=True):
        at = {p["epoch"]: p for p in passes}
        rows[f"seed {seed}"] = {
            "pass kept": kept,
            "passes run": len(passes),
            "validation loss, kept pass": at[kept]["validation_loss"],
            "validation loss, last pass": passes[-1]["validation_loss"],
            "training loss, kept pass": at[kept]["train_loss"],
            "training loss, last pass": passes[-1]["train_loss"],
        }
    return pd.DataFrame(rows).T.astype({"pass kept": int, "passes run": int})


def stages(final: dict[str, Any]) -> pd.DataFrame:
    """Single seeds beside the five averaged, for each stage, then with the temperature."""
    rows = {}
    for name, stage in final["stages"].items():
        single = pd.DataFrame(stage["single"])
        rows[f"{name}: one seed, mean of five"] = {
            "validation loss": single["loss"].mean(),
            "loss spread (sd)": single["loss"].std(),
            "accuracy": single["accuracy"].mean(),
            "accuracy spread (sd)": single["accuracy"].std(),
            "best seed, accuracy": single["accuracy"].max(),
            "worst seed, accuracy": single["accuracy"].min(),
        }
        rows[f"{name}: averaged"] = {
            "validation loss": stage["together"]["loss"],
            "accuracy": stage["together"]["accuracy"],
        }
    rows[f"{final['kept']}: averaged, with the temperature"] = {
        "validation loss": final["validation_after"]["loss"],
        "accuracy": final["validation_after"]["accuracy"],
    }
    return pd.DataFrame(rows).T


def validation_probabilities(
    data: tone.Data, final: dict[str, Any]
) -> tuple[list[str], np.ndarray, np.ndarray] | None:
    """Labels of the last block, and the kept model's probabilities before and after.

    Only the probabilities after the temperature are stored. Dividing by a temperature
    is undone by dividing by its inverse, which gives back the ones before.
    """
    file = tone.OUT / "validation_final.npy"
    if not file.is_file():
        return None
    after = np.load(file)
    before = classification.with_temperature(after, 1.0 / final["temperature"])
    _, validation = tone.blocks(data)[-1]
    return validation["sentiment"].tolist(), before, after


def reliability(truth: list[str], probabilities: np.ndarray) -> pd.DataFrame:
    """Headlines grouped by how sure the model said it was, with how often it was right."""
    said = probabilities.max(axis=1)
    right = np.array([LABELS[i] for i in probabilities.argmax(axis=1)]) == np.array(truth)
    edges = [1 / 3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    frame = pd.DataFrame(
        {"said": said, "right": right, "group": pd.cut(said, edges, include_lowest=True)}
    )
    grouped = frame.groupby("group", observed=True)
    table = pd.DataFrame(
        {
            "headlines": grouped["right"].size(),
            "said": grouped["said"].mean(),
            "right": grouped["right"].mean(),
        }
    )
    table.index.name = "how sure it said it was"
    return table


def calibration_gap(truth: list[str], probabilities: np.ndarray) -> float:
    """The average distance between "said" and "right", weighted by headlines (ECE)."""
    table = reliability(truth, probabilities)
    weights = table["headlines"] / table["headlines"].sum()
    return float((weights * (table["said"] - table["right"]).abs()).sum())


def validation_errors(data: tone.Data, final: dict[str, Any]) -> dict[str, pd.DataFrame] | None:
    """Where the kept model is wrong on the last block: by pair of labels, and by market."""
    found = validation_probabilities(data, final)
    if found is None:
        return None
    truth, _, after = found
    _, validation = tone.blocks(data)[-1]
    said = [LABELS[i] for i in after.argmax(axis=1)]
    frame = pd.DataFrame(
        {"label": truth, "said": said, "market": validation["market"].tolist()}
    ).assign(right=lambda f: f["label"] == f["said"])
    grid = pd.crosstab(
        pd.Categorical(frame["label"], LABELS), pd.Categorical(frame["said"], LABELS), dropna=False
    ).rename_axis(index="the label", columns="the model said")
    wrong = frame[~frame["right"]]
    pairs = (
        wrong.groupby(["label", "said"]).size().sort_values(ascending=False).rename("headlines")
    ).to_frame()
    pairs["share of all errors"] = pairs["headlines"] / max(len(wrong), 1)
    per_market = frame.groupby("market")["right"]
    by_market = pd.DataFrame({"headlines": per_market.size(), "accuracy": per_market.mean()})
    by_market["wrong"] = by_market["headlines"] - per_market.sum().astype(int)
    return {"grid": grid, "pairs": pairs, "by market": by_market}


# --- the test ---


def test_scores(test: dict[str, Any]) -> pd.DataFrame:
    """The models on the test set, with the baseline of always the commonest test label.

    The baseline is worked out from the stored table of labels against answers, so the
    labels themselves are not read here.
    """
    per_label = np.array(test["table"]).sum(axis=1)
    rows: dict[str, dict[str, float]] = {
        "baseline: always the commonest label": {"accuracy": per_label.max() / per_label.sum()}
    }
    for name, shown in (("in use", "finbert-radar-1 (in the app)"), ("new", "the new model")):
        score = test["scores"][name]
        rows[shown] = {
            "accuracy": score["accuracy"],
            "95% from": score["from"],
            "95% to": score["to"],
            "loss": score["loss"],
            "macro F1": score["macro_f1"],
        }
    return pd.DataFrame(rows).T


# --- small facts the notebook's sentences are built from ---


def window(frame: pd.DataFrame) -> str:
    """The first and last day a set of headlines covers."""
    if not len(frame):
        return "no headlines"
    return f"{frame['created_at'].min():%Y-%m-%d} to {frame['created_at'].max():%Y-%m-%d}"


def block_table(data: tone.Data) -> pd.DataFrame:
    """Each walk-forward block and the test set: how many headlines, and from when to when."""
    rows = {}
    for number, (train, validation) in enumerate(tone.blocks(data), start=1):
        rows[f"block {number}"] = {
            "trained on": len(train),
            "training from": train["created_at"].min(),
            "training to": train["created_at"].max(),
            "validated on": len(validation),
            "validation from": validation["created_at"].min(),
            "validation to": validation["created_at"].max(),
        }
    rows["test"] = {
        "validated on": len(data.test),
        "validation from": data.test["created_at"].min(),
        "validation to": data.test["created_at"].max(),
    }
    return pd.DataFrame(rows).T


def overfitting(final: dict[str, Any]) -> dict[str, Any]:
    """Across the kept stage's seeds: where validation loss was lowest and what came after."""
    table = curves(final)
    rise = table["validation loss, last pass"] - table["validation loss, kept pass"]
    fall = table["training loss, kept pass"] - table["training loss, last pass"]
    return {
        "seeds": len(table),
        "kept": table["pass kept"].tolist(),
        "stopped_after_kept": int((table["passes run"] > table["pass kept"]).sum()),
        "rising": int((rise > 0).sum()),
        "mean_rise": float(rise.mean()),
        "mean_training_fall": float(fall.mean()),
        "training_below_validation": float(
            (table["validation loss, kept pass"] - table["training loss, kept pass"]).mean()
        ),
    }


def comparisons(steps: dict[str, dict[str, dict[str, Any]] | None]) -> pd.DataFrame:
    """Every choice that has been made: the gap to the runner-up beside the seed spread."""
    rows = {}
    for name, found in steps.items():
        if found is None:
            continue
        verdict = difference(found)
        rows[name] = {
            "chosen": verdict["winner"],
            "runner-up": verdict["runner_up"],
            "gap in validation loss": verdict["gap"],
            "seed spread": verdict["seed_spread"],
            "verdict": "measurable" if verdict["measurable"] else "no measurable difference",
        }
    return pd.DataFrame(rows).T
