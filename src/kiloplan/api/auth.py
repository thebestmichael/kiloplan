"""Sign up, log in, log out and the current user."""

import os
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field

from kiloplan.api.deps import SESSION_COOKIE, CurrentUser, DbSession
from kiloplan.storage import auth_store
from kiloplan.storage.models import User

router = APIRouter(prefix="/api/auth")

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MIN_PASSWORD_LENGTH = 8


class UserOut(BaseModel):
    id: int
    email: str
    name: str


class Credentials(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=200)


class SignupRequest(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)


def _log_in(response: Response, session: DbSession, user: User) -> None:
    token = auth_store.start_session(session, user)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(auth_store.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        # set KILOPLAN_COOKIE_SECURE=1 wherever the app is served over HTTPS
        secure=os.environ.get("KILOPLAN_COOKIE_SECURE") == "1",
    )


@router.post("/signup")
def sign_up(request: SignupRequest, response: Response, session: DbSession) -> UserOut:
    try:
        user = auth_store.create_user(session, request.email, request.name, request.password)
    except auth_store.EmailTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    _log_in(response, session, user)
    session.commit()
    return _user_out(user)


@router.post("/login")
def log_in(request: Credentials, response: Response, session: DbSession) -> UserOut:
    user = auth_store.authenticate(session, request.email, request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    _log_in(response, session, user)
    session.commit()
    return _user_out(user)


@router.post("/logout", status_code=204)
def log_out(
    response: Response,
    session: DbSession,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if token:
        auth_store.end_session(session, token)
        session.commit()
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
def me(user: CurrentUser) -> dict[str, UserOut | None]:
    return {"user": _user_out(user) if user else None}
