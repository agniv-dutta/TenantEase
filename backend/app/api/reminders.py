"""Reminder planner and drafting endpoints."""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import clock
from app.audit import append_event
from app.db import get_session
from app.llm.drafter import draft_message
from app.llm.guardrails import check_all
from app.models import Lease, Payment, Reminder, Tenant, Unit
from app.schemas import (
    CheckRequest,
    DraftRequest,
    GuardrailResult,
    PlanStep,
    ReminderEditRequest,
    ReminderOut,
)

router = APIRouter()

VALID_LANGUAGES = {"en", "hi", "hinglish"}
VALID_TONES = {"friendly", "neutral", "polite_firm"}


def system_channel(preferred_channel: str) -> str:
    """System reminders cannot be calls; fall back to WhatsApp."""
    return "whatsapp" if preferred_channel == "call" else preferred_channel


def build_plan(
    tier: str, preferred_channel: str, due_date: date, has_overdue: bool
) -> list[PlanStep]:
    """Deterministic reminder plan for a risk tier.

    low: one friendly reminder the day before due.
    medium: two neutral reminders, three days before and on the due date.
    high: a friendly reminder five days before plus a manager call two days
    before.

    ``has_overdue`` is accepted for future tone escalation but the planner
    itself never emits ``polite_firm`` (that is never a first touch).
    """
    channel = system_channel(preferred_channel)
    steps: list[PlanStep] = []
    if tier == "low":
        steps.append(
            PlanStep(
                offset_days=-1,
                date=due_date - timedelta(days=1),
                channel=channel,
                tone="friendly",
                owner="system",
            )
        )
    elif tier == "medium":
        steps.append(
            PlanStep(
                offset_days=-3,
                date=due_date - timedelta(days=3),
                channel=channel,
                tone="neutral",
                owner="system",
            )
        )
        steps.append(
            PlanStep(offset_days=0, date=due_date, channel=channel, tone="neutral", owner="system")
        )
    else:  # high
        steps.append(
            PlanStep(
                offset_days=-5,
                date=due_date - timedelta(days=5),
                channel=channel,
                tone="friendly",
                owner="system",
            )
        )
        steps.append(
            PlanStep(
                offset_days=-2,
                date=due_date - timedelta(days=2),
                channel="call",
                tone="friendly",
                owner="manager",
            )
        )
    if preferred_channel == "call" and tier != "high":
        steps.append(
            PlanStep(
                offset_days=-2,
                date=due_date - timedelta(days=2),
                channel="call",
                tone="friendly",
                owner="manager",
            )
        )
    _ = has_overdue
    return steps


def _open_cycle_and_due(session: Session, lease_id: int) -> tuple[date, date, int]:
    """Return (open cycle, due date, amount) for a lease's current cycle."""
    payments = session.exec(
        select(Payment).where(Payment.lease_id == lease_id).order_by(Payment.cycle_month)
    ).all()
    open_cycle = clock.open_cycle()
    current = next((p for p in payments if p.cycle_month == open_cycle), None)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "This lease has no bill for the open cycle."},
        )
    return current.cycle_month, current.due_date, current.amount


def _has_overdue(session: Session, lease_id: int, before: date) -> bool:
    """Whether the lease has any unpaid or late cycle before the open cycle."""
    payments = session.exec(
        select(Payment).where(Payment.lease_id == lease_id).where(Payment.cycle_month < before)
    ).all()
    for p in payments:
        if p.paid_date is None:
            return True
        if (p.paid_date - p.due_date).days > 5:
            return True
    return False


def _to_out(reminder: Reminder, session: Session) -> ReminderOut:
    """Convert a reminder row and its tenant/unit labels to the API schema."""
    meta = json.loads(reminder.metadata_json) if reminder.metadata_json else {}
    lease = session.get(Lease, reminder.lease_id)
    tenant = session.get(Tenant, lease.tenant_id) if lease else None
    unit = session.get(Unit, lease.unit_id) if lease else None
    return ReminderOut(
        id=reminder.id,  # type: ignore[arg-type]
        lease_id=reminder.lease_id,
        tenant_name=tenant.name if tenant else "Unknown tenant",
        unit_label=unit.label if unit else "Unknown unit",
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


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    lease_id: int | None = None, session: Session = Depends(get_session)
) -> list[ReminderOut]:
    """List reminders, optionally filtered by lease."""
    stmt = select(Reminder).order_by(Reminder.created_at.desc())  # type: ignore[attr-defined]
    if lease_id is not None:
        stmt = stmt.where(Reminder.lease_id == lease_id)
    return [_to_out(r, session) for r in session.exec(stmt).all()]


