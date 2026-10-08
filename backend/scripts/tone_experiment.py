"""Raising the accuracy of news tone: the experiment of docs/DECISIONS.md 097.

    uv run python backend/scripts/tone_experiment.py            # every step, resumable
    uv run python backend/scripts/tone_experiment.py --report   # print what is stored

Needs the `nlp` extra, a graphics card, and the database. Every choice is made on the
training and validation parts. Probabilities for the two test sets are written to disk
as each model is trained and are read once, by `report`, after the final model is fixed.
Nothing here is used by the app: it writes under data/research/tone/, which is not
committed.
"""

import argparse
import gc
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import NewsArticle, NewsSymbol
from radar.db.session import make_engine, session_scope
from radar.models import classification, dataset, finetune, sentiment
from radar.pipelines import finetune as job
from radar.pipelines.labels import load_labels

OUT = Path("data/research/tone")
SEEDS = (13, 17, 23, 29, 31)
LABELS = list(sentiment.LABELS)
IN_USE = Path("data/models/finbert-radar-1")

# The two written-down candidates of step 1.
ORIGINAL: dict[str, Any] = {
    "epochs": 4,
    "early_stopping_patience": 99,
    "label_smoothing": 0.0,
    "class_weights": False,
    "layer_wise_lr_decay": 1.0,
    "oversample_minority": False,
}
TUNED: dict[str, Any] = {
    "epochs": 10,
    "early_stopping_patience": 2,
    "label_smoothing": 0.1,
    "class_weights": True,
    "layer_wise_lr_decay": 0.9,
    "oversample_minority": False,
}
CONFIGS = {"original": ORIGINAL, "tuned": TUNED}

# Step 3: a training label is dropped when the models give it under LOW and give
# another label over HIGH. Step 4: how sure the ensemble must be, and how much is added.
LOW, HIGH = 0.20, 0.60
SURE = 0.90
POOL = 15_000
TIMES = 3
# Step 5.
WANTED_RIGHT, WANTED_KEPT = 0.80, 0.40


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def free() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def predict(model_dir: Path, texts: list[str]) -> np.ndarray:
    scorer = sentiment.FinbertScorer(str(model_dir), "experiment")
    out = scorer.probabilities(texts)
    del scorer
    free()
    return out


class Data:
    """The labelled parts, the two sealed test sets, and the unlabelled pool."""

    def __init__(self, pool_size: int = POOL, pool_file: str = "pool.json") -> None:
        self.pool_size, self.pool_file = pool_size, pool_file
        engine = make_engine()
        with session_scope(engine) as session:
            training = job.with_text(session, job.load_training_labels())
            reference = job.with_text(session, load_labels())
            fresh = job.with_text(session, job.load_replication_labels())
            job.check_dataset(training, reference)
            job.check_replication(fresh, training, reference)
            self.parts = {
                name: training[training["split"] == name].reset_index(drop=True)
                for name in dataset.SPLITS
            }
            self.fresh = fresh.reset_index(drop=True)
            self.pool = self._pool(session, training, reference, fresh)

    def _pool(
        self, session: Any, training: pd.DataFrame, reference: pd.DataFrame, fresh: pd.DataFrame
    ) -> pd.DataFrame:
        """Stored articles from the training period that no labelled set has, or echoes."""
        path = OUT / self.pool_file
        newest = self.parts["train"]["created_at"].max()
        labelled = pd.concat([training, reference, fresh])
        if path.is_file():
            ids = json.loads(path.read_text())
        else:
            found = session.scalars(
                select(NewsArticle.id)
                .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
                .where(
                    NewsArticle.duplicate_of.is_(None),
                    NewsArticle.created_at <= newest,
                    NewsSymbol.symbol.in_(sorted(set(training["symbol"]))),
                )
                .distinct()
                .order_by(NewsArticle.id)
            ).all()
            taken = set(labelled["article_id"])
            free_ids = [i for i in found if i not in taken]
            rng = np.random.default_rng(20261009)
            ids = sorted(
                rng.choice(
                    free_ids, size=min(self.pool_size * 2, len(free_ids)), replace=False
                ).tolist()
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ids))
        rows = session.execute(
            select(
                NewsArticle.id, NewsArticle.headline, NewsArticle.summary, NewsArticle.created_at
            ).where(NewsArticle.id.in_(ids))
        ).all()
        pool = pd.DataFrame(rows, columns=["article_id", "headline", "summary", "created_at"])
        pool = dataset.drop_repeats(pool, labelled["headline"].map(dataset.headline_key))
        pool = pool.sort_values("article_id").head(self.pool_size).reset_index(drop=True)
        pool["text"] = [
            sentiment.article_text(h, s or "")
            for h, s in zip(pool["headline"], pool["summary"], strict=True)
        ]
        if pool["created_at"].max() > newest:
            raise ValueError("The pool reaches past the training period")
        return pool


