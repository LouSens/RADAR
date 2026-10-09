"""The news-tone model rebuilt as one pipeline, in order (decision 101).

    load        the labelled headlines, the second labelling pass, the new test set
    guards      nothing shared between the parts, and the parts in time order
    choose_*    input text, base model and settings, each on three walk-forward blocks
    final       five seeds on the last block
    self_train  the five label stored articles and are trained again with the sure ones
    calibrate   one temperature
    test_once   the new test set, read a single time

Every step stores what it found under `data/research/tone4/` and reads it back when it
is there, so a rerun costs seconds and a step is repeated by deleting its file. The
test set is not touched by any step before `test_once`. Needs the `nlp` extra and the
database.
"""

import csv
import gc
import hashlib
import io
import json
import shutil
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import NewsArticle, NewsSymbol
from radar.db.session import make_engine, session_scope
from radar.logging import get_logger
from radar.models import classification, dataset, evidence, finetune, sentiment
from radar.pipelines import finetune as job
from radar.pipelines.labels import load_labels

log = get_logger(__name__)

OUT = Path("data/research/tone4")
MODEL_DIR = Path("data/models/tone-radar-2")
ROUND4_LABELS_FILE = "sentiment_round4_labels.csv"
LABELS = list(sentiment.LABELS)
MARKET = {"BTC/USD": "Bitcoin", "SPY": "US stocks", "GLD": "Gold", "PAXG/USD": "Gold"}

# The test period starts here; nothing dated later is trained or chosen on.
TEST_FROM = pd.Timestamp("2026-08-01", tz="UTC")
# Choices are made on the last three stretches of 300 headlines before it.
BLOCK, BLOCKS = 300, 3
CHOICE_SEEDS = (13, 17)
FINAL_SEEDS = (13, 17, 23, 29, 31)

TEXTS: dict[str, dict[str, bool]] = {
    "headline": {"with_asset": False, "with_summary": False},
    "asset + headline": {"with_asset": True, "with_summary": False},
    "headline + summary": {"with_asset": False, "with_summary": True},
    "asset + headline + summary": {"with_asset": True, "with_summary": True},
}
MODELS: dict[str, str] = {
    "RoBERTa (social media)": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "FinBERT": "ProsusAI/finbert",
    "DeBERTa-v3": "microsoft/deberta-v3-base",
    "DeBERTa-v3 (finance)": "nickmuchi/deberta-v3-base-finetuned-finance-text-classification",
}
# Where every choice starts. At most 8 passes, stopped after 2 without a lower
# validation error, the lowest-error pass kept.
START: dict[str, Any] = {
    "epochs": 8,
    "early_stopping_patience": 2,
    "learning_rate": 2e-5,
    "layer_wise_lr_decay": 1.0,
    "dropout": None,
    "weight_decay": 0.01,
    "label_smoothing": 0.0,
}
# Step 3, in this order; each list is tried with everything else held at the winner so far.
SETTINGS: list[list[dict[str, Any]]] = [
    [
        {"learning_rate": rate, "layer_wise_lr_decay": decay}
        for rate in (1e-5, 2e-5, 3e-5)
        for decay in (1.0, 0.85)
    ],
    [{"dropout": drop, "weight_decay": decay} for drop in (None, 0.2) for decay in (0.01, 0.1)],
    [{"label_smoothing": 0.0}, {"label_smoothing": 0.1}],
]
POOL_SIZE, ADD_AT_MOST = 30_000, 12_000
# Fixes which articles are drawn into the pool and which sure ones are added.
DRAW_SEED = 20261010
SURE_IS_RIGHT = 0.80
# The bars of decision 101.
P_BELOW, ACCURACY_GAP, LOSS_GAP = 0.05, 0.05, 0.10


@dataclass
class Data:
    # Training and validation headlines, oldest first.
    labelled: pd.DataFrame
    # The new test set. No step before `test_once` reads its labels.
    test: pd.DataFrame
    # Every other labelled headline: the reference sample, and old test headlines that
    # fall inside the new test period.
    held_back: pd.DataFrame


