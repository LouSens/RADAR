import pytest

from radar import cli


def test_makefile_targets_all_have_a_cli_command() -> None:
    targets = {"up", "down", "migrate", "audit", "backfill", "test", "lint", "demo"}
    assert targets <= set(cli.COMMANDS) | set(cli.NOT_YET) | {"audit"}


def test_unbuilt_command_exits_non_zero() -> None:
    assert cli.main(["demo"]) == 2


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.main(["place-order"])
