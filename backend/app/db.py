"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    """Create all tables if they do not exist."""
    import app.models  # noqa: F401  ensure models are registered

    SQLModel.metadata.create_all(engine)
    _ensure_risk_score_columns()


def _ensure_risk_score_columns() -> None:
    """Backfill additive risk_scores columns for existing SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    columns = {col["name"] for col in inspect(engine).get_columns("risk_scores")}
    with engine.begin() as conn:
        if "raw_score" not in columns:
            conn.execute(text("ALTER TABLE risk_scores ADD COLUMN raw_score FLOAT NOT NULL DEFAULT 0.0"))
        if "prev_cycle_outstanding_days" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE risk_scores "
                    "ADD COLUMN prev_cycle_outstanding_days FLOAT NOT NULL DEFAULT 0.0"
                )
            )


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    with Session(engine) as session:
        yield session
