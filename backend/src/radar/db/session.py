"""Database engine, sessions, and migrations."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from radar.config import Settings, load_settings

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def make_engine(url: URL | None = None, settings: Settings | None = None) -> Engine:
    url = url or (settings or load_settings()).database_url()
    # The server and every session work in UTC, whatever the host's zone is.
    return create_engine(url, connect_args={"options": "-c timezone=utc"}, pool_pre_ping=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A session that commits on success and rolls back on error."""
    session = sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def alembic_config(engine: Engine) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["engine"] = engine
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    command.upgrade(alembic_config(engine), revision)


def downgrade(engine: Engine, revision: str) -> None:
    command.downgrade(alembic_config(engine), revision)
