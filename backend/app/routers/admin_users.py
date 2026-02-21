from __future__ import annotations

"""Admin user management endpoints."""

import re
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from ..auth import hash_password
from ..deps import AdminUserDep, DbDep
from ..models import User
from ..utils.errors import http_error
from .admin_common import commit_db, refresh_db


router = APIRouter()

# 管理员用户管理接口。
# - GET  /users: 列表（可按 username/role/is_disabled 过滤，支持分页）
# - POST /users: 创建用户（username/password/role/is_disabled）
# - PATCH /users/{id}: 修改 role/is_disabled（保证至少保留 1 个活跃 admin）
# - POST /users/{id}/reset_password: 重置密码
#
# 备注：该文件是 router 层，负责输入校验与 DB 写入边界处理。

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class UserItem(BaseModel):
    id: str
    username: str
    role: str
    is_disabled: bool
    created_at: datetime


class UsersListResponse(BaseModel):
    items: list[UserItem]
    total: int


class ListUsersParams(BaseModel):
    q: str | None = None
    role: str | None = None
    is_disabled: bool | None = None
    limit: int = 50
    offset: int = 0


def get_list_users_params(
    q: str | None = None,
    role: str | None = None,
    is_disabled: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ListUsersParams:
    return ListUsersParams(q=q, role=role, is_disabled=is_disabled, limit=limit, offset=offset)


@router.get("/users", response_model=UsersListResponse)
def list_users(
    _: AdminUserDep,
    db: DbDep,
    params: ListUsersParams = Depends(get_list_users_params),
):
    """List users (admin-only) with optional filters and pagination."""
    stmt = select(User).order_by(User.created_at.desc())
    if params.q:
        stmt = stmt.where(User.username.like(f"%{params.q}%"))
    if params.role:
        role_key = params.role.strip()
        if role_key not in ("user", "admin"):
            http_error(422, "invalid_request", "Invalid role")
        stmt = stmt.where(User.role == role_key)
    if params.is_disabled is not None:
        stmt = stmt.where(User.is_disabled == params.is_disabled)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.limit(params.limit).offset(params.offset)).all()
    return UsersListResponse(
        items=[UserItem.model_validate(u, from_attributes=True) for u in items],
        total=total,
    )


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    is_disabled: bool = False


@router.post("/users", response_model=UserItem, status_code=201)
def create_user(_: AdminUserDep, db: DbDep, req: CreateUserRequest):
    """Create a new user (admin-only)."""
    username = req.username.strip()
    if not USERNAME_RE.match(username):
        http_error(422, "invalid_request", "Invalid username")
    if not (8 <= len(req.password) <= 72):
        http_error(422, "invalid_request", "Invalid password length")

    role_key = (req.role or "user").strip() or "user"
    if role_key not in ("user", "admin"):
        http_error(422, "invalid_request", "Invalid role")

    exists = db.scalar(select(User).where(User.username == username))
    if exists:
        http_error(409, "conflict", "Username already exists")

    user = User(
        username=username,
        password_hash=hash_password(req.password),
        role=role_key,
        is_disabled=bool(req.is_disabled),
    )
    db.add(user)
    commit_db(db)
    refresh_db(db, user)
    return UserItem.model_validate(user, from_attributes=True)


class PatchUserRequest(BaseModel):
    is_disabled: bool | None = None
    role: str | None = None


@router.patch("/users/{user_id}")
def patch_user(admin: AdminUserDep, db: DbDep, user_id: str, req: PatchUserRequest):
    """Patch user role/disabled flags (admin-only)."""
    user = db.get(User, user_id)
    if not user:
        http_error(404, "not_found", "User not found")

    if user.id == admin.id and req.is_disabled:
        http_error(409, "conflict", "Cannot disable yourself")

    if req.role and req.role not in ("user", "admin"):
        http_error(422, "invalid_request", "Invalid role")

    # Ensure at least one active admin.
    if (req.role == "user" or req.is_disabled is True) and user.role == "admin" and not user.is_disabled:
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(and_(User.role == "admin", User.is_disabled == False))  # noqa: E712
        )
        if (active_admins or 0) <= 1:
            http_error(409, "conflict", "Must keep at least one active admin")

    if req.is_disabled is not None:
        user.is_disabled = req.is_disabled
    if req.role is not None:
        user.role = req.role
    db.add(user)
    commit_db(db)
    return {"ok": True}


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset_password")
def reset_password(_: AdminUserDep, db: DbDep, user_id: str, req: ResetPasswordRequest):
    """Reset user password (admin-only)."""
    if not (8 <= len(req.new_password) <= 72):
        http_error(422, "invalid_request", "Invalid password length")
    user = db.get(User, user_id)
    if not user:
        http_error(404, "not_found", "User not found")
    user.password_hash = hash_password(req.new_password)
    db.add(user)
    commit_db(db)
    return {"ok": True}
