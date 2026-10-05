"""Alembic environment. Run through `radar migrate`, which supplies the engine."""

from alembic import context
from sqlalchemy import Engine

from radar.db.models import Base
from radar.db.session import make_engine

target_metadata = Base.metadata


def run_migrations() -> None:
    engine: Engine = context.config.attributes.get("engine") or make_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