def run(
    name: str,
    data: Data,
    texts: list[str],
    labels: list[str],
    config: dict[str, Any],
    seed: int,
    *,
    also: dict[str, list[str]] | None = None,
    keep: bool = False,
) -> dict[str, np.ndarray]:
    """Train one model, or read what it said if it was trained before.

    What it said about the validation part and both test sets is written to disk. The
    test sets' files are not read again until `report`.
    """
    folder = OUT / "runs" / name
    wanted = {
        "validation": data.parts["validation"]["text"].tolist(),
        "test": data.parts["test"]["text"].tolist(),
        "fresh": data.fresh["text"].tolist(),
        **(also or {}),
    }
    if not all((folder / f"{part}.npy").is_file() for part in wanted):
        model_dir = folder / "model"
        validation = data.parts["validation"]
        result = finetune.fine_tune(
            texts,
            labels,
            validation["text"].tolist(),
            validation["sentiment"].tolist(),
            model_dir,
            seed=seed,
            **config,
        )
        free()
        (folder / "training.json").write_text(result.model_dump_json())
        for part, part_texts in wanted.items():
            np.save(folder / f"{part}.npy", predict(model_dir, part_texts))
        if not keep:
            shutil.rmtree(model_dir, ignore_errors=True)
        say(f"  trained {name}: kept pass {result.best_epoch} of {len(result.epochs)}")
    return {
        part: np.load(folder / f"{part}.npy") for part in wanted if part not in ("test", "fresh")
    }


def said(probabilities: np.ndarray) -> list[str]:
    return [LABELS[i] for i in probabilities.argmax(axis=1)]


def right(probabilities: np.ndarray, truth: list[str]) -> float:
    return classification.report(truth, said(probabilities), LABELS).accuracy


def temperature(probabilities: np.ndarray, truth: list[str]) -> float:
    """The one number that makes the stated confidence match how often it is right."""
    wanted = np.array([LABELS.index(label) for label in truth])
    logits = np.log(np.clip(probabilities, 1e-9, 1))
    best, best_loss = 1.0, np.inf
    for t in np.arange(0.5, 3.01, 0.05):
        scaled = logits / t
        scaled -= scaled.max(axis=1, keepdims=True)
        p = np.exp(scaled) / np.exp(scaled).sum(axis=1, keepdims=True)
        loss = -np.log(np.clip(p[np.arange(len(wanted)), wanted], 1e-9, 1)).mean()
        if loss < best_loss:
            best, best_loss = float(t), float(loss)
    return best


def cooled(probabilities: np.ndarray, t: float) -> np.ndarray:
    scaled = np.log(np.clip(probabilities, 1e-9, 1)) / t
    scaled -= scaled.max(axis=1, keepdims=True)
    out: np.ndarray = np.exp(scaled) / np.exp(scaled).sum(axis=1, keepdims=True)
    return out


