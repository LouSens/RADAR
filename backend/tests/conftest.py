"""Shared fixtures. Database tests run against a throwaway database on the dev server.

They are skipped when no database is configured or reachable, unless
`RADAR_REQUIRE_DB=1` (set in CI), in which case that is a failure.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from radar.config import load_settings
from radar.db.session import make_engine, session_scope, upgrade

TEST_DATABASE = "radar_test"


def _unavailable(reason: str) -> None:
    if os.environ.get("RADAR_REQUIRE_DB") == "1":
        pytest.fail(f"Database required but unavailable: {reason}")
    pytest.skip(f"Database unavailable: {reason}")


@pytest.fixture(scope="session")
def empty_engine() -> Iterator[Engine]:
    """An engine on a freshly created, empty test database."""
    settings = load_settings()
    try:
        admin_url = settings.database_url()
    except RuntimeError as exc:
        _unavailable(str(exc))
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
    except OperationalError as exc:
        _unavailable(type(exc.orig).__name__)
    engine = make_engine(settings.database_url(TEST_DATABASE))
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def engine(empty_engine: Engine) -> Engine:
    """The test database with every migration applied."""
    upgrade(empty_engine)
    return empty_engine


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session on clean tables: every table is emptied before the test."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE bars, news_symbols, news_articles, ingestion_runs,"
                " data_quality_reports, assets RESTART IDENTITY CASCADE"
            )
        )
    with session_scope(engine) as db:
        yield db
