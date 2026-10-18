"""Tenant drawer endpoint: profile, history, score, plan, reminders."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.common import payment_cell
from app.api.reminders import build_plan
from app.db import get_session
from app.ml.scoring import current_cycle
from app.models import Lease, Payment, Property, Reminder, RiskScore, Tenant, Unit
from app.schemas import Factor, PaymentCell, PlanStep, ReminderOut, TenantDetail

router = APIRouter()


def _reminder_out(reminder: Reminder) -> ReminderOut:
    """Convert a reminder row to the API schema."""
    meta = json.loads(reminder.metadata_json) if reminder.metadata_json else {}
    return ReminderOut(
        id=reminder.id,  # type: ignore[arg-type]
        lease_id=reminder.lease_id,
        cycle_month=reminder.cycle_month,
        channel=reminder.channel,
        tone=reminder.tone,
        language=reminder.language,
        message=reminder.message,
        status=reminder.status,
        created_at=reminder.created_at,
        approved_at=reminder.approved_at,
        guardrails=meta.get("guardrails", []),
        fallback=bool(meta.get("fallback", False)),
    )


@router.get("/{lease_id}", response_model=TenantDetail)
def tenant_detail(lease_id: int, session: Session = Depends(get_session)) -> TenantDetail:
    """Everything the drawer needs for one lease."""
    lease = session.get(Lease, lease_id)
    if lease is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Lease not found."})
    tenant = session.get(Tenant, lease.tenant_id)
    unit = session.get(Unit, lease.unit_id)
    prop = session.get(Property, unit.property_id)  # type: ignore[union-attr]
    cycle = current_cycle(session)

    payments = session.exec(
        select(Payment).where(Payment.lease_id == lease_id).order_by(Payment.cycle_month)
    ).all()
    history: list[PaymentCell] = [payment_cell(p, cycle) for p in payments[:-1]]
    score = session.exec(
        select(RiskScore).where(RiskScore.lease_id == lease_id).where(RiskScore.cycle_month == cycle)
    ).first()

    factors: list[Factor] = []
    risk = None
    tier = None
    if score is not None:
        risk = score.probability
        tier = score.tier
        for item in json.loads(score.top_factors_json or "[]"):
            factors.append(
                Factor(
                    feature=item["feature"],
                    template_value=item.get("template_value", ""),
                    direction=item["direction"],
                    contribution=item["contribution"],
                )
            )

    prior_cycles = len(payments) - 1
    cold_start = prior_cycles < 3
    due = payments[-1].due_date if payments else None
    has_overdue = any(
        p.paid_date is None or (p.paid_date - p.due_date).days > 5 for p in payments[:-1]
    )
    plan: list[PlanStep] = (
        build_plan(tier or "low", tenant.preferred_channel, due, has_overdue)  # type: ignore[union-attr]
        if due
        else []
    )

    reminders = session.exec(
        select(Reminder).where(Reminder.lease_id == lease_id).order_by(Reminder.created_at)  # type: ignore[attr-defined]
    ).all()

    return TenantDetail(
        lease_id=lease_id,
        tenant_id=lease.tenant_id,
        tenant_name=tenant.name,  # type: ignore[union-attr]
        unit_label=unit.label,  # type: ignore[union-attr]
        property_name=prop.name if prop else "Unknown",
        rent_inr=lease.monthly_rent,
        due_day=lease.due_day,
        occupation_type=tenant.occupation_type,  # type: ignore[union-attr]
        preferred_language=tenant.preferred_language,  # type: ignore[union-attr]
        preferred_channel=tenant.preferred_channel,  # type: ignore[union-attr]
        tenure_months=_months_between(lease.start_date, cycle),
        prior_cycles=prior_cycles,
        history=history,
        probability=risk,
        tier=tier,
        factors=factors,
        plan=plan,
        reminders=[_reminder_out(r) for r in reminders],
        cold_start=cold_start,
    )


def _months_between(start, end) -> int:  # type: ignore[no-untyped-def]
    """Whole months between two dates."""
    return (end.year - start.year) * 12 + (end.month - start.month)
