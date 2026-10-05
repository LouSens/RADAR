"""The `radar` command. Every Makefile target calls one of these subcommands."""

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

from radar.logging import configure_logging, get_logger

log = get_logger(__name__)

# Commands that exist in the Makefile but are built in a later phase.
NOT_YET: dict[str, str] = {
    "audit": "Phase 0, step 4",
    "migrate": "Phase 1",
    "backfill": "Phase 1",
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


COMMANDS: dict[str, tuple[Callable[[], int], str]] = {
    "lint": (lint, "run ruff and mypy"),
    "test": (test, "run the backend tests"),
    "up": (up, "start the containers with docker compose"),
    "down": (down, "stop the containers"),
}


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    for name, phase in NOT_YET.items():
        sub.add_parser(name, help=f"not built yet ({phase})")
    args = parser.parse_args(argv)

    command: str = args.command
    if command in NOT_YET:
        log.error("command_not_built_yet", command=command, arrives_in=NOT_YET[command])
        return 2
    return COMMANDS[command][0]()


if __name__ == "__main__":
    sys.exit(main())
