"""Server-side audit event creation and stable demo timestamps."""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app import clock
from app.models import AuditEvent

AUDIT_KINDS = {
    "reminder_drafted",
    "reminder_edited",
    "reminder_approved",
    "payment_recorded",
    "payment_parsed",
}


def append_event(
    session: Session,
    kind: str,
    summary: str,
    lease_id: int | None,
    details: dict[str, Any],
) -> AuditEvent:
    """Append one server-authored event with a strictly increasing demo time."""
    if kind not in AUDIT_KINDS:
        raise ValueError(f"Unsupported audit event kind: {kind}")
    previous = session.exec(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
    event_at = clock.now()
    if previous is not None and previous.at is not None:
        previous_at = previous.at
        if previous_at.tzinfo is None:
            previous_at = previous_at.replace(tzinfo=timezone.utc)
        if previous_at >= event_at:
            event_at = previous_at + timedelta(microseconds=1)
    event = AuditEvent(
        at=event_at,
        actor="demo manager",
        kind=kind,
        lease_id=lease_id,
        summary=summary,
        details=details,
    )
    session.add(event)
    session.flush()
    return event


def event_dict(event: AuditEvent) -> dict[str, Any]:
    """Serialize an event for the audit API without exposing model scores."""
    at = event.at
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return {
        "id": event.id,
        "at": at.isoformat(),
        "actor": event.actor,
        "kind": event.kind,
        "lease_id": event.lease_id,
        "summary": event.summary,
        "details": event.details,
    }
