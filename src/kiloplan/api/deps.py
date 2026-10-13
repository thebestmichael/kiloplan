"""Shared request dependencies."""

from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from kiloplan.storage import auth_store
from kiloplan.storage.db import get_session
from kiloplan.storage.models import Lifter, User
from kiloplan.storage.program_store import get_or_create_lifter

SESSION_COOKIE = "kiloplan_session"

DbSession = Annotated[Session, Depends(get_session)]


def current_user(
    session: DbSession, token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None
) -> User | None:
    """The logged-in user, from the session cookie."""
    return auth_store.user_for_token(session, token) if token else None


CurrentUser = Annotated[User | None, Depends(current_user)]


def current_lifter(session: DbSession, user: CurrentUser) -> Lifter:
    """Whose data a request reads and writes: the user's own, or the shared guest lifter.

    This is never taken from the request itself, so one account cannot name another's.
    """
    if user is not None:
        return user.lifter
    return get_or_create_lifter(session, auth_store.GUEST_LIFTER)


Owner = Annotated[Lifter, Depends(current_lifter)]
