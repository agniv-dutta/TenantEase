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
    _ensure_unit_columns()
    _ensure_audit_event_columns()


def _ensure_unit_columns() -> None:
    """Add unit vacancy fields to databases created by earlier demo versions."""
    if not str(engine.url).startswith("sqlite"):
        return
    columns = {col["name"] for col in inspect(engine).get_columns("units")}
    with engine.begin() as conn:
        if "status" not in columns:
            conn.execute(
                text("ALTER TABLE units ADD COLUMN status VARCHAR NOT NULL DEFAULT 'occupied'")
            )
        if "vacant_since" not in columns:
            conn.execute(text("ALTER TABLE units ADD COLUMN vacant_since DATE"))


def _ensure_audit_event_columns() -> None:
    """Upgrade the earlier payment-only audit table to the structured schema."""
    if not str(engine.url).startswith("sqlite"):
        return
    columns = {col["name"] for col in inspect(engine).get_columns("audit_events")}
    with engine.begin() as conn:
        if "event_type" in columns:
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update"))
            conn.execute(text("DROP TRIGGER IF EXISTS audit_events_no_delete"))
            conn.execute(text("ALTER TABLE audit_events RENAME TO audit_events_legacy"))
            conn.execute(
                text(
                    "CREATE TABLE audit_events ("
                    "id INTEGER PRIMARY KEY, at DATETIME NOT NULL, actor VARCHAR NOT NULL, "
                    "kind VARCHAR NOT NULL, lease_id INTEGER, summary VARCHAR NOT NULL, "
                    "details JSON NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO audit_events (id, at, actor, kind, lease_id, summary, details) "
                    "SELECT id, created_at, 'demo manager', 'payment_recorded', lease_id, "
                    "'Recorded payment for lease ' || COALESCE(lease_id, 'unknown'), detail_json "
                    "FROM audit_events_legacy WHERE event_type = 'payment_recorded'"
                )
            )
            conn.execute(text("DROP TABLE audit_events_legacy"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_events_at ON audit_events (at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_events_kind ON audit_events (kind)"))
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS audit_events_no_update "
                "BEFORE UPDATE ON audit_events BEGIN "
                "SELECT RAISE(ABORT, 'audit events are append-only'); END"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS audit_events_no_delete "
                "BEFORE DELETE ON audit_events BEGIN "
                "SELECT RAISE(ABORT, 'audit events are append-only'); END"
            )
        )


def _ensure_risk_score_columns() -> None:
    """Backfill additive risk_scores columns for existing SQLite databases."""
    if not str(engine.url).startswith("sqlite"):
        return
    columns = {col["name"] for col in inspect(engine).get_columns("risk_scores")}
    with engine.begin() as conn:
        if "raw_score" not in columns:
            conn.execute(
                text("ALTER TABLE risk_scores ADD COLUMN raw_score FLOAT NOT NULL DEFAULT 0.0")
            )
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
