from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[Literal["user", "admin"]] = mapped_column(String(16), nullable=False, default="user")
    is_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    codex_settings: Mapped["UserCodexSettings | None"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserCodexSettings(Base):
    __tablename__ = "user_codex_settings"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    overrides_toml: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="codex_settings")


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    model: Mapped[str] = mapped_column(String(128), primary_key=True)
    upstream_channel: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="microusd_per_1m_tokens")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    input_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_output_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class UpstreamChannel(Base):
    __tablename__ = "upstream_channels"

    channel: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    models_path: Mapped[str] = mapped_column(String(128), nullable=False, default="/v1/models")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="generate")
    model: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    codex_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    # Pricing snapshot (microusd per 1m tokens). Nullable: pricing may be missing.
    input_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_output_microusd_per_1m_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_microusd: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