def load_round4_labels() -> pd.DataFrame:
    """The new test labels (`split` "test3") and the second pass on old ones ("second")."""
    text = (resources.files("radar") / ROUND4_LABELS_FILE).read_text(encoding="utf-8")
    frame = pd.DataFrame(list(csv.DictReader(io.StringIO(text))))
    frame["article_id"] = frame["article_id"].astype("int64")
    return frame


def load() -> Data:
    """Join every label to its article and lay the parts out in time order."""
    with session_scope(make_engine()) as session:
        first = job.with_text(session, job.load_training_labels())
        replication = job.with_text(session, job.load_replication_labels())
        reference = job.with_text(session, load_labels())
        round4 = job.with_text(session, load_round4_labels())
    old = pd.concat([first, replication], ignore_index=True)
    again = round4[round4["split"] == "second"].set_index("article_id")["sentiment"]
    inside = old["created_at"] < TEST_FROM
    labelled = old[inside].sort_values(["created_at", "article_id"]).reset_index(drop=True)
    labelled["first"] = labelled["sentiment"]
    labelled["second"] = labelled["article_id"].map(again)
    # Scoring follows the second pass where there is one: it is the rule the test follows.
    labelled["sentiment"] = labelled["second"].fillna(labelled["first"])
    test = round4[round4["split"] == "test3"]
    test = test.sort_values(["created_at", "article_id"]).reset_index(drop=True)
    for frame in (labelled, test):
        frame["market"] = frame["symbol"].map(MARKET)
    held_back = pd.concat([old[~inside], reference], ignore_index=True)
    data = Data(labelled=labelled, test=test, held_back=held_back)
    broken = {name: count for name, count in guards(data).items() if count}
    if broken:
        raise ValueError(f"The parts are not separate: {broken}")
    return data


def guards(data: Data) -> dict[str, int]:
    """Counts that must all be zero for the test to be fair."""
    parts = {"training": data.labelled, "test": data.test, "held back": data.held_back}
    keys = {name: set(part["headline"].map(dataset.headline_key)) for name, part in parts.items()}
    ids = {name: set(part["article_id"]) for name, part in parts.items()}
    return {
        "articles in both training and test": len(ids["training"] & ids["test"]),
        "near-copies in both training and test": len(keys["training"] & keys["test"]),
        "test articles labelled before": len(ids["test"] & ids["held back"]),
        "test near-copies of something labelled before": len(keys["test"] & keys["held back"]),
        "near-copies appearing twice in training": int(
            data.labelled["headline"].map(dataset.headline_key).duplicated().sum()
        ),
        "training headlines dated inside the test period": int(
            (data.labelled["created_at"] >= TEST_FROM).sum()
        ),
        "test headlines dated before the test period": int(
            (data.test["created_at"] < TEST_FROM).sum()
        ),
    }


def agreement(data: Data) -> pd.DataFrame:
    """How often the two labelling passes gave the same label, per market."""
    both = data.labelled.dropna(subset=["second"])
    same = (both["first"] == both["second"]).groupby(both["market"]).agg(["size", "mean"])
    same.loc["all"] = [len(both), float((both["first"] == both["second"]).mean())]
    return same.rename(columns={"size": "headlines", "mean": "same label"})


def shares(frame: pd.DataFrame) -> np.ndarray:
    """What a model is trained towards: one row per headline, a share for each label.

    One labelling pass gives its label everything. Two passes that differ give half each.
    """
    column = {label: i for i, label in enumerate(LABELS)}
    out = np.zeros((len(frame), len(LABELS)))
    rows = np.arange(len(frame))
    second = frame["second"].fillna(frame["first"]) if "second" in frame else frame["first"]
    for given in (frame["first"], second):
        out[rows, [column[label] for label in given]] += 0.5
    return out


