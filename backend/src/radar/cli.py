"""The `radar` command. Every Makefile target calls one of these subcommands."""

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from radar.logging import configure_logging, get_logger

log = get_logger(__name__)

# Commands that exist in the Makefile but are built in a later phase.
NOT_YET: dict[str, str] = {
    "demo": "Phase 7",
}


def _run(*commands: Sequence[str]) -> int:
    """Run each command in order and return the first non-zero exit code."""
    for command in commands:
        code = subprocess.run(command, check=False).returncode  # noqa: S603
        if code != 0:
            return code
    return 0


def _npm(*args: str) -> list[str]:
    # npm is a .cmd shim on Windows, which needs the shell to resolve it.
    npm = shutil.which("npm") or "npm"
    return [npm, "--prefix", "frontend", *args]


def _has_frontend() -> bool:
    return Path("frontend/node_modules").is_dir()


def lint() -> int:
    py = sys.executable
    commands: list[Sequence[str]] = [
        [py, "-m", "ruff", "check", "."],
        [py, "-m", "ruff", "format", "--check", "."],
        [py, "-m", "mypy"],
    ]
    if _has_frontend():
        commands += [_npm("run", "lint"), _npm("run", "typecheck")]
    else:
        log.warning("frontend_skipped", hint="run `npm --prefix frontend ci` to include it")
    return _run(*commands)


def test() -> int:
    commands: list[Sequence[str]] = [[sys.executable, "-m", "pytest"]]
    if _has_frontend():
        commands.append(_npm("test"))
    else:
        log.warning("frontend_skipped", hint="run `npm --prefix frontend ci` to include it")
    return _run(*commands)


def up() -> int:
    return _run(["docker", "compose", "up", "-d", "--wait"])


def down() -> int:
    return _run(["docker", "compose", "down"])


def migrate() -> int:
    """Apply database migrations, then sync the assets table with the universe."""
    from radar.db.assets import sync_assets
    from radar.db.session import make_engine, session_scope, upgrade
    from radar.universe import get_universe

    engine = make_engine()
    upgrade(engine)
    with session_scope(engine) as session:
        count = sync_assets(session, get_universe())
    log.info("migrated", assets=count)
    return 0


def backfill(args: argparse.Namespace) -> int:
    """Fetch history for the universe into the raw layer and the database."""
    from radar.config import load_settings
    from radar.db.session import make_engine
    from radar.ingest.backfill import Backfill
    from radar.ingest.raw_store import RawStore
    from radar.providers.alpaca_rest import AlpacaDataClient
    from radar.universe import get_universe

    settings = load_settings()
    if settings.alpaca_api_key_id is None or settings.alpaca_api_secret_key is None:
        log.error("missing_alpaca_keys", hint="copy .env.example to .env and fill in paper keys")
        return 1
    with AlpacaDataClient(settings.alpaca_api_key_id, settings.alpaca_api_secret_key) as client:
        client.on_page = RawStore().record
        job = Backfill(client, make_engine(settings=settings), get_universe())
        result = job.run(bars=not args.skip_bars, news=not args.skip_news)
    log.info(
        "backfill_finished",
        rows_changed=result.rows_changed,
        windows_fetched=result.windows_fetched,
        windows_skipped=result.windows_skipped,
        bars_rejected=result.bars_rejected,
        failures=len(result.failures),
    )
    return 1 if result.failures else 0


def quality() -> int:
    """Check stored data, set flags, and write data quality reports."""
    from radar.db.session import make_engine
    from radar.pipelines.quality import run_quality
    from radar.universe import get_universe

    findings = run_quality(make_engine(), get_universe())
    return 1 if any(f.status == "fail" for f in findings) else 0


def worker() -> int:
    """Run the live streams and the scheduled jobs until stopped."""
    from radar.pipelines.worker import run_worker

    return run_worker()


def profile() -> int:
    """Measure the stored data and write docs/DATA_PROFILE.md."""
    from radar.db.session import make_engine
    from radar.pipelines.profile import write_profile
    from radar.universe import get_universe

    write_profile(make_engine(), get_universe())
    return 0


def api() -> int:
    """Serve the HTTP API and the live WebSocket."""
    import uvicorn

    from radar.api.app import create_app
    from radar.config import load_settings

    settings = load_settings()
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port, log_config=None)
    return 0


