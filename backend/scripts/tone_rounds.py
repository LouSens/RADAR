"""Further rounds on tone accuracy: docs/DECISIONS.md 098.

    uv run python backend/scripts/tone_rounds.py            # rounds 2 and 3, resumable
    uv run python backend/scripts/tone_rounds.py --report   # the one last reading

Runs after `tone_experiment.py` has finished and its report has been read. Everything
is chosen on the validation part. The sealed tests are read once more, by `--report`,
for the candidate validation prefers. Writes under data/research/tone/ only.
"""

import argparse
import datetime
import itertools
import json
import shutil
from typing import Any

import numpy as np
import pandas as pd
import tone_experiment as base

from radar.models import classification, finetune, sentiment

OUT = base.OUT
SEEDS = base.SEEDS
LABELS = base.LABELS
# The families of model tried beside FinBERT, and whether each brings its own
# three-way head (if not, its labels are set in our order).
FAMILIES: dict[str, tuple[str, bool]] = {
    "deberta": ("microsoft/deberta-v3-base", False),
    "roberta": ("cardiffnlp/twitter-roberta-base-sentiment-latest", True),
}
# A round must add this much validation accuracy for the next one to run.
WORTH = 0.005
# Round 3: how many unlabelled articles are read, and how many at most are added.
POOL = 60_000
ADDED = 12_000
# No new model is started after this hour, local time.
LAST_HOUR = 7


def late() -> bool:
    now = datetime.datetime.now().astimezone()
    return LAST_HOUR <= now.hour < 20


def loadable(model: str) -> bool:
    """Whether the model's tokenizer loads with the packages already installed."""
    from transformers import AutoTokenizer

    try:
        AutoTokenizer.from_pretrained(model)
    except Exception:
        return False
    return True


def stored(prefix: str, part: str) -> np.ndarray:
    """What the five models of a family said about a part, averaged."""
    files = [OUT / "runs" / f"{prefix}-{seed}" / f"{part}.npy" for seed in SEEDS]
    out: np.ndarray = np.mean([np.load(f) for f in files], axis=0)
    return out


def together(prefixes: list[str], part: str) -> np.ndarray:
    """Families averaged, each counting once however many models it has."""
    out: np.ndarray = np.mean([stored(prefix, part) for prefix in prefixes], axis=0)
    return out


def best_of(families: dict[str, str], truth: list[str]) -> tuple[list[str], float]:
    """The set of families whose average is right most often on validation.

    Of two that tie, the smaller set wins.
    """
    found: list[tuple[float, int, list[str]]] = []
    for size in range(1, len(families) + 1):
        for names in itertools.combinations(families, size):
            said = together([families[name] for name in names], "validation")
            found.append((base.right(said, truth), -size, list(names)))
    score, _, chosen = max(found)
    return chosen, score


def round_two(log: dict[str, Any]) -> dict[str, str]:
    choices = json.loads((OUT / "choices.json").read_text())
    final = json.loads((OUT / "final_train.json").read_text())
    data = base.Data()
    truth = data.parts["validation"]["sentiment"].tolist()
    config = base.CONFIGS[choices["step1"]["chosen"]]
    families = {"finbert": final["prefix"]}
    first = base.right(stored(final["prefix"], "validation"), truth)
    left_out: dict[str, str] = {}
    for name, (model, has_head) in FAMILIES.items():
        if not loadable(model):
            left_out[name] = "its tokenizer needs a package that is not installed"
            continue
        if late():
            left_out[name] = "out of time"
            continue
        settings = {**config, "base_model": model}
        if not has_head:
            settings["label_names"] = LABELS
        for seed in SEEDS:
            base.run(
                f"r2-{name}-{seed}",
                data,
                final["texts"],
                final["labels"],
                settings,
                seed,
                keep=True,
            )
        families[name] = f"r2-{name}"
        alone = base.right(stored(f"r2-{name}", "validation"), truth)
        base.say(f"round 2, {name}: five together {alone:.3f}")
    names, score = best_of(families, truth)
    log["round2"] = {
        "round 1": first,
        "left out": left_out,
        "each family": {
            name: base.right(stored(prefix, "validation"), truth)
            for name, prefix in families.items()
        },
        "best": names,
        "best score": score,
        "gain": score - first,
    }
    base.say(f"round 2: best {names} at {score:.3f}, round 1 was {first:.3f}")
    return {name: families[name] for name in names}


