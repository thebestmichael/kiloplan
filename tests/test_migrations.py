from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from kiloplan.storage.db import connect, create_db_engine, migrate
from kiloplan.storage.models import Base, Lifter


def schema_differences(engine):
    with engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def test_migrations_build_the_same_schema_as_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    migrate(url)
    assert schema_differences(connect(url)) == []


def test_migrating_twice_changes_nothing(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    migrate(url)
    migrate(url)
    assert schema_differences(connect(url)) == []


def test_a_database_made_before_migrations_is_adopted_with_its_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_db_engine(url)
    with Session(engine) as session:
        session.add(Lifter(name="default"))
        session.commit()
    assert "alembic_version" not in inspect(engine).get_table_names()

    migrate(url)

    engine = connect(url)
    assert "alembic_version" in inspect(engine).get_table_names()
    with Session(engine) as session:
        assert session.scalars(select(Lifter.name)).all() == ["default"]
    assert schema_differences(engine) == []
