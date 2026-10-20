"""Shared test fixtures: ensure a seeded database exists."""

from __future__ import annotations

from pathlib import Path

import pytest

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "khata.db"


def _covers_ledger_window() -> bool:
    """True when the seed on disk still covers the demo clock's ledger window."""
    from sqlmodel import Session, select

    from app import clock
    from app.db import engine
    from app.models import Payment

    with Session(engine) as session:
        months = {row for row in session.exec(select(Payment.cycle_month)).all()}
    return all(month in months for month in clock.recent_cycles())


@pytest.fixture(autouse=True, scope="session")
def _ensure_seeded_db() -> None:
    """Create data/khata.db once per test session if missing or stale.

    A stale database is one that does not cover the demo clock (for example
    after DEMO_TODAY moves); the fix is always a reseed, never a silent gap.
    """
    if not DB_PATH.exists() or not _covers_ledger_window():
        from app.ml.synth import write_db

        write_db(str(DB_PATH), seed=42)