def experiment() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = Data()
    train, validation = data.parts["train"], data.parts["validation"]
    truth = validation["sentiment"].tolist()
    texts, labels = train["text"].tolist(), train["sentiment"].tolist()
    log: dict[str, Any] = {"pool": len(data.pool)}
    say(f"train {len(train)}, validation {len(validation)}, pool {len(data.pool)}")

    # Step 1: which settings, by the mean validation score over three seeds.
    pool_texts = data.pool["text"].tolist()
    scores: dict[str, list[float]] = {}
    for name, config in CONFIGS.items():
        scores[name] = [
            right(
                run(
                    f"1-{name}-{seed}", data, texts, labels, config, seed, also={"pool": pool_texts}
                )["validation"],
                truth,
            )
            for seed in SEEDS[:3]
        ]
        say(f"step 1, {name}: {np.round(scores[name], 3)} mean {np.mean(scores[name]):.3f}")
    chosen = max(scores, key=lambda name: float(np.mean(scores[name])))
    config = CONFIGS[chosen]
    log["step1"] = {"scores": scores, "chosen": chosen}

    # Step 2: five seeds, probabilities averaged. Three were trained in step 1.
    members = [
        run(f"1-{chosen}-{seed}", data, texts, labels, config, seed, also={"pool": pool_texts})
        for seed in SEEDS
    ]
    single = float(np.mean([right(m["validation"], truth) for m in members]))
    together = np.mean([m["validation"] for m in members], axis=0)
    stages = {"2-ensemble": right(together, truth)}
    final = "2"
    log["step2"] = {"one model, mean": single, "ensemble": stages["2-ensemble"]}
    say(f"step 2: one model {single:.3f}, five together {stages['2-ensemble']:.3f}")

    # Step 3: likely label mistakes in the training part, by out-of-fold predictions.
    folds = np.random.default_rng(97).permutation(len(train)) % 5
    out_of_fold = np.zeros((len(train), len(LABELS)))
    for fold in range(5):
        inside = folds != fold
        held = train.loc[~inside, "text"].tolist()
        found = run(
            f"3-fold{fold}",
            data,
            train.loc[inside, "text"].tolist(),
            train.loc[inside, "sentiment"].tolist(),
            config,
            SEEDS[0],
            also={"held": held},
        )
        out_of_fold[~inside] = found["held"]
    given = np.array([LABELS.index(label) for label in labels])
    own = out_of_fold[np.arange(len(train)), given]
    other = np.where(np.eye(len(LABELS), dtype=bool)[given], 0, out_of_fold).max(axis=1)
    doubtful = (own < LOW) & (other > HIGH)
    kept_texts = [t for t, bad in zip(texts, doubtful, strict=True) if not bad]
    kept_labels = [label for label, bad in zip(labels, doubtful, strict=True) if not bad]
    pruned = [
        run(f"3-{seed}", data, kept_texts, kept_labels, config, seed, also={"pool": pool_texts})
        for seed in SEEDS
    ]
    stages["3-pruned"] = right(np.mean([m["validation"] for m in pruned], axis=0), truth)
    log["step3"] = {
        "out-of-fold right": float((out_of_fold.argmax(axis=1) == given).mean()),
        "dropped": int(doubtful.sum()),
        "dropped by label": pd.Series(np.array(labels)[doubtful]).value_counts().to_dict(),
        "ensemble": stages["3-pruned"],
    }
    say(f"step 3: dropped {int(doubtful.sum())}, five together {stages['3-pruned']:.3f}")
    if stages["3-pruned"] >= stages["2-ensemble"]:
        final, members, texts, labels = "3", pruned, kept_texts, kept_labels

    # Step 4: self-training on stored articles from the training period.
    before = np.mean([m["validation"] for m in members], axis=0)
    t = temperature(before, truth)
    on_pool = cooled(np.mean([m["pool"] for m in members], axis=0), t)
    sure = on_pool.max(axis=1) >= SURE
    picked = on_pool.argmax(axis=1)
    mix = pd.Series(labels).value_counts(normalize=True)
    rng = np.random.default_rng(97)
    extra: list[int] = []
    for index, label in enumerate(LABELS):
        rows = np.flatnonzero(sure & (picked == index))
        cap = round(TIMES * len(labels) * float(mix.get(label, 0)))
        extra += rng.choice(rows, size=min(cap, len(rows)), replace=False).tolist()
    more_texts = texts + [pool_texts[i] for i in extra]
    more_labels = labels + [LABELS[picked[i]] for i in extra]
    taught = [
        run(f"4-{seed}", data, more_texts, more_labels, config, seed, keep=True) for seed in SEEDS
    ]
    stages["4-self-trained"] = right(np.mean([m["validation"] for m in taught], axis=0), truth)
    log["step4"] = {
        "temperature": t,
        "sure of": int(sure.sum()),
        "added": len(extra),
        "added by label": pd.Series([LABELS[picked[i]] for i in extra]).value_counts().to_dict(),
        "ensemble": stages["4-self-trained"],
    }
    say(f"step 4: added {len(extra)}, five together {stages['4-self-trained']:.3f}")
    if stages["4-self-trained"] >= stages[{"2": "2-ensemble", "3": "3-pruned"}[final]]:
        final, members = "4", taught

    # What the final model was trained on, for the rounds of decision 098.
    (OUT / "final_train.json").write_text(
        json.dumps(
            {
                "prefix": {"2": f"1-{chosen}", "3": "3", "4": "4"}[final],
                "human": {"texts": texts, "labels": labels},
                "texts": more_texts if final == "4" else texts,
                "labels": more_labels if final == "4" else labels,
            }
        )
    )

    # Step 5: one temperature and one threshold, both from the validation part.
    together = np.mean([m["validation"] for m in members], axis=0)
    t = temperature(together, truth)
    calm = cooled(together, t)
    sureness, correct = calm.max(axis=1), np.array(said(calm)) == np.array(truth)
    threshold: float | None = None
    at: tuple[float, float] = (0.0, 0.0)
    for candidate in np.unique(np.round(sureness, 3)):
        kept = sureness >= candidate
        if kept.mean() >= WANTED_KEPT and correct[kept].mean() >= WANTED_RIGHT:
            threshold, at = float(candidate), (float(kept.mean()), float(correct[kept].mean()))
            break
    if threshold is None:
        threshold = float(np.quantile(sureness, 0.5))
        kept = sureness >= threshold
        at = (float(kept.mean()), float(correct[kept].mean()))
    log["step5"] = {
        "temperature": t,
        "threshold": threshold,
        "validation kept": at[0],
        "validation right": at[1],
    }
    log["stages"] = stages
    log["final"] = final
    (OUT / "choices.json").write_text(json.dumps(log, indent=2, default=float))
    say(
        f"final model: step {final}; threshold {threshold:.3f} keeps {at[0]:.0%}, {at[1]:.0%} right"
    )


