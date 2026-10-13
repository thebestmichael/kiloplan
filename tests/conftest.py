import pytest
from sqlalchemy.orm import Session

from kiloplan.api.main import app
from kiloplan.storage.db import create_db_engine, get_session


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
