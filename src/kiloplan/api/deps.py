"""Shared request dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from kiloplan.storage.db import get_session

DEFAULT_LIFTER = "default"

DbSession = Annotated[Session, Depends(get_session)]
