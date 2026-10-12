"""Alembic environment. The URL comes from the caller, else KILOPLAN_DATABASE_URL."""

import os

from alembic import context

from kiloplan.storage.db import DEFAULT_URL, connect
from kiloplan.storage.models import Base

url = context.config.get_main_option("sqlalchemy.url") or os.environ.get(
    "KILOPLAN_DATABASE_URL", DEFAULT_URL
)

with connect(url).connect() as connection:
    # batch mode lets SQLite alter tables, which it otherwise cannot
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
