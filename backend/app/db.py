from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .settings import SETTINGS


engine = create_engine(
    f"sqlite:///{SETTINGS.db_path}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from .models import Base  # noqa: WPS433

    Base.metadata.create_all(bind=engine)
    _ensure_model_pricing_columns()


def _ensure_model_pricing_columns() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "model_pricing" not in table_names:
        return
    columns = {column["name"] for column in inspector.get_columns("model_pricing")}
    if "upstream_channel" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE model_pricing ADD COLUMN upstream_channel VARCHAR(64) NOT NULL DEFAULT ''"))
