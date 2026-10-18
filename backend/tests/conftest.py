"""Shared test fixtures: ensure a seeded database exists."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _ensure_seeded_db() -> None:
    """Create data/khata.db once per test session if missing."""
    db_path = Path(__file__).resolve().parent.parent / "data" / "khata.db"
    if not db_path.exists():
        from app.ml.synth import write_db

        write_db(str(db_path), seed=42)
