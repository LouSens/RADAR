"""Train the regime model, record it, and score every stored day.

Training fits the model on all history, measures it walk-forward, and writes a registry
row holding the parameters. Scoring applies the current model and stores filtered
probabilities. The API only ever reads the stored rows.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import ModelRegistry, RegimeState
from radar.db.session import session_scope
from radar.features.calendars import nyse_schedule
from radar.logging import get_logger
from radar.models import regime
from radar.pipelines.datasets import build_regime_observations
from radar.universe import Asset, Universe

log = get_logger(__name__)

MODEL_NAME = "regime"
ARTEFACT_ROOT = Path("data/models")
# MLflow retired its plain file store, so runs go to a local SQLite file in the same folder.
MLFLOW_DIR = Path("data/mlflow")
MLFLOW_URI = f"sqlite:///{MLFLOW_DIR.as_posix()}/mlflow.db"
BATCH = 2_000


def day_end(asset: Asset, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """When each observed day had ended, which is when its regime reading became known."""
    if asset.asset_class == "crypto":
        return days + pd.Timedelta(days=1)
    first = days.min().tz_localize("America/New_York").tz_convert("UTC")
    last = days.max().tz_localize("America/New_York").tz_convert("UTC") + pd.Timedelta(days=1)
    schedule = nyse_schedule(first, last)
    closes = pd.Series(pd.DatetimeIndex(schedule["close"]).tz_convert("UTC"), index=schedule.index)
    return pd.DatetimeIndex(closes.reindex(days))


def _log_to_mlflow(
    asset: Asset, model: regime.RegimeModel, metrics: dict[str, Any], artefact: Path, uri: str
) -> None:
    import mlflow

    MLFLOW_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(uri)
    if mlflow.get_experiment_by_name(MODEL_NAME) is None:
        mlflow.create_experiment(
            MODEL_NAME, artifact_location=(MLFLOW_DIR / "artifacts").resolve().as_uri()
        )
    mlflow.set_experiment(MODEL_NAME)
    with mlflow.start_run(run_name=f"{asset.symbol} {model.train_end}"):
        mlflow.log_params(
            {
                "symbol": asset.symbol,
                "version": model.version,
                "n_states": model.n_states,
                "train_start": str(model.train_start),
                "train_end": str(model.train_end),
                "n_train": model.n_train,
            }
        )
        numeric = {"bic": model.bic, "log_likelihood": model.log_likelihood}
        walk = metrics.get("walk_forward")
        if walk:
            numeric["wf_model_log_density"] = walk["model_log_density"]
            numeric["wf_baseline_log_density"] = walk["baseline_log_density"]
            numeric["wf_average_run_length"] = walk["average_run_length"]
        mlflow.log_metrics(numeric)
        mlflow.log_artifact(str(artefact))


def train(
    engine: Engine,
    asset: Asset,
    *,
    evaluate: bool = True,
    artefact_root: Path = ARTEFACT_ROOT,
    mlflow_uri: str | None = MLFLOW_URI,
    n_init: int = 5,
) -> int:
    """Fit, evaluate, and register a model for one asset. Returns the registry id."""
    with session_scope(engine) as session:
        observations = build_regime_observations(session, asset)
    model = regime.fit(observations, compare=regime.CANDIDATE_STATES, n_init=n_init)
    evaluation = regime.evaluate(observations, step=63, n_init=2) if evaluate else None
    metrics = regime.to_registry_metrics(model, evaluation)

    slug = asset.symbol.lower().replace("/", "-")
    artefact = artefact_root / MODEL_NAME / slug / f"{model.train_end}.json"
    regime.save(model, artefact)
    if mlflow_uri is not None:
        try:
            _log_to_mlflow(asset, model, metrics, artefact, mlflow_uri)
        except Exception as exc:
            # Experiment tracking is a record, not a dependency: the registry row below
            # is what the app uses.
            log.warning("mlflow_logging_failed", symbol=asset.symbol, error=type(exc).__name__)

    with session_scope(engine) as session:
        session.execute(
            update(ModelRegistry)
            .where(ModelRegistry.name == MODEL_NAME, ModelRegistry.symbol == asset.symbol)
            .values(is_current=False)
        )
        row = ModelRegistry(
            name=MODEL_NAME,
            symbol=asset.symbol,
            version=model.version,
            train_start=model.train_start,
            train_end=model.train_end,
            is_current=True,
            params=model.model_dump(mode="json"),
            metrics=metrics,
            artefact_path=str(artefact),
        )
        session.add(row)
        session.flush()
        model_id = row.id
    log.info("regime_trained", symbol=asset.symbol, model_id=model_id, days=model.n_train)
    return model_id


def current_model(session: Session, symbol: str) -> ModelRegistry | None:
    return session.scalars(
        select(ModelRegistry)
        .where(
            ModelRegistry.name == MODEL_NAME,
            ModelRegistry.symbol == symbol,
            ModelRegistry.is_current,
        )
        .order_by(ModelRegistry.trained_at.desc())
        .limit(1)
    ).first()


def score(engine: Engine, asset: Asset) -> int:
    """Store filtered probabilities for every day, using the current model.

    Returns the number of rows that changed; scoring the same data twice changes none.
    """
    with session_scope(engine) as session:
        registered = current_model(session, asset.symbol)
        if registered is None:
            return 0
        model = regime.RegimeModel.model_validate(registered.params)
        model_id = registered.id
        observations = build_regime_observations(session, asset)

    probabilities = regime.filtered_probabilities(model, observations)
    stamps = day_end(asset, pd.DatetimeIndex(probabilities.index))
    labels = probabilities.idxmax(axis=1).tolist()
    top = probabilities.max(axis=1).tolist()
    records = probabilities.round(6).to_dict("records")
    rows = [
        {
            "symbol": asset.symbol,
            "model_id": model_id,
            "ts": ts.to_pydatetime(),
            "label": label,
            "probability": float(probability),
            "probs": probs,
        }
        for ts, label, probability, probs in zip(stamps, labels, top, records, strict=True)
        if not pd.isna(ts)
    ]

    changed = 0
    with session_scope(engine) as session:
        for start in range(0, len(rows), BATCH):
            statement = insert(RegimeState).values(rows[start : start + BATCH])
            excluded = statement.excluded
            upsert = statement.on_conflict_do_update(
                index_elements=[RegimeState.symbol, RegimeState.model_id, RegimeState.ts],
                set_={
                    "label": excluded.label,
                    "probability": excluded.probability,
                    "probs": excluded.probs,
                },
                where=tuple_(RegimeState.label, RegimeState.probs).is_distinct_from(
                    tuple_(excluded.label, excluded.probs)
                ),
            ).returning(RegimeState.ts)
            changed += len(session.execute(upsert).all())
    log.info("regime_scored", symbol=asset.symbol, days=len(rows), changed=changed)
    return changed


def run(engine: Engine, universe: Universe, *, retrain: bool = False, evaluate: bool = True) -> int:
    """Train where there is no current model (or always, with `retrain`), then score."""
    from radar.pipelines import followed

    changed = 0
    for asset in followed.of(engine, universe):
        with session_scope(engine) as session:
            missing = current_model(session, asset.symbol) is None
        if retrain or missing:
            train(engine, asset, evaluate=evaluate)
        changed += score(engine, asset)
    return changed


def latest_training(session: Session, symbol: str) -> datetime | None:
    stamp: datetime | None = session.scalar(
        select(func.max(ModelRegistry.trained_at)).where(
            ModelRegistry.name == MODEL_NAME, ModelRegistry.symbol == symbol
        )
    )
    return stamp.astimezone(UTC) if stamp else None