def texts(frame: pd.DataFrame, text: str) -> list[str]:
    """The input text for each row, built the way `text` names (a key of `TEXTS`)."""
    return [
        dataset.model_text(str(headline), str(summary or ""), str(market), **TEXTS[text])
        for headline, summary, market in zip(
            frame["headline"], frame["summary"], frame["market"], strict=True
        )
    ]


def blocks(data: Data) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """The three walk-forward blocks: (train on, validate on), oldest block first."""
    return [
        (data.labelled.iloc[list(train)], data.labelled.iloc[list(validate)])
        for train, validate in dataset.walk_forward_blocks(len(data.labelled), BLOCK, BLOCKS)
    ]


# --- one training run, stored ---


def _free() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _label_names(model: str) -> list[str] | None:
    """The label order to give a base model whose own labels are not ours."""
    from transformers import AutoConfig

    same = {"bearish": "negative", "bullish": "positive"}
    own = AutoConfig.from_pretrained(model).id2label
    names = [same.get(own[i].lower(), own[i].lower()) for i in sorted(own)]
    if sorted(names) != sorted(LABELS):
        return LABELS  # no usable head: a new one is trained
    return None if names == [own[i].lower() for i in sorted(own)] else names


def _predict(folder: Path | str, inputs: list[str]) -> np.ndarray:
    """`folder` is a folder holding a model, or the name of one to download."""
    where = folder.as_posix() if isinstance(folder, Path) else folder
    scorer = sentiment.FinbertScorer(where, "tone")
    out = scorer.probabilities(inputs)
    del scorer
    _free()
    return out


def _name(*parts: Any) -> str:
    # A short name for a folder, not a secret.
    written = json.dumps(parts, sort_keys=True, default=str).encode()
    return hashlib.sha1(written, usedforsecurity=False).hexdigest()[:10]


def run(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    text: str,
    model: str,
    settings: dict[str, Any],
    seed: int,
    added: pd.DataFrame | None = None,
    also: dict[str, list[str]] | None = None,
    keep_model: Path | None = None,
) -> dict[str, Any]:
    """Train one model and store what it said; read it back if it is already stored.

    `added` holds extra training rows with a `text` and a `sentiment` column (labels
    written by models, for self-training). `also` names further lists of texts to be
    scored with the kept model. The model's files are deleted unless `keep_model` says
    where to keep them.
    """
    name = _name(
        list(train["article_id"]),
        list(validation["article_id"]),
        text,
        model,
        settings,
        seed,
        None if added is None else list(added["text"]),
    )
    folder = OUT / "runs" / name
    record = folder / "training.json"
    wanted = ["validation", *(also or {})]
    if not (record.is_file() and all((folder / f"{key}.npy").is_file() for key in wanted)):
        folder.mkdir(parents=True, exist_ok=True)
        model_dir = keep_model or Path(tempfile.mkdtemp(prefix="radar_tone_"))
        train_texts, targets = texts(train, text), shares(train)
        train_labels = train["sentiment"].tolist()
        if added is not None and len(added):
            column = {label: i for i, label in enumerate(LABELS)}
            extra = np.zeros((len(added), len(LABELS)))
            extra[np.arange(len(added)), [column[label] for label in added["sentiment"]]] = 1.0
            train_texts, targets = train_texts + added["text"].tolist(), np.vstack([targets, extra])
            train_labels = train_labels + added["sentiment"].tolist()
        validation_texts = texts(validation, text)
        result = finetune.fine_tune(
            train_texts,
            train_labels,
            validation_texts,
            validation["sentiment"].tolist(),
            model_dir,
            base_model=model,
            label_names=_label_names(model),
            seed=seed,
            train_targets=targets,
            keep="loss",
            **settings,
        )
        _free()
        np.save(folder / "validation.npy", _predict(model_dir, validation_texts))
        for key, inputs in (also or {}).items():
            np.save(folder / f"{key}.npy", _predict(model_dir, inputs))
        if keep_model is None:
            shutil.rmtree(model_dir, ignore_errors=True)
        record.write_text(result.model_dump_json())
        log.info("tone run stored", extra={"run": name, "model": model, "seed": seed})
    out: dict[str, Any] = {"name": name, "training": json.loads(record.read_text())}
    for key in wanted:
        out[key] = np.load(folder / f"{key}.npy")
    return out