def openapi(args: argparse.Namespace) -> int:
    """Write the API schema, which generates the frontend's types. Needs no database."""
    import json
    from pathlib import Path

    from sqlalchemy import create_engine

    from radar.api.app import create_app
    from radar.universe import get_universe

    # The engine is never connected: building the schema only inspects the routes.
    app = create_app(create_engine("postgresql+psycopg://"), get_universe())
    text = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    Path(args.output).write_text(text, encoding="utf-8", newline="\n")
    return 0


def regime(args: argparse.Namespace) -> int:
    """Train the regime model where needed, then score every stored day."""
    from radar.db.session import make_engine
    from radar.pipelines import regime as job
    from radar.universe import get_universe

    changed = job.run(
        make_engine(), get_universe(), retrain=args.retrain, evaluate=not args.skip_evaluation
    )
    log.info("regime_done", rows_changed=changed)
    return 0


def simulate(args: argparse.Namespace) -> int:
    """Measure the simulator's past ranges where needed, then store today's run."""
    from radar.db.session import make_engine
    from radar.pipelines import simulation as job
    from radar.universe import get_universe

    changed = job.run(make_engine(), get_universe(), recalibrate=args.recalibrate)
    log.info("simulate_done", rows_changed=changed)
    return 0


def volatility() -> int:
    """Forecast volatility for every day not yet covered, and score the models."""
    from radar.db.session import make_engine
    from radar.pipelines import volatility as job
    from radar.universe import get_universe

    changed = job.run(make_engine(), get_universe())
    log.info("volatility_done", rows_changed=changed)
    return 0


def risk() -> int:
    """Estimate tail risk for every day not yet covered, and backtest each method."""
    from radar.db.session import make_engine
    from radar.pipelines import risk as job
    from radar.universe import get_universe

    changed = job.run(make_engine(), get_universe())
    log.info("risk_done", rows_changed=changed)
    return 0


def sentiment() -> int:
    """Score new articles for tone (needs the nlp extra), refresh the summaries, measure
    accuracy against the labelled sample, and rerun the sentiment-versus-price study."""
    from radar.db.session import make_engine
    from radar.models.lexicon import DEFAULT_PATH, Lexicon
    from radar.pipelines import event_study
    from radar.pipelines import sentiment as job
    from radar.universe import get_universe

    engine, universe = make_engine(), get_universe()
    changed = job.run(engine, universe, job.load_scorer(engine))
    topic_scorer = job.load_topic_scorer()
    if topic_scorer is not None:
        changed += job.classify_articles(engine, topic_scorer)
    if DEFAULT_PATH.is_file():
        job.evaluate(engine, lexicon=Lexicon.load())
    else:
        log.warning("word_list_missing", path=str(DEFAULT_PATH))
        job.evaluate(engine)
    studies = event_study.run(engine, universe)
    log.info("sentiment_done", rows_changed=changed, studies=studies)
    return 0


def finetune() -> int:
    """Fine-tune the sentiment model on the labelled headlines and test it (needs nlp)."""
    from radar.db.session import make_engine
    from radar.models.lexicon import DEFAULT_PATH, Lexicon
    from radar.pipelines import finetune as job

    lexicon = Lexicon.load() if DEFAULT_PATH.is_file() else None
    metrics = job.run(make_engine(), lexicon=lexicon)
    log.info("finetune_done", adopted=metrics["adopted"], reason=metrics["reason"])
    return 0


def track() -> int:
    """Write down today's forecasts and score the ones whose days have ended."""
    from radar.db.session import make_engine
    from radar.pipelines import track as job
    from radar.universe import get_universe

    changed = job.run(make_engine(), get_universe())
    log.info("track_done", rows_changed=changed)
    return 0


def portfolio() -> int:
    """Recompute the stored analysis of the saved holdings with the latest prices."""
    from radar.db.session import make_engine
    from radar.pipelines import portfolio as job
    from radar.universe import get_universe

    universe = get_universe()
    engine = make_engine()
    stored = job.run(engine, universe, job.binance_reader(), job.asset_finder(engine))
    log.info("portfolio_done", analyses_stored=stored)
    return 0


