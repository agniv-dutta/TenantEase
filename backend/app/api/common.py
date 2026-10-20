"""Shared helpers for the API routers."""

from __future__ import annotations

import calendar
from datetime import date

from app import clock
from app.models import Payment
from app.schemas import PaymentCell


def _last_day_of_month(cycle_month: date) -> date:
    """The last calendar day of ``cycle_month``."""
    return date(cycle_month.year, cycle_month.month, calendar.monthrange(cycle_month.year, cycle_month.month)[1])


def vacant_cell(cycle_month: date, due_day: int) -> PaymentCell:
    """A month the lease was not billed for: an empty cell in the register.

    Rows are padded with these so every lease shows the same month columns,
    which keeps the ledger grid aligned in the stacked layout too.
    """
    due_date = min(cycle_month.replace(day=due_day), _last_day_of_month(cycle_month))
    return PaymentCell(
        cycle_month=cycle_month,
        due_date=due_date,
        status="vacant",
        paid_date=None,
        days_late=None,
        amount=0,
    )


def payment_cell(
    payment: Payment,
    open_cycle: date,
    probability: float | None = None,
    tier: str | None = None,
) -> PaymentCell:
    """Classify one payment into a ledger cell.

    Statuses: paid_on_time, paid_late, unpaid_overdue, unpaid_upcoming and
    open. Whether unpaid rent is due soon, open or overdue is judged against
    ``clock.today()`` (DEMO_TODAY), the same date everything else uses. The
    open cycle is the last cycle and always has no paid_date in the prototype.
    """
    if payment.cycle_month == open_cycle and payment.paid_date is None:
        status = "open" if payment.due_date <= clock.today() else "unpaid_upcoming"
        return PaymentCell(
            cycle_month=payment.cycle_month,
            due_date=payment.due_date,
            status=status,
            paid_date=None,
            days_late=None,
            amount=payment.amount,
            probability=probability,
            tier=tier,
        )
    if payment.paid_date is None:
        status = "unpaid_overdue" if payment.due_date <= clock.today() else "unpaid_upcoming"
        return PaymentCell(
            cycle_month=payment.cycle_month,
            due_date=payment.due_date,
            status=status,
            paid_date=None,
            days_late=None,
            amount=payment.amount,
        )
    days_late = max(0, (payment.paid_date - payment.due_date).days)
    return PaymentCell(
        cycle_month=payment.cycle_month,
        due_date=payment.due_date,
        status="paid_late" if days_late > 0 else "paid_on_time",
        paid_date=payment.paid_date,
        days_late=days_late,
        amount=payment.amount,
    )
