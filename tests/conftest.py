import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import sign_up
from kiloplan.api.main import app
from kiloplan.ingestion.usda import load_foods, read_foods
from kiloplan.storage.db import create_db_engine, get_session
from kiloplan.storage.models import Food
from usda_data import write_usda_zip


@pytest.fixture
def engine(tmp_path):
    return create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def api_uses_test_database(request):
    """Every API request in a test gets a session on that test's own database."""

    def override():
        # created on first use, so tests that never touch the database stay fast
        with Session(request.getfixturevalue("engine")) as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def ben():
    """Another lifter with their own account, created before the test adds any data."""
    return sign_up()


@pytest.fixture
def usda_zip(tmp_path):
    """A small USDA archive on disk."""
    return write_usda_zip(tmp_path / "foods.zip")


@pytest.fixture
def foods(usda_zip, session):
    """The archive's foods loaded into the database, as {name: id}."""
    load_foods(session, read_foods(usda_zip))
    session.commit()
    return {food.name: food.id for food in session.scalars(select(Food))}