def measure(truth: list[str], probabilities: np.ndarray) -> dict[str, float]:
    said = [LABELS[i] for i in probabilities.argmax(axis=1)]
    report = classification.report(truth, said, LABELS)
    return {
        "loss": classification.log_loss(truth, probabilities, LABELS),
        "accuracy": report.accuracy,
        "macro_f1": report.macro_f1,
    }


# --- steps 1 to 3: choices on the three blocks ---


def on_blocks(data: Data, *, text: str, model: str, settings: dict[str, Any]) -> dict[str, Any]:
    """One candidate, trained on each block with each seed. Means, and every run."""
    rows = []
    for number, (train, validation) in enumerate(blocks(data), start=1):
        for seed in CHOICE_SEEDS:
            got = run(train, validation, text=text, model=model, settings=settings, seed=seed)
            passes = got["training"]["epochs"]
            kept = next(p for p in passes if p["epoch"] == got["training"]["best_epoch"])
            rows.append(
                {
                    "block": number,
                    "seed": seed,
                    **measure(validation["sentiment"].tolist(), got["validation"]),
                    "passes": len(passes),
                    "kept": kept["epoch"],
                    "training_loss": kept["train_loss"],
                    "validation_loss_last_pass": passes[-1]["validation_loss"],
                }
            )
    frame = pd.DataFrame(rows)
    return {
        "loss": float(frame["loss"].mean()),
        "accuracy": float(frame["accuracy"].mean()),
        "macro_f1": float(frame["macro_f1"].mean()),
        "training_loss": float(frame["training_loss"].mean()),
        "runs": rows,
    }


def _stored(name: str) -> dict[str, Any] | None:
    path = OUT / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def _store(name: str, found: dict[str, Any]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(found, indent=1, default=str))
    return found


def _winner(options: dict[str, dict[str, Any]]) -> str:
    return min(options, key=lambda name: options[name]["loss"])


def choose_text(data: Data) -> dict[str, Any]:
    """Step 1: which text the model reads."""
    found = _stored("step1_text")
    if found is None:
        model = MODELS["RoBERTa (social media)"]
        options = {name: on_blocks(data, text=name, model=model, settings=START) for name in TEXTS}
        found = _store("step1_text", {"options": options, "winner": _winner(options)})
    return found


def choose_model(data: Data) -> dict[str, Any]:
    """Step 2: which base model is trained further."""
    found = _stored("step2_model")
    if found is None:
        text = choose_text(data)["winner"]
        options = {
            name: on_blocks(data, text=text, model=model, settings=START)
            for name, model in MODELS.items()
        }
        found = _store("step2_model", {"options": options, "winner": _winner(options)})
    return found


def _label(settings: dict[str, Any]) -> str:
    return ", ".join(f"{key} {value}" for key, value in settings.items())


def choose_settings(data: Data) -> dict[str, Any]:
    """Step 3: the training settings, one group at a time."""
    found = _stored("step3_settings")
    if found is None:
        text = choose_text(data)["winner"]
        model = MODELS[choose_model(data)["winner"]]
        settings, groups = dict(START), []
        for group in SETTINGS:
            options = {
                _label(change): on_blocks(
                    data, text=text, model=model, settings={**settings, **change}
                )
                for change in group
            }
            best = _winner(options)
            settings.update(next(change for change in group if _label(change) == best))
            groups.append({"options": options, "winner": best})
        found = _store("step3_settings", {"groups": groups, "settings": settings})
    return found


