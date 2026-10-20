"""Read-only audit event listing endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.audit import AUDIT_KINDS, event_dict
from app.db import get_session
from app.models import AuditEvent

router = APIRouter()


@router.get("")
def list_events(
    lease_id: int | None = None,
    kind: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """List newest audit events, with optional lease, kind and summary filters."""
    statement = select(AuditEvent).order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
    if lease_id is not None:
        statement = statement.where(AuditEvent.lease_id == lease_id)
    if kind:
        if kind not in AUDIT_KINDS:
            return []
        statement = statement.where(AuditEvent.kind == kind)
    if q:
        statement = statement.where(AuditEvent.summary.ilike(f"%{q.strip()}%"))
    return [event_dict(event) for event in session.exec(statement).all()]
