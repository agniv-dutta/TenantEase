"""Tenant drawer endpoint: profile, history, score, plan, reminders."""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.common import payment_cell
from app.api.reminders import build_plan
from app.db import get_session
from app.ml.features import SAFE_FACTOR_SENTENCE
from app.ml.scoring import current_cycle
from app.models import Lease, Payment, Property, Reminder, RiskScore, Tenant, Unit
from app.schemas import Factor, PaymentCell, PlanStep, ReminderOut, TenantDetail

router = APIRouter()
logger = logging.getLogger(__name__)


def _fallback_sentence(feature: str) -> str:
    """Sentence for a stored factor that predates the template renderer."""
    logger.warning("No stored sentence for feature %r; using the safe default.", feature)
    return SAFE_FACTOR_SENTENCE


def _strength_bucket(scores: list[RiskScore]) -> Callable[[float], str]:
    """Tertile cut points for |SHAP| across the scored portfolio of one cycle.

    A SHAP value is not a share of the probability, so it never appears as a
    weight. It only ranks a factor as the main, moderate or minor contributor.
    """
    magnitudes = sorted(
        abs(float(item.get("contribution", 0.0)))
        for row in scores
        for item in json.loads(row.top_factors_json or "[]")
    )
    if not magnitudes:
        return lambda _: "minor"
    lower = magnitudes[max(0, math.ceil(len(magnitudes) / 3) - 1)]
    upper = magnitudes[max(0, math.ceil(2 * len(magnitudes) / 3) - 1)]

    def bucket(value: float) -> str:
        if value >= upper:
            return "main"
        if value >= lower:
            return "moderate"
        return "minor"

    return bucket


def _reminder_out(reminder: Reminder, tenant_name: str, unit_label: str) -> ReminderOut:
    """Convert a reminder row and its tenant/unit labels to the API schema."""
    meta = json.loads(reminder.metadata_json) if reminder.metadata_json else {}
    return ReminderOut(
        id=reminder.id,  # type: ignore[arg-type]
        lease_id=reminder.lease_id,
        tenant_name=tenant_name,
        unit_label=unit_label,
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
    portfolio_scores = session.exec(
        select(RiskScore).where(RiskScore.cycle_month == cycle)
    ).all()
    score = next((s for s in portfolio_scores if s.lease_id == lease_id), None)
    strength_of = _strength_bucket(portfolio_scores)

    factors: list[Factor] = []
    risk = None
    tier = None
    if score is not None:
        risk = score.probability
        tier = score.tier
        for item in json.loads(score.top_factors_json or "[]"):
            direction = item.get("direction") or (
                "raises" if float(item.get("contribution", 0.0)) > 0 else "lowers"
            )
            factors.append(
                Factor(
                    feature=item["feature"],
                    sentence=item.get("sentence") or _fallback_sentence(item["feature"]),
                    direction=direction,
                    strength=strength_of(abs(float(item.get("contribution", 0.0)))),
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
        top_factors=factors,
        plan=plan,
        reminders=[_reminder_out(r, tenant.name, unit.label) for r in reminders],  # type: ignore[union-attr]
        cold_start=cold_start,
    )


def _months_between(start, end) -> int:  # type: ignore[no-untyped-def]
    """Whole months between two dates."""
    return (end.year - start.year) * 12 + (end.month - start.month)