def relationships() -> int:
    """Recompute how the markets move together, and each market's macro drivers."""
    from radar.db.session import make_engine
    from radar.pipelines import relationships as job
    from radar.universe import get_universe

    stored = job.run(make_engine(), get_universe())
    log.info("relationships_done", rows_stored=stored)
    return 0


def news_swings() -> int:
    """Test whether news improves the swings forecast, and store the verdict."""
    from radar.db.session import make_engine
    from radar.pipelines import news_volatility as job
    from radar.universe import get_universe

    stored = job.run(make_engine(), get_universe())
    log.info("news_swings_done", markets=stored)
    return 0


def audit(args: argparse.Namespace) -> int:
    from radar.pipelines.audit import run_audit

    return run_audit(
        news_start_year=args.news_start_year,
        skip_news=args.skip_news,
        skip_streams=args.skip_streams,
        render_only=args.render_only,
        resume=args.resume,
    )


COMMANDS: dict[str, tuple[Callable[[], int], str]] = {
    "lint": (lint, "run ruff, mypy, eslint, and tsc"),
    "test": (test, "run the backend and frontend tests"),
    "up": (up, "start the containers with docker compose"),
    "down": (down, "stop the containers"),
    "quality": (quality, "check stored data and write data quality reports"),
    "worker": (worker, "run live ingestion and scheduled jobs"),
    "profile": (profile, "measure the stored data and write docs/DATA_PROFILE.md"),
    "api": (api, "serve the HTTP API and live WebSocket"),
    "volatility": (volatility, "forecast volatility and score the models"),
    "risk": (risk, "estimate tail risk and backtest each method"),
    "sentiment": (sentiment, "score news for tone and refresh the summaries"),
    "finetune": (finetune, "fine-tune the sentiment model and test it on held-out headlines"),
    "track": (track, "log today's forecasts and score those that have come due"),
    "portfolio": (portfolio, "recompute the portfolio analysis with the latest prices"),
    "relationships": (relationships, "recompute how the markets move together"),
    "news-swings": (news_swings, "test whether news improves the swings forecast"),
    "migrate": (migrate, "apply database migrations and sync the asset universe"),
}


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    audit_parser = sub.add_parser("audit", help="probe the live data API, write docs/DATA_AUDIT.md")
    audit_parser.add_argument("--news-start-year", type=int, default=2015)
    audit_parser.add_argument("--skip-news", action="store_true", help="skip the long news scan")
    audit_parser.add_argument("--skip-streams", action="store_true", help="skip WebSocket probes")
    audit_parser.add_argument(
        "--render-only", action="store_true", help="rebuild the report from the last saved results"
    )
    audit_parser.add_argument(
        "--resume", action="store_true", help="keep saved sections and run only the missing ones"
    )
    regime_parser = sub.add_parser("regime", help="train and score the regime model")
    regime_parser.add_argument("--retrain", action="store_true", help="fit a new model first")
    regime_parser.add_argument(
        "--skip-evaluation", action="store_true", help="skip the walk-forward evaluation"
    )
    simulate_parser = sub.add_parser("simulate", help="run the outcome simulator and store it")
    simulate_parser.add_argument(
        "--recalibrate", action="store_true", help="measure past ranges again first (minutes)"
    )
    openapi_parser = sub.add_parser("openapi", help="write the API schema for the frontend")
    openapi_parser.add_argument("--output", default="frontend/openapi.json")
    backfill_parser = sub.add_parser("backfill", help="fetch history for the universe")
    backfill_parser.add_argument("--skip-bars", action="store_true")
    backfill_parser.add_argument("--skip-news", action="store_true")
    for name, phase in NOT_YET.items():
        sub.add_parser(name, help=f"not built yet ({phase})")
    args = parser.parse_args(argv)

    command: str = args.command
    if command == "audit":
        return audit(args)
    if command == "backfill":
        return backfill(args)
    if command == "openapi":
        return openapi(args)
    if command == "regime":
        return regime(args)
    if command == "simulate":
        return simulate(args)
    if command in NOT_YET:
        log.error("command_not_built_yet", command=command, arrives_in=NOT_YET[command])
        return 2
    return COMMANDS[command][0]()


if __name__ == "__main__":
    sys.exit(main())
