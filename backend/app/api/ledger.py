"""Ledger endpoint: one row per lease with the last N cycles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.common import payment_cell
from app.db import get_session
from app.ml.scoring import current_cycle
from app.models import Lease, Payment, Property, RiskScore, Tenant, Unit
from app.schemas import LedgerResponse, LedgerRow

router = APIRouter()


@router.get("/ledger", response_model=LedgerResponse)
def ledger(
    property_id: int | None = None,
    months: int = 6,
    session: Session = Depends(get_session),
) -> LedgerResponse:
    """Return ledger rows for the open cycle, optionally filtered by property."""
    if months < 1 or months > 24:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_months", "message": "Months must be between 1 and 24."},
        )
    cycle = current_cycle(session)
    units = {u.id: u for u in session.exec(select(Unit)).all()}
    properties = {p.id: p for p in session.exec(select(Property)).all()}
    tenants = {t.id: t for t in session.exec(select(Tenant)).all()}
    scores = {
        s.lease_id: s for s in session.exec(select(RiskScore).where(RiskScore.cycle_month == cycle)).all()
    }

    sortable_rows: list[tuple[float, float, int, LedgerRow]] = []
    for lease in session.exec(select(Lease)).all():
        unit = units[lease.unit_id]
        if property_id is not None and unit.property_id != property_id:
            continue
        payments = session.exec(
            select(Payment).where(Payment.lease_id == lease.id).order_by(Payment.cycle_month)
        ).all()
        if not payments or payments[-1].cycle_month != cycle:
            continue  # lease not active in the open cycle
        tenant = tenants[lease.tenant_id]
        history = payments[-(months + 1) : -1]
        current = payments[-1]
        score = scores.get(lease.id)  # type: ignore[arg-type]
        cells = [payment_cell(p, cycle) for p in history]
        row = LedgerRow(
            lease_id=lease.id,  # type: ignore[arg-type]
            tenant_name=tenant.name,
            unit_label=unit.label,
            property_name=properties[unit.property_id].name,
            property_id=unit.property_id,
            occupation_type=tenant.occupation_type,
            preferred_language=tenant.preferred_language,
            preferred_channel=tenant.preferred_channel,
            cycles=cells,
            current=payment_cell(
                current,
                cycle,
                probability=score.probability if score else None,
                tier=score.tier if score else None,
            ),
        )
        sortable_rows.append(
            (
                score.raw_score if score else 0.0,
                score.prev_cycle_outstanding_days if score else 0.0,
                lease.id,  # type: ignore[arg-type]
                row,
            )
        )

    sortable_rows.sort(key=lambda item: (-item[0], -item[1], item[2]))
    rows = [row for _, _, _, row in sortable_rows]
    return LedgerResponse(cycle_month=cycle, rows=rows)
