"""Database engine and sessions. SQLite by default; set KILOPLAN_DATABASE_URL to change it.

The application database is built and upgraded by the Alembic migrations in
`migrations/`. Tests build theirs straight from the models, and a test checks that the
two give the same schema.
"""

import os
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from kiloplan.storage.models import Base

DEFAULT_URL = "sqlite:///data/kiloplan.db"
MIGRATIONS = Path(__file__).parent / "migrations"
BASELINE_REVISION = "0001"


def connect(url: str) -> Engine:
    """An engine with no tables created. SQLite gets foreign keys switched on."""
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def create_db_engine(url: str) -> Engine:
    """An engine with the tables created from the models, without migrations."""
    engine = connect(url)
    Base.metadata.create_all(engine)
    return engine


def migrate(url: str, revision: str = "head") -> None:
    """Bring a database up to a schema revision, the newest by default.

    A database made before migrations existed has the baseline tables but no version
    mark, so it is marked as the baseline first.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    engine = connect(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    if "lifters" in tables and "alembic_version" not in tables:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, revision)


@cache
def get_engine() -> Engine:
    url = os.environ.get("KILOPLAN_DATABASE_URL", DEFAULT_URL)
    migrate(url)
    return connect(url)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session