def chosen(data: Data) -> dict[str, Any]:
    """The text, base model and settings steps 1 to 3 ended on."""
    name = choose_model(data)["winner"]
    return {
        "text": choose_text(data)["winner"],
        "model_name": name,
        "model": MODELS[name],
        "settings": choose_settings(data)["settings"],
    }


# --- steps 4 to 6, on the last block ---


def pool(data: Data, text: str) -> pd.DataFrame:
    """Stored articles no one has labelled, drawn at random from the whole training period.

    None is newer than the newest training headline of the last block, and none shares
    a headline key with anything labelled.
    """
    train, _ = blocks(data)[-1]
    newest = train["created_at"].max()
    every = pd.concat([data.labelled, data.test, data.held_back])
    path = OUT / "pool.json"
    with session_scope(make_engine()) as session:
        if path.is_file():
            ids = json.loads(path.read_text())
        else:
            found = session.execute(
                select(NewsArticle.id, NewsSymbol.symbol)
                .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
                .where(
                    NewsArticle.duplicate_of.is_(None),
                    NewsArticle.created_at <= newest,
                    NewsSymbol.symbol.in_(list(MARKET)),
                )
                .order_by(NewsArticle.id, NewsSymbol.symbol)
            ).all()
            taken = set(every["article_id"])
            free = sorted({row[0] for row in found if row[0] not in taken})
            rng = np.random.default_rng(DRAW_SEED)
            # Twice the size, because near-copies are dropped afterwards.
            ids = rng.choice(free, size=min(POOL_SIZE * 2, len(free)), replace=False).tolist()
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ids))
        rows: list[Any] = []
        for start in range(0, len(ids), 20_000):  # a query takes a limited number of values
            rows += session.execute(
                select(
                    NewsArticle.id,
                    NewsSymbol.symbol,
                    NewsArticle.headline,
                    NewsArticle.summary,
                    NewsArticle.created_at,
                )
                .join(NewsSymbol, NewsSymbol.article_id == NewsArticle.id)
                .where(
                    NewsArticle.id.in_(ids[start : start + 20_000]),
                    NewsSymbol.symbol.in_(list(MARKET)),
                )
                .order_by(NewsArticle.id, NewsSymbol.symbol)
            ).all()
    frame = pd.DataFrame(
        rows, columns=["article_id", "symbol", "headline", "summary", "created_at"]
    )
    frame = frame.drop_duplicates("article_id")
    frame = dataset.drop_repeats(frame, every["headline"].map(dataset.headline_key))
    # In the order they were drawn, so the first `POOL_SIZE` are a random draw too.
    order = {article: place for place, article in enumerate(ids)}
    frame = frame.sort_values("article_id", key=lambda column: column.map(order))
    frame = frame.head(POOL_SIZE).reset_index(drop=True)
    frame["market"] = frame["symbol"].map(MARKET)
    frame["text"] = texts(frame, text)
    if pd.to_datetime(frame["created_at"], utc=True).max() > newest:
        raise ValueError("The pool reaches past the training period")
    return frame


def sure_from(truth: list[str], probabilities: np.ndarray) -> float | None:
    """The lowest confidence at which the headlines kept are right `SURE_IS_RIGHT` of the time.

    None when no confidence that keeps at least a fifth of the headlines reaches it.
    """
    confidence = probabilities.max(axis=1)
    right = np.array([LABELS[i] for i in probabilities.argmax(axis=1)]) == np.array(truth)
    for level in np.sort(np.unique(confidence)):
        kept = confidence >= level
        if kept.mean() < 0.2:
            break
        if right[kept].mean() >= SURE_IS_RIGHT:
            return float(level)
    return None


