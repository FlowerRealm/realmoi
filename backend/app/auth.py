from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
import bcrypt
from passlib.context import CryptContext

from .settings import SETTINGS


if not hasattr(bcrypt, "__about__") and hasattr(bcrypt, "__version__"):
    class _BcryptAbout:
        __version__ = bcrypt.__version__

    bcrypt.__about__ = _BcryptAbout()  # type: ignore[attr-defined]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, user_id: str, username: str, role: Literal["user", "admin"]) -> str:
    now = datetime.now(tz=timezone.utc)
    exp = now + timedelta(seconds=SETTINGS.jwt_ttl_seconds)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, SETTINGS.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SETTINGS.jwt_secret, algorithms=["HS256"])