@router.post("/draft", response_model=ReminderOut)
def draft_reminder(body: DraftRequest, session: Session = Depends(get_session)) -> ReminderOut:
    """Draft a reminder message for a lease, language and tone."""
    if body.language not in VALID_LANGUAGES:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_language", "message": "Language must be en, hi or hinglish."},
        )
    if body.tone not in VALID_TONES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_tone",
                "message": "Tone must be friendly, neutral or polite_firm.",
            },
        )

    lease = session.get(Lease, body.lease_id)
    if lease is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Lease not found."}
        )
    tenant = session.get(Tenant, lease.tenant_id)
    unit = session.get(Unit, lease.unit_id)
    cycle_month, due, amount = _open_cycle_and_due(session, body.lease_id)
    has_overdue = _has_overdue(session, body.lease_id, cycle_month)

    tone = body.tone
    notes = []
    if tone == "polite_firm" and not has_overdue:
        tone = "neutral"
        notes.append(
            "Polite firm tone is only used when a payment is already overdue, so this draft is neutral."
        )

    due_str = f"{due.day} {due.strftime('%b')}"
    result = draft_message(
        first_name=tenant.name,  # type: ignore[union-attr]
        unit_label=unit.label,  # type: ignore[union-attr]
        amount_inr=amount,
        due_str=due_str,
        language=body.language,
        tone=tone,
        acknowledge_overdue=has_overdue,
        allowed_numeric_tokens=[unit.label],  # type: ignore[union-attr]
    )

    reminder = Reminder(
        lease_id=body.lease_id,
        cycle_month=cycle_month,
        channel=system_channel(tenant.preferred_channel),  # type: ignore[union-attr]
        tone=tone,
        language=body.language,
        message=result.message,
        status="draft",
        metadata_json=json.dumps(
            {
                "guardrails": result.guardrails,
                "source": result.source,
                "fallback": result.source == "fallback",
                "notes": notes + result.notes,
            },
            ensure_ascii=False,
        ),
    )
    session.add(reminder)
    session.flush()
    append_event(
        session,
        "reminder_drafted",
        f"Drafted reminder for lease {body.lease_id}",
        body.lease_id,
        {
            "reminder_id": reminder.id,
            "cycle_month": cycle_month.isoformat(),
            "channel": reminder.channel,
            "tone": reminder.tone,
            "language": reminder.language,
        },
    )
    session.commit()
    session.refresh(reminder)
    out = _to_out(reminder, session)
    if notes:
        out.guardrails = out.guardrails + [
            {"name": "tone_adjusted", "passed": True, "reason": notes[0]}
        ]
    return out


@router.post("/check", response_model=list[GuardrailResult])
def check_message(
    body: CheckRequest, session: Session = Depends(get_session)
) -> list[GuardrailResult]:
    """Re-run guardrails on an edited message so the drawer can gate approval."""
    lease = session.get(Lease, body.lease_id)
    if lease is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Lease not found."}
        )
    unit = session.get(Unit, lease.unit_id)
    _, due, amount = _open_cycle_and_due(session, body.lease_id)
    due_str = f"{due.day} {due.strftime('%b')}"
    results = check_all(
        message=body.message,
        language=body.language,
        amount_str=f"{amount:,}",
        due_str=due_str,
        allowed_numeric_tokens=[unit.label],  # type: ignore[union-attr]
    )
    return [GuardrailResult(**r.as_dict()) for r in results]


@router.post("/{reminder_id}/approve", response_model=ReminderOut)
def approve_reminder(reminder_id: int, session: Session = Depends(get_session)) -> ReminderOut:
    """Approve a drafted reminder."""
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Reminder not found."}
        )
    if reminder.status == "approved":
        return _to_out(reminder, session)
    reminder.status = "approved"
    reminder.approved_at = clock.now()
    session.add(reminder)
    append_event(
        session,
        "reminder_approved",
        f"Approved reminder for lease {reminder.lease_id}",
        reminder.lease_id,
        {"reminder_id": reminder.id, "cycle_month": reminder.cycle_month.isoformat()},
    )
    session.commit()
    session.refresh(reminder)
    return _to_out(reminder, session)


@router.put("/{reminder_id}/edit", response_model=ReminderOut)
def edit_reminder(
    reminder_id: int, body: ReminderEditRequest, session: Session = Depends(get_session)
) -> ReminderOut:
    """Save a checked reminder edit and append before-and-after text."""
    reminder = session.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Reminder not found."}
        )
    if reminder.status == "approved":
        raise HTTPException(
            status_code=409,
            detail={"code": "already_approved", "message": "Approved reminders cannot be edited."},
        )
    if not body.message.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_message", "message": "Enter reminder text before saving."},
        )
    lease = session.get(Lease, reminder.lease_id)
    unit = session.get(Unit, lease.unit_id) if lease else None
    _, due, amount = _open_cycle_and_due(session, reminder.lease_id)
    checks = check_all(
        message=body.message,
        language=reminder.language,
        amount_str=f"{amount:,}",
        due_str=f"{due.day} {due.strftime('%b')}",
        allowed_numeric_tokens=[unit.label] if unit else [],
    )
    failed = [check.reason for check in checks if not check.passed]
    if failed:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "guardrail_failed",
                "message": "Fix the reminder checks before saving: " + " ".join(failed),
            },
        )
    if body.message != reminder.message:
        before = reminder.message
        reminder.message = body.message
        session.add(reminder)
        append_event(
            session,
            "reminder_edited",
            f"Edited reminder for lease {reminder.lease_id}",
            reminder.lease_id,
            {"reminder_id": reminder.id, "before": before, "after": body.message},
        )
        session.commit()
        session.refresh(reminder)
    return _to_out(reminder, session)
