from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_access_token, hash_password, verify_password
from ..deps import CurrentUserDep, DbDep
from ..models import User
from ..settings import SETTINGS
from ..utils.errors import http_error


router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserOut


@router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest, db: DbDep):
    if not SETTINGS.allow_signup:
        http_error(403, "signup_disabled", "Signup disabled")

    username = req.username.strip()
    if not USERNAME_RE.match(username):
        http_error(422, "invalid_request", "Invalid username")
    if not (8 <= len(req.password) <= 72):
        http_error(422, "invalid_request", "Invalid password length")

    exists = db.scalar(select(User).where(User.username == username))
    if exists:
        http_error(409, "conflict", "Username already exists")

    user = User(username=username, password_hash=hash_password(req.password), role="user", is_disabled=False)
    db.add(user)
    db.commit()

    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenResponse(access_token=token, user=UserOut(id=user.id, username=user.username, role=user.role))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: DbDep):
    username = req.username.strip()
    user: User | None = db.scalar(select(User).where(User.username == username))
    if not user or not verify_password(req.password, user.password_hash):
        http_error(401, "unauthorized", "Invalid credentials")
    if user.is_disabled:
        http_error(403, "forbidden", "User disabled")

    token = create_access_token(user_id=user.id, username=user.username, role=user.role)
    return TokenResponse(access_token=token, user=UserOut(id=user.id, username=user.username, role=user.role))


class MeResponse(BaseModel):
    id: str
    username: str
    role: str
    is_disabled: bool


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUserDep):
    return MeResponse(id=user.id, username=user.username, role=user.role, is_disabled=user.is_disabled)

