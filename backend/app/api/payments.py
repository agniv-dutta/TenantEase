"""Payment endpoints: parse a pasted message, then record a confirmed payment.

Nothing is posted automatically. ``/parse`` only proposes fields and candidate
leases; ``/record`` is the single write path and it always writes an audit
event first.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import clock
from app.audit import append_event
from app.db import get_session
from app.ml.scoring import current_cycle, score_open_cycle
from app.models import AuditEvent, Lease, Payment
from app.payments.parser import parse_payment_message
from app.schemas import (
    ParsedFields,
    PaymentMatch,
    PaymentParseRequest,
    PaymentParseResponse,
    PaymentRecordRequest,
    PaymentRecordResponse,
)

router = APIRouter()

VALID_METHODS = {"upi", "cash", "bank_transfer", "cheque"}
AMOUNT_TOLERANCE = 0


@router.post("/parse", response_model=PaymentParseResponse)
def parse_message(
    body: PaymentParseRequest, session: Session = Depends(get_session)
) -> PaymentParseResponse:
    """Parse a pasted message into fields, candidate leases and flags."""
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_message", "message": "Paste a payment message first."},
        )
    result = parse_payment_message(session, text)
    candidate_ids = [match.lease_id for match in result.matches]
    fields = result.fields.as_dict()
    safe_fields = {key: fields.get(key) for key in ("amount", "paid_date", "method", "language")}
    safe_fields["reference_present"] = bool(fields.get("reference"))
    append_event(
        session,
        "payment_parsed",
        f"Parsed payment message with {len(candidate_ids)} candidate lease{'s' if len(candidate_ids) != 1 else ''}",
        candidate_ids[0] if len(candidate_ids) == 1 else None,
        {"fields": safe_fields, "candidate_lease_ids": candidate_ids, "flags": result.flags},
    )
    session.commit()
    return PaymentParseResponse(
        fields=ParsedFields(**fields),
        matches=[PaymentMatch(**m.as_dict()) for m in result.matches],
        flags=result.flags,
    )


@router.post("/record", response_model=PaymentRecordResponse, status_code=201)
def record_payment(
    body: PaymentRecordRequest, session: Session = Depends(get_session)
) -> PaymentRecordResponse:
    """Record a confirmed payment for a lease's cycle.

    Validates the amount against the bill (flagging a partial or an excess),
    rejects duplicates, writes an audit event, then re-scores the open cycle.
    """
    if body.method not in VALID_METHODS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_method",
                "message": "Method must be upi, cash, bank_transfer or cheque.",
            },
        )
    if body.amount <= 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_amount", "message": "Amount must be greater than zero."},
        )
    if body.paid_date > clock.today():
        raise HTTPException(
            status_code=422,
            detail={"code": "date_in_future", "message": "The paid date cannot be after today."},
        )

    lease = session.get(Lease, body.lease_id)
    if lease is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Lease not found."}
        )

    cycle = current_cycle(session)
    payment = session.exec(
        select(Payment)
        .where(Payment.lease_id == body.lease_id)
        .where(Payment.cycle_month == body.cycle_month)
    ).first()
    reference = (body.reference or "").strip() or None

    # Duplicates: the same cycle already paid on this date for this amount, or
    # another recorded payment already carries this reference.
    if payment is not None and payment.paid_date is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate",
                "message": "This payment is already recorded for that month.",
            },
        )
    if reference and _reference_exists(session, reference):
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate", "message": "That reference is already recorded."},
        )

    expected = payment.amount if payment else lease.monthly_rent
    flags: list[str] = []
    if body.amount < expected - AMOUNT_TOLERANCE:
        flags.append("partial_payment")
    elif body.amount > expected + AMOUNT_TOLERANCE:
        flags.append("excess_payment")

    if payment is None:
        payment = Payment(
            lease_id=body.lease_id,
            cycle_month=body.cycle_month,
            due_date=body.cycle_month.replace(day=1),
            amount=body.amount,
            method=body.method,
        )
        session.add(payment)
    payment.paid_date = body.paid_date
    payment.amount = body.amount
    payment.method = body.method

    days_late = max(0, (body.paid_date - payment.due_date).days)
    append_event(
        session,
        "payment_recorded",
        f"Recorded payment for lease {body.lease_id}",
        body.lease_id,
        {
            "cycle_month": body.cycle_month.isoformat(),
            "amount": body.amount,
            "paid_date": body.paid_date.isoformat(),
            "method": body.method,
            "reference": reference,
            "flags": flags,
        },
    )
    session.commit()

    rescored = score_open_cycle(session, cycle)

    return PaymentRecordResponse(
        lease_id=body.lease_id,
        cycle_month=body.cycle_month,
        amount=body.amount,
        paid_date=body.paid_date,
        method=body.method,
        reference=reference,
        days_late=days_late,
        status="paid_late" if days_late > 5 else "paid_on_time",
        rescored=rescored,
        flags=flags,
    )


def _reference_exists(session: Session, reference: str) -> bool:
    """Whether a recorded payment already carries this reference."""
    events = session.exec(select(AuditEvent).where(AuditEvent.kind == "payment_recorded")).all()
    for event in events:
        if event.details.get("reference") == reference:
            return True
    return False
