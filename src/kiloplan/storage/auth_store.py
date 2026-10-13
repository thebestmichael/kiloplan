"""Accounts and login sessions.

Passwords are hashed with Argon2. A session is a random token kept in the browser's
cookie; the database holds only its SHA-256 hash, so a leaked database cannot be used
to log in.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kiloplan.storage.models import AuthSession, Lifter, User

GUEST_LIFTER = "default"
SESSION_LIFETIME = timedelta(days=30)

_hasher = PasswordHasher()


class EmailTakenError(ValueError):
    """An account with this email already exists."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    # stored without a timezone, so compared without one
    return datetime.now(UTC).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(session: Session, email: str, name: str, password: str) -> User:
    """Create an account with its own lifter.

    The very first account takes over the guest lifter, so data entered before
    accounts existed is not left behind.
    """
    email = normalise_email(email)
    if session.scalar(select(User).where(User.email == email)):
        raise EmailTakenError("An account with this email already exists.")
    user = User(email=email, name=name.strip(), password_hash=_hasher.hash(password))

    is_first = session.scalar(select(func.count()).select_from(User)) == 0
    guest = session.scalar(select(Lifter).where(Lifter.name == GUEST_LIFTER))
    # a placeholder name until the user's id is known
    lifter = guest if is_first and guest else Lifter(name=f"pending-{secrets.token_hex(8)}")
    user.lifter = lifter
    session.add(user)
    session.flush()
    lifter.name = f"user-{user.id}"
    session.flush()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    """The user for these credentials, or None. Never says which part was wrong."""
    user = session.scalar(select(User).where(User.email == normalise_email(email)))
    if user is None:
        return None
    try:
        _hasher.verify(user.password_hash, password)
    except (VerificationError, InvalidHashError):
        return None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
    return user


def start_session(session: Session, user: User) -> str:
    """Log a browser in. Returns the token to put in its cookie."""
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=_token_hash(token), user_id=user.id, expires_at=_now() + SESSION_LIFETIME
        )
    )
    session.flush()
    return token


def user_for_token(session: Session, token: str) -> User | None:
    stored = session.get(AuthSession, _token_hash(token))
    if stored is None or stored.expires_at <= _now():
        return None
    return stored.user


def end_session(session: Session, token: str) -> None:
    stored = session.get(AuthSession, _token_hash(token))
    if stored is not None:
        session.delete(stored)
