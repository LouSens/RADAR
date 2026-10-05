"""The `radar` command. Every Makefile target calls one of these subcommands."""

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

from radar.logging import configure_logging, get_logger

log = get_logger(__name__)

# Commands that exist in the Makefile but are built in a later phase.
NOT_YET: dict[str, str] = {
    "worker": "Phase 1",
    "api": "Phase 2",
    "demo": "Phase 7",
}


def _run(*commands: Sequence[str]) -> int:
    """Run each command in order and return the first non-zero exit code."""
    for command in commands:
        code = subprocess.run(command, check=False).returncode  # noqa: S603
        if code != 0:
            return code
    return 0


def lint() -> int:
    py = sys.executable
    return _run(
        [py, "-m", "ruff", "check", "."],
        [py, "-m", "ruff", "format", "--check", "."],
        [py, "-m", "mypy"],
    )


def test() -> int:
    return _run([sys.executable, "-m", "pytest"])


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
        failures=len(result.failures),
    )
    return 1 if result.failures else 0


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
    "lint": (lint, "run ruff and mypy"),
    "test": (test, "run the backend tests"),
    "up": (up, "start the containers with docker compose"),
    "down": (down, "stop the containers"),
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
    if command in NOT_YET:
        log.error("command_not_built_yet", command=command, arrives_in=NOT_YET[command])
        return 2
    return COMMANDS[command][0]()


if __name__ == "__main__":
    sys.exit(main())
