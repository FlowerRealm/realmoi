from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .auth import decode_access_token
from .db import SessionLocal
from .models import User


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthorized", "message": "Missing token"}})

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthorized", "message": "Invalid token"}})

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail={"error": {"code": "unauthorized", "message": "Invalid token"}})

    user = db.get(User, user_id)
    if not user or user.is_disabled:
        raise HTTPException(status_code=403, detail={"error": {"code": "forbidden", "message": "User disabled"}})
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUserDep) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"error": {"code": "forbidden", "message": "Admin only"}})
    return user


AdminUserDep = Annotated[User, Depends(require_admin)]
