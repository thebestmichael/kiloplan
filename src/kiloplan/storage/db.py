"""Database engine and sessions. SQLite by default; set KILOPLAN_DATABASE_URL to change it."""

import os
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session
from sqlalchemy.pool import ConnectionPoolEntry

from kiloplan.storage.models import Base

DEFAULT_URL = "sqlite:///data/kiloplan.db"


def create_db_engine(url: str) -> Engine:
    """An engine with the tables created. SQLite gets foreign keys switched on."""
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@cache
def get_engine() -> Engine:
    return create_db_engine(os.environ.get("KILOPLAN_DATABASE_URL", DEFAULT_URL))


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session
