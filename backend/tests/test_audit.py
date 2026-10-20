"""Tests for append-only audit kinds and audit route output."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app import clock
from app.audit import AUDIT_KINDS, append_event
from app.db import get_session
from app.main import app
from app.models import AuditEvent, Lease, Payment, Property, SQLModel, Tenant, Unit


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a client with the app's configured audit database."""
    with TestClient(app) as test_client:
        yield test_client


def test_each_audit_kind_is_appendable_and_monotonic(tmp_path) -> None:
    """Every supported kind stores server actor, details and an ordered demo time."""
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        events = [
            append_event(session, kind, f"Synthetic {kind}", 1, {"text": "नमस्ते"})
            for kind in sorted(AUDIT_KINDS)
        ]
        session.commit()
        assert all(event.actor == "demo manager" for event in events)
        assert [event.at for event in events] == sorted(event.at for event in events)
        stored = session.query(AuditEvent).all()
        assert {event.kind for event in stored} == AUDIT_KINDS
        assert all(event.details == {"text": "नमस्ते"} for event in stored)
        assert all(event.at.date() == clock.today() for event in stored)


def test_audit_endpoint_returns_newest_first(client: TestClient) -> None:
    """The read endpoint includes audit details and newest-first ordering."""
    result = client.get("/api/audit")
    assert result.status_code == 200
    rows = result.json()
    assert rows == sorted(rows, key=lambda row: (row["at"], row["id"]), reverse=True)
    if rows:
        assert set(rows[0]) == {"id", "at", "actor", "kind", "lease_id", "summary", "details"}


def test_reminder_workflow_writes_draft_edit_and_one_approval(client: TestClient) -> None:
    """A saved edit records both texts and repeated approval is idempotent."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    draft_response = client.post(
        "/api/reminders/draft",
        json={"lease_id": lease_id, "language": "en", "tone": "friendly"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    edited_text = draft["message"] + " Thank you."
    edit_response = client.put(f"/api/reminders/{draft['id']}/edit", json={"message": edited_text})
    assert edit_response.status_code == 200
    assert client.post(f"/api/reminders/{draft['id']}/approve").status_code == 200
    assert client.post(f"/api/reminders/{draft['id']}/approve").status_code == 200
    events = client.get(f"/api/audit?lease_id={lease_id}").json()
    reminder_events = [
        event for event in events if event["details"].get("reminder_id") == draft["id"]
    ]
    assert [event["kind"] for event in reminder_events].count("reminder_drafted") == 1
    assert [event["kind"] for event in reminder_events].count("reminder_edited") == 1
    assert [event["kind"] for event in reminder_events].count("reminder_approved") == 1
    edit_event = next(event for event in reminder_events if event["kind"] == "reminder_edited")
    assert edit_event["details"]["before"] == draft["message"]
    assert edit_event["details"]["after"] == edited_text
    assert all(event["actor"] == "demo manager" for event in reminder_events)


def test_payment_parse_writes_sanitized_event(client: TestClient) -> None:
    """Parsing records proposed fields without logging the pasted text or name."""
    response = client.post(
        "/api/payments/parse", json={"text": "Rent received Rs 15000 on 5 Oct by UPI"}
    )
    assert response.status_code == 200
    events = client.get("/api/audit?kind=payment_parsed").json()
    event = events[0]
    assert event["kind"] == "payment_parsed"
    assert "text" not in event["details"]
    assert "payer_name_guess" not in event["details"].get("fields", {})


def test_confirmed_payment_is_audited_once(tmp_path, monkeypatch) -> None:
    """A payment confirmation writes one event and duplicate confirmation is rejected."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'payment-audit.db'}")
    SQLModel.metadata.create_all(test_engine)
    cycle = clock.open_cycle()
    with Session(test_engine) as session:
        session.add(Property(id=1, name="Synthetic House", locality="Synthetic locality"))
        session.add(Unit(id=1, property_id=1, label="SYN-01", bhk=1, rent_inr=15000, floor=1))
        session.add(
            Tenant(
                id=1,
                name="Synthetic Tenant",
                phone="0000000000",
                occupation_type="salaried",
                preferred_language="en",
                preferred_channel="whatsapp",
            )
        )
        session.add(
            Lease(
                id=1,
                unit_id=1,
                tenant_id=1,
                start_date=cycle.replace(year=cycle.year - 1),
                monthly_rent=15000,
                due_day=1,
                deposit=30000,
            )
        )
        for index, payment_cycle in enumerate(clock.recent_cycles()):
            session.add(
                Payment(
                    id=index + 1,
                    lease_id=1,
                    cycle_month=payment_cycle,
                    due_date=payment_cycle,
                    amount=15000,
                    method="upi",
                )
            )
        session.commit()

    def override_session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_session, override_session)
    monkeypatch.setattr("app.api.payments.score_open_cycle", lambda session, target: 0)
    with TestClient(app) as client:
        payload = {
            "lease_id": 1,
            "cycle_month": cycle.isoformat(),
            "amount": 15000,
            "paid_date": clock.today().isoformat(),
            "method": "upi",
        }
        recorded = client.post("/api/payments/record", json=payload)
        assert recorded.status_code == 201, recorded.text
        assert client.post("/api/payments/record", json=payload).status_code == 409
        events = client.get("/api/audit?kind=payment_recorded").json()
        assert len(events) == 1
        assert events[0]["details"]["amount"] == 15000