def report() -> None:
    """The one reading of the two test sets, after every choice is stored."""
    choices = json.loads((OUT / "choices.json").read_text())
    data = Data()
    final, t, threshold = (
        choices["final"],
        choices["step5"]["temperature"],
        choices["step5"]["threshold"],
    )
    sets = {"test": data.parts["test"], "fresh": data.fresh}
    out: dict[str, Any] = {"final": final}
    for name, frame in sets.items():
        truth = frame["sentiment"].tolist()
        path = OUT / f"in_use_{name}.npy"
        if not path.is_file():
            np.save(path, predict(IN_USE, frame["text"].tolist()))
        old = said(np.load(path))
        rows: dict[str, Any] = {
            "n": len(frame),
            "in use": classification.report(truth, old, LABELS).accuracy,
        }
        # The other steps are shown beside the final one; they chose nothing.
        for step in ("2", "3", "4"):
            prefix = f"1-{choices['step1']['chosen']}" if step == "2" else step
            files = [OUT / "runs" / f"{prefix}-{seed}" / f"{name}.npy" for seed in SEEDS]
            if not all(f.is_file() for f in files):
                continue
            together = np.mean([np.load(f) for f in files], axis=0)
            rows[f"step {step}, five together"] = right(together, truth)
            rows[f"step {step}, one model, mean"] = float(
                np.mean([right(np.load(f), truth) for f in files])
            )
            if step == final:
                new = said(together)
                found = classification.report(truth, new, LABELS)
                check = classification.mcnemar(truth, old, new)
                calm = cooled(together, t)
                kept = calm.max(axis=1) >= threshold
                correct = np.array(new) == np.array(truth)
                rows["final"] = {
                    "right": found.accuracy,
                    "macro_f1": found.macro_f1,
                    "only in use right": check.only_first_right,
                    "only new right": check.only_second_right,
                    "p": check.p_value,
                    "kept": float(kept.mean()),
                    "right among kept": float(correct[kept].mean()) if kept.any() else None,
                    "right among dropped": float(correct[~kept].mean()) if (~kept).any() else None,
                }
        out[name] = rows
    (OUT / "results.json").write_text(json.dumps(out, indent=2, default=float))
    say(json.dumps({"choices": choices, "results": out}, indent=2, default=float))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    if parser.parse_args().report:
        report()
    else:
        experiment()