def distil(
    name: str, data: base.Data, texts: list[str], wanted: np.ndarray, *, seed: int = 13
) -> None:
    """Train one FinBERT on the ensemble's probabilities, and store what it then says."""
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    folder = OUT / "runs" / name
    parts = {
        "validation": data.parts["validation"]["text"].tolist(),
        "test": data.parts["test"]["text"].tolist(),
        "fresh": data.fresh["text"].tolist(),
    }
    if all((folder / f"{part}.npy").is_file() for part in parts):
        return
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(sentiment.MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(sentiment.MODEL_ID).to(device)
    own = {label.lower(): i for i, label in model.config.id2label.items()}
    order = [own[label] for label in LABELS]
    target = np.zeros_like(wanted)
    target[:, order] = wanted
    epochs, batch = 3, 32
    steps = epochs * int(np.ceil(len(texts) / batch))
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
    schedule = get_linear_schedule_with_warmup(optimiser, int(0.1 * steps), steps)
    truth = data.parts["validation"]["sentiment"].tolist()
    best = -1.0
    model_dir = folder / "model"
    for _ in range(epochs):
        model.train()
        shuffled = rng.permutation(len(texts))
        for start in range(0, len(shuffled), batch):
            rows = shuffled[start : start + batch]
            encoded = tokenizer(
                [texts[i] for i in rows],
                padding=True,
                truncation=True,
                max_length=finetune.MAX_TOKENS,
                return_tensors="pt",
            ).to(device)
            logits = model(**encoded).logits
            aim = torch.tensor(target[rows], dtype=torch.float, device=device)
            loss = -(aim * torch.log_softmax(logits, dim=-1)).sum(dim=-1).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            schedule.step()
            optimiser.zero_grad()
        model.eval()
        said: list[str] = []
        with torch.no_grad():
            for start in range(0, len(parts["validation"]), 64):
                encoded = tokenizer(
                    parts["validation"][start : start + 64],
                    padding=True,
                    truncation=True,
                    max_length=finetune.MAX_TOKENS,
                    return_tensors="pt",
                ).to(device)
                picked = model(**encoded).logits.argmax(dim=-1).tolist()
                said += [model.config.id2label[i].lower() for i in picked]
        score = classification.report(truth, said, LABELS).accuracy
        if score > best:
            best = score
            model_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(model_dir)
            tokenizer.save_pretrained(model_dir)
    del model, optimiser
    base.free()
    for part, part_texts in parts.items():
        np.save(folder / f"{part}.npy", base.predict(model_dir, part_texts))
    base.say(f"  trained {name}: one model, {best:.3f} on validation")


def round_three(best: dict[str, str], log: dict[str, Any]) -> None:
    choices = json.loads((OUT / "choices.json").read_text())
    final = json.loads((OUT / "final_train.json").read_text())
    config = base.CONFIGS[choices["step1"]["chosen"]]
    data = base.Data(POOL, "pool60.json")
    truth = data.parts["validation"]["sentiment"].tolist()
    pool_texts = data.pool["text"].tolist()
    human_texts, human_labels = final["human"]["texts"], final["human"]["labels"]

    # What the best ensemble says about the larger pool. FinBERT's models were only
    # kept on disk if step 4 was the final one; otherwise they are trained again.
    said = []
    for name, prefix in best.items():
        settings = dict(config)
        if name in FAMILIES:
            settings["base_model"] = FAMILIES[name][0]
            if not FAMILIES[name][1]:
                settings["label_names"] = LABELS
        for seed in SEEDS:
            folder = OUT / "runs" / f"{prefix}-{seed}"
            path = folder / "pool60.npy"
            if not path.is_file():
                if not (folder / "model").is_dir():
                    for old in folder.glob("*.npy"):
                        old.unlink()
                    base.run(
                        f"{prefix}-{seed}",
                        data,
                        final["texts"],
                        final["labels"],
                        settings,
                        seed,
                        keep=True,
                    )
                np.save(path, base.predict(folder / "model", pool_texts))
        said.append(
            np.mean(
                [np.load(OUT / "runs" / f"{prefix}-{seed}" / "pool60.npy") for seed in SEEDS],
                axis=0,
            )
        )
    before = together(list(best.values()), "validation")
    t = base.temperature(before, truth)
    on_pool = base.cooled(np.mean(said, axis=0), t)
    # Decision 099's amendment: the 0.90 of the first round selected nothing. An article
    # is taken at the confidence where about four in five validation headlines are right.
    calm = base.cooled(before, t)
    sureness = calm.max(axis=1)
    correct = np.array(base.said(calm)) == np.array(truth)
    level = float(np.quantile(sureness, 0.5))
    for value in np.unique(np.round(sureness, 3)):
        kept = sureness >= value
        if kept.mean() >= base.WANTED_KEPT and correct[kept].mean() >= base.WANTED_RIGHT:
            level = float(value)
            break
    sure = on_pool.max(axis=1) >= level
    picked = on_pool.argmax(axis=1)
    mix = pd.Series(human_labels).value_counts(normalize=True)
    rng = np.random.default_rng(98)
    extra: list[int] = []
    for index, label in enumerate(LABELS):
        rows = np.flatnonzero(sure & (picked == index))
        cap = round(ADDED * float(mix.get(label, 0)))
        extra += rng.choice(rows, size=min(cap, len(rows)), replace=False).tolist()
    texts = human_texts + [pool_texts[i] for i in extra]
    labels = human_labels + [LABELS[picked[i]] for i in extra]

    families: dict[str, str] = {}
    for name in best:
        settings = dict(config)
        if name in FAMILIES:
            settings["base_model"] = FAMILIES[name][0]
            if not FAMILIES[name][1]:
                settings["label_names"] = LABELS
        if late():
            break
        for seed in SEEDS:
            base.run(f"r3-{name}-{seed}", data, texts, labels, settings, seed)
        families[name] = f"r3-{name}"
    if len(families) < len(best):
        log["round3"] = {"stopped": "out of time"}
        return
    score = base.right(together(list(families.values()), "validation"), truth)
    log["round3"] = {
        "sure of": int(sure.sum()),
        "added": len(extra),
        "ensemble": score,
        "gain": score - log["round2"]["best score"],
    }
    base.say(f"round 3: added {len(extra)}, together {score:.3f}")

    # One model taught by the ensemble: its probabilities on the added articles, and
    # the labels themselves on the labelled ones.
    if not late():
        ensemble_on_pool = np.mean(said, axis=0)[extra]
        own = np.eye(len(LABELS))[[LABELS.index(label) for label in human_labels]]
        distil("r3-single", data, texts, np.vstack([own, ensemble_on_pool]))
        log["round3"]["single"] = base.right(
            np.load(OUT / "runs" / "r3-single" / "validation.npy"), truth
        )
    log["round3"]["families"] = families


def rounds() -> None:
    log: dict[str, Any] = {}
    best = round_two(log)
    (OUT / "rounds.json").write_text(json.dumps(log, indent=2, default=float))
    if log["round2"]["gain"] >= WORTH and not late():
        round_three(best, log)
    else:
        log["round3"] = {"stopped": "round 2 added under half a point, or out of time"}
    # The candidate validation prefers.
    candidate: dict[str, Any] = {
        "prefixes": list(best.values()),
        "score": log["round2"]["best score"],
    }
    third = log.get("round3", {})
    if third.get("ensemble", 0) > candidate["score"]:
        candidate = {"prefixes": list(third["families"].values()), "score": third["ensemble"]}
    if third.get("single", 0) >= candidate["score"] - WORTH:
        candidate["single"] = True
    log["candidate"] = candidate
    (OUT / "rounds.json").write_text(json.dumps(log, indent=2, default=float))
    base.say(json.dumps(log, indent=2, default=float))
    # Models are large and are not needed again.
    for folder in (OUT / "runs").glob("r2-*/model"):
        shutil.rmtree(folder, ignore_errors=True)


def report() -> None:
    """The one last reading of the sealed tests, for the candidate validation prefers."""
    log = json.loads((OUT / "rounds.json").read_text())
    candidate = log["candidate"]
    data = base.Data()
    validation = data.parts["validation"]["sentiment"].tolist()
    before = together(candidate["prefixes"], "validation")
    t = base.temperature(before, validation)
    calm = base.cooled(before, t)
    sureness = calm.max(axis=1)
    correct = np.array(base.said(calm)) == np.array(validation)
    threshold = float(np.quantile(sureness, 0.5))
    for value in np.unique(np.round(sureness, 3)):
        kept = sureness >= value
        if kept.mean() >= base.WANTED_KEPT and correct[kept].mean() >= base.WANTED_RIGHT:
            threshold = float(value)
            break
    out: dict[str, Any] = {"candidate": candidate, "temperature": t, "threshold": threshold}
    for name, frame in {"test": data.parts["test"], "fresh": data.fresh}.items():
        truth = frame["sentiment"].tolist()
        old = base.said(np.load(OUT / f"in_use_{name}.npy"))
        said = together(candidate["prefixes"], name)
        new = base.said(said)
        found = classification.report(truth, new, LABELS)
        check = classification.mcnemar(truth, old, new)
        kept = base.cooled(said, t).max(axis=1) >= threshold
        right = np.array(new) == np.array(truth)
        rows: dict[str, Any] = {
            "n": len(frame),
            "in use": classification.report(truth, old, LABELS).accuracy,
            "right": found.accuracy,
            "macro_f1": found.macro_f1,
            "only in use right": check.only_first_right,
            "only new right": check.only_second_right,
            "p": check.p_value,
            "kept": float(kept.mean()),
            "right among kept": float(right[kept].mean()) if kept.any() else None,
        }
        if candidate.get("single"):
            one = base.said(np.load(OUT / "runs" / "r3-single" / f"{name}.npy"))
            rows["single model right"] = classification.report(truth, one, LABELS).accuracy
            rows["single model p"] = classification.mcnemar(truth, old, one).p_value
        out[name] = rows
    (OUT / "rounds_results.json").write_text(json.dumps(out, indent=2, default=float))
    base.say(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    if parser.parse_args().report:
        report()
    else:
        rounds()