def _five(
    data: Data,
    choice: dict[str, Any],
    stage: str,
    added: pd.DataFrame | None = None,
    also: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Five seeds on the last block; their average, and each one's passes."""
    train, validation = blocks(data)[-1]
    runs = [
        run(
            train,
            validation,
            text=choice["text"],
            model=choice["model"],
            settings=choice["settings"],
            seed=seed,
            added=added,
            also=also,
            keep_model=MODEL_DIR / stage / str(seed),
        )
        for seed in FINAL_SEEDS
    ]
    truth = validation["sentiment"].tolist()
    out: dict[str, Any] = {
        "runs": [r["name"] for r in runs],
        "passes": [r["training"]["epochs"] for r in runs],
        "kept": [r["training"]["best_epoch"] for r in runs],
        "single": [measure(truth, r["validation"]) for r in runs],
        "validation": np.mean([r["validation"] for r in runs], axis=0),
    }
    out["together"] = measure(truth, out["validation"])
    for key in also or {}:
        out[key] = np.mean([r[key] for r in runs], axis=0)
    return out


def final(data: Data) -> dict[str, Any]:
    """Steps 4 to 6: five seeds, self-training if it helps, one temperature."""
    found = _stored("final")
    if found is not None:
        return found
    choice = chosen(data)
    train, validation = blocks(data)[-1]
    truth = validation["sentiment"].tolist()
    unlabelled = pool(data, choice["text"])
    plain = _five(data, choice, "plain", also={"pool": unlabelled["text"].tolist()})

    # Step 5. The five label the pool; the sure ones join the training headlines.
    level = sure_from(truth, plain["validation"])
    added = unlabelled.iloc[0:0].assign(sentiment=[])
    if level is not None:
        said = np.array([LABELS[i] for i in plain["pool"].argmax(axis=1)])
        sure = unlabelled.assign(sentiment=said)[plain["pool"].max(axis=1) >= level]
        mix = train["sentiment"].value_counts(normalize=True)
        rng = np.random.default_rng(DRAW_SEED)
        parts = []
        for label, share in mix.items():
            part = sure[sure["sentiment"] == label]
            take = min(len(part), int(ADD_AT_MOST * share))
            parts.append(part.iloc[rng.choice(len(part), size=take, replace=False)])
        added = pd.concat(parts).sort_values("article_id")
    stages = {"five models": plain}
    if len(added):
        stages["five models, self-trained"] = _five(data, choice, "self", added=added)
    kept = min(stages, key=lambda name: stages[name]["together"]["loss"])
    for stage, folder in (("five models", "plain"), ("five models, self-trained", "self")):
        if stage != kept:
            shutil.rmtree(MODEL_DIR / folder, ignore_errors=True)

    # Step 6. One temperature, fitted on validation.
    probabilities = stages[kept]["validation"]
    temperature = classification.fit_temperature(truth, probabilities, LABELS)
    cooled = classification.with_temperature(probabilities, temperature)
    np.save(OUT / "validation_final.npy", cooled)
    return _store(
        "final",
        {
            "choice": choice,
            "train": len(train),
            "validation": len(validation),
            "train_to": str(train["created_at"].max()),
            "validation_to": str(validation["created_at"].max()),
            "pool": {
                "size": len(unlabelled),
                "from": str(unlabelled["created_at"].min()),
                "to": str(unlabelled["created_at"].max()),
                "sure_level": level,
                "added": len(added),
                "added_mix": added["sentiment"].value_counts().to_dict(),
            },
            "stages": {
                name: {key: stage[key] for key in ("passes", "kept", "single", "together")}
                for name, stage in stages.items()
            },
            "kept": kept,
            "folder": "plain" if kept == "five models" else "self",
            "temperature": temperature,
            "validation_after": measure(truth, cooled),
        },
    )


def final_probabilities(data: Data, frame: pd.DataFrame) -> np.ndarray:
    """What the kept five say about `frame`, averaged, with the temperature applied."""
    found = final(data)
    inputs = texts(frame, found["choice"]["text"])
    folder = MODEL_DIR / found["folder"]
    mean = np.mean([_predict(folder / str(seed), inputs) for seed in FINAL_SEEDS], axis=0)
    return classification.with_temperature(mean, found["temperature"])


# --- step 7: the test, once ---


def test_once(data: Data) -> dict[str, Any]:
    """Score the kept model and the one in use on the new test set, a single time.

    The result is stored, and a second call returns the stored result without scoring
    again, so the test set cannot be used to try something else.
    """
    found = _stored("test")
    if found is not None:
        return found
    kept = final(data)
    truth = data.test["sentiment"].tolist()
    new = final_probabilities(data, data.test)
    # The model in use reads what it reads in the app: the headline and the summary.
    in_use = _predict(
        job.MODEL_DIR,
        [
            sentiment.article_text(str(headline), str(summary or ""))
            for headline, summary in zip(data.test["headline"], data.test["summary"], strict=True)
        ],
    )
    np.save(OUT / "test_new.npy", new)
    np.save(OUT / "test_in_use.npy", in_use)
    said = {
        "in use": [LABELS[i] for i in in_use.argmax(axis=1)],
        "new": [LABELS[i] for i in new.argmax(axis=1)],
    }
    scores: dict[str, dict[str, Any]] = {
        "in use": measure(truth, in_use),
        "new": measure(truth, new),
    }
    for name, score in scores.items():
        low, high = evidence.share_interval(score["accuracy"], len(truth))
        score.update({"from": low, "to": high})
        report = classification.report(truth, said[name], LABELS)
        score["classes"] = [each.model_dump() for each in report.classes]
    check = classification.mcnemar(truth, said["in use"], said["new"])
    by_market = {}
    for market, part in data.test.groupby("market"):
        rows = part.index.to_numpy()
        by_market[market] = {
            "headlines": len(rows),
            **{name: float(np.mean([said[name][i] == truth[i] for i in rows])) for name in said},
        }
    validation = kept["validation_after"]
    gap = validation["accuracy"] - scores["new"]["accuracy"]
    loss_gap = scores["new"]["loss"] - validation["loss"]
    better = scores["new"]["accuracy"] > scores["in use"]["accuracy"] and check.p_value < P_BELOW
    return _store(
        "test",
        {
            "headlines": len(truth),
            "from": str(data.test["created_at"].min()),
            "to": str(data.test["created_at"].max()),
            "scores": scores,
            "comparison": check.model_dump(),
            "by_market": by_market,
            "table": pd.crosstab(
                pd.Categorical(truth, LABELS), pd.Categorical(said["new"], LABELS), dropna=False
            )
            .to_numpy()
            .tolist(),
            "validation": validation,
            "accuracy_gap": gap,
            "loss_gap": loss_gap,
            "bars": {
                "better than the model in use": bool(better),
                "not overfitted": bool(gap <= ACCURACY_GAP and loss_gap <= LOSS_GAP),
            },
        },
    )


# --- baselines, for the tables ---


def store_baselines(data: Data) -> dict[str, Any]:
    """Score the two models that already exist on the three validation blocks, and store it.

    Neither is trained here and the test set is not read. Both read what they read in
    the app: the headline and the summary. `finbert-radar-1` was trained on headlines up
    to 2025-05-09, which is before the first block's validation part begins.
    """
    found = _stored("baselines")
    if found is not None:
        return found
    models: dict[str, Path | str] = {
        "finbert-radar-1 (in the app)": job.MODEL_DIR,
        "plain FinBERT, not trained further": sentiment.MODEL_ID,
    }
    out: dict[str, Any] = {}
    for name, model in models.items():
        rows = []
        for number, (_, validation) in enumerate(blocks(data), start=1):
            inputs = [
                sentiment.article_text(str(headline), str(summary or ""))
                for headline, summary in zip(
                    validation["headline"], validation["summary"], strict=True
                )
            ]
            scores = measure(validation["sentiment"].tolist(), _predict(model, inputs))
            rows.append({"block": number, **scores})
        out[name] = {"blocks": rows}
    return _store("baselines", out)
