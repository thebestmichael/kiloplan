"""Signing up test accounts."""

from fastapi.testclient import TestClient

from kiloplan.api.main import app


def sign_up(email="ben@example.com", name="Ben", password="correct horse"):
    """A separate browser, signed up and logged in."""
    client = TestClient(app)
    response = client.post(
        "/api/auth/signup", json={"email": email, "name": name, "password": password}
    )
    assert response.status_code == 200, response.text
    return client
