from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import sign_up
from kiloplan.api.deps import SESSION_COOKIE
from kiloplan.api.main import app
from kiloplan.storage import auth_store
from kiloplan.storage.models import AuthSession, Lifter, User

ANA = {"email": "ana@example.com", "name": "Ana", "password": "correct horse"}


def browser():
    return TestClient(app)


def test_sign_up_logs_the_browser_in():
    client = browser()
    assert client.get("/api/auth/me").json() == {"user": None}

    response = client.post("/api/auth/signup", json=ANA)
    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "ana@example.com", "name": "Ana"}
    assert client.get("/api/auth/me").json() == {"user": response.json()}

    # the cookie cannot be read by scripts, and another browser is still a guest
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert browser().get("/api/auth/me").json() == {"user": None}


def test_passwords_and_session_tokens_are_not_stored_as_they_are(session):
    client = sign_up(**ANA)
    user = session.scalars(select(User)).one()
    assert user.password_hash.startswith("$argon2")
    assert ANA["password"] not in user.password_hash
    stored = session.scalars(select(AuthSession)).one()
    assert stored.token_hash != client.cookies[SESSION_COOKIE]
    assert len(stored.token_hash) == 64


def test_log_in_and_log_out():
    sign_up(**ANA)
    client = browser()
    login = {"email": "ANA@example.com ", "password": ANA["password"]}
    # emails are matched without regard to case
    assert (
        client.post("/api/auth/login", json={**login, "email": "ANA@example.com"}).status_code
        == 200
    )
    assert client.get("/api/auth/me").json()["user"]["name"] == "Ana"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json() == {"user": None}
    # logging out twice is harmless
    assert client.post("/api/auth/logout").status_code == 204


def test_logging_out_ends_the_session_on_the_server(session):
    client = sign_up(**ANA)
    token = client.cookies[SESSION_COOKIE]
    client.post("/api/auth/logout")
    # a copy of the old cookie no longer works
    thief = browser()
    thief.cookies.set(SESSION_COOKIE, token)
    assert thief.get("/api/auth/me").json() == {"user": None}


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": "ana@example.com", "password": "wrong horse"},
        {"email": "nobody@example.com", "password": "correct horse"},
    ],
)
def test_wrong_credentials_get_the_same_answer(credentials):
    sign_up(**ANA)
    response = browser().post("/api/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password is incorrect."
    assert "set-cookie" not in response.headers


def test_an_email_can_only_be_used_once():
    sign_up(**ANA)
    again = browser().post("/api/auth/signup", json={**ANA, "email": "Ana@Example.com"})
    assert again.status_code == 409
    assert "already exists" in again.json()["detail"]


@pytest.mark.parametrize(
    "change",
    [{"email": "not-an-email"}, {"password": "short"}, {"name": ""}, {"email": "a b@example.com"}],
)
def test_sign_up_rejects_bad_details(change):
    assert browser().post("/api/auth/signup", json={**ANA, **change}).status_code == 422


def test_an_expired_session_is_a_guest_again(session):
    client = sign_up(**ANA)
    stored = session.scalars(select(AuthSession)).one()
    stored.expires_at -= auth_store.SESSION_LIFETIME + timedelta(minutes=1)
    session.commit()
    assert client.get("/api/auth/me").json() == {"user": None}


def test_a_made_up_cookie_is_a_guest():
    client = browser()
    client.cookies.set(SESSION_COOKIE, "not-a-real-token")
    assert client.get("/api/auth/me").json() == {"user": None}


def test_each_account_and_the_guest_have_separate_data(ben):
    guest = browser()
    ana = sign_up(**ANA)
    water = {"day": "2026-10-13", "ml": 500}
    for client, times in ((guest, 1), (ben, 2), (ana, 3)):
        for _ in range(times):
            client.post("/api/nutrition/water", json=water)

    def drunk(client):
        return client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()["water_ml"]

    assert (drunk(guest), drunk(ben), drunk(ana)) == (500, 1000, 1500)
    # logging out returns the browser to the guest's data
    ana.post("/api/auth/logout")
    assert drunk(ana) == 500


def test_a_request_cannot_name_another_lifter(ben):
    ben.post("/api/nutrition/water", json={"day": "2026-10-13", "ml": 750})
    guest = browser()
    # the old `lifter` parameter is ignored wherever it is sent
    day = guest.get("/api/nutrition/diary", params={"day": "2026-10-13", "lifter": "user-1"}).json()
    assert day["water_ml"] == 0
    guest.post("/api/nutrition/water", json={"day": "2026-10-13", "ml": 100, "lifter": "user-1"})
    assert ben.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()["water_ml"] == 750


def test_the_first_account_takes_over_what_the_guest_entered(session):
    guest = browser()
    guest.post("/api/nutrition/water", json={"day": "2026-10-13", "ml": 900})
    guest.put("/api/nutrition/bodyweight", json={"bodyweight_kg": 92})

    ana = sign_up(**ANA)
    mine = ana.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert (mine["water_ml"], mine["bodyweight_kg"]) == (900, 92)
    # the guest starts again from nothing
    assert guest.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()["water_ml"] == 0

    # a second account does not take over the guest's data
    guest.post("/api/nutrition/water", json={"day": "2026-10-13", "ml": 300})
    second = sign_up(email="cy@example.com", name="Cy")
    assert second.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()["water_ml"] == 0
    assert sorted(lifter.name for lifter in session.scalars(select(Lifter))) == [
        "default",
        "user-1",
        "user-2",
    ]
