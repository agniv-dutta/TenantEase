"""Maintenance triage endpoints: raise a request and list a lease's requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.llm.triage import classify
from app.models import Lease, MaintenanceRequest
from app.schemas import MaintenanceCreate, MaintenanceOut

router = APIRouter()


def _out(row: MaintenanceRequest) -> MaintenanceOut:
    """Convert a stored request row to the API schema."""
    return MaintenanceOut(
        id=row.id,  # type: ignore[arg-type]
        lease_id=row.lease_id,
        text=row.text,
        category=row.category,
        urgency=row.urgency,
        suggested_trade=row.suggested_trade,
        summary=row.summary,
        method=row.method,
        forced_emergency=row.forced_emergency,
        created_at=row.created_at,
    )


@router.post("", response_model=MaintenanceOut, status_code=201)
def create_request(
    payload: MaintenanceCreate, session: Session = Depends(get_session)
) -> MaintenanceOut:
    """Triage a complaint and store the result."""
    if session.get(Lease, payload.lease_id) is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Lease not found."}
        )
    text = payload.text.strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "Describe the issue in a few words."},
        )
    result = classify(text)
    row = MaintenanceRequest(
        lease_id=payload.lease_id,
        text=text,
        category=result.triage.category.value,
        urgency=result.triage.urgency.value,
        suggested_trade=result.triage.suggested_trade,
        summary=result.triage.one_line_summary,
        method=result.method,
        forced_emergency=result.forced_emergency,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _out(row)


@router.get("", response_model=list[MaintenanceOut])
def list_requests(
    lease_id: int | None = None, session: Session = Depends(get_session)
) -> list[MaintenanceOut]:
    """List maintenance requests, optionally for one lease."""
    statement = select(MaintenanceRequest)
    if lease_id is not None:
        statement = statement.where(MaintenanceRequest.lease_id == lease_id)
    statement = statement.order_by(MaintenanceRequest.created_at)  # type: ignore[attr-defined]
    return [_out(row) for row in session.exec(statement).all()]
