"""Tests for the synthetic data generator."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest
from sqlmodel import Session, create_engine, select

from app.ml.synth import month_add, write_db
from app.models import Lease, Payment, Tenant


@pytest.fixture(scope="module")
def stats_and_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, str]:
    """Generate one database per test module run."""
    path = str(tmp_path_factory.mktemp("data") / "khata.db")
    stats = write_db(path, seed=42)
    return stats, path


def test_base_rate_in_range(stats_and_db: tuple[dict, str]) -> None:
    """The planted base rate of >5-days-late is between 15% and 22%."""
    rate = stats_and_db[0]["base_rate"]
    assert 0.15 <= rate <= 0.22, f"base rate {rate} outside [0.15, 0.22]"


def test_determinism(tmp_path) -> None:
    """Same seed produces identical row counts and payment fingerprints."""
    p1 = str(tmp_path / "a.db")
    p2 = str(tmp_path / "b.db")
    s1 = write_db(p1, seed=42)
    s2 = write_db(p2, seed=42)
    assert s1 == s2
    for path in (p1, p2):
        engine = create_engine(f"sqlite:///{path}")
        with Session(engine) as session:
            pays = session.exec(select(Payment)).all()
            fingerprint = sum(
                (p.lease_id * 31 + p.cycle_month.toordinal() + (p.paid_date.toordinal() if p.paid_date else 0))
                for p in pays
            )
            if path == p1:
                first = fingerprint
            else:
                assert fingerprint == first


def test_payment_invariants(stats_and_db: tuple[dict, str]) -> None:
    """No payment before lease start, no paid_date before cycle start, one per cycle."""
    _, path = stats_and_db
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        leases = {l.id: l for l in session.exec(select(Lease)).all()}  # noqa: E741
        payments = session.exec(select(Payment)).all()
        seen: set[tuple[int, date]] = set()
        for p in payments:
            key = (p.lease_id, p.cycle_month)
            assert key not in seen, f"duplicate payment for lease {p.lease_id} cycle {p.cycle_month}"
            seen.add(key)
            lease = leases[p.lease_id]
            assert p.cycle_month >= lease.start_date.replace(day=1)
            if p.paid_date is not None:
                assert p.paid_date >= p.cycle_month, "paid_date before cycle start"
                assert p.paid_date <= date.today()


def test_tenant_fields_valid(stats_and_db: tuple[dict, str]) -> None:
    """Occupation, language and channel values are from the allowed sets."""
    _, path = stats_and_db
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        tenants = session.exec(select(Tenant)).all()
        occ = Counter(t.occupation_type for t in tenants)
        assert set(occ) <= {"salaried", "business", "student", "gig"}
        assert set(t.preferred_language for t in tenants) <= {"en", "hi", "hinglish"}
        assert set(t.preferred_channel for t in tenants) <= {"whatsapp", "sms", "call"}
        assert len(tenants) > 100


def test_month_add() -> None:
    """month_add wraps across year boundaries."""
    assert month_add(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert month_add(date(2026, 1, 1), -1) == date(2025, 12, 1)
