"""Leak-safe as-of feature pipeline.

One training row is built per (lease, cycle). The ``as_of`` timestamp for a
row is that cycle's due date minus 7 days. Features may only use information
whose timestamp is <= ``as_of``:

* A payment whose ``paid_date`` is after ``as_of`` (or NULL) counts as
  outstanding; the feature value becomes elapsed days since its due date.
* The billed rent is treated as known: ``rent_amount`` is the maximum of the
  unit's initial asking rent and amounts of payments *settled* by ``as_of``.
  The current cycle's payment row is never read (its amount can reflect a
  partial-payment outcome).

Explicitly excluded from features: tenant name, phone, property, locality,
``preferred_language``, ``preferred_channel``. Occupation type is included
only when ``settings.use_occupation`` is true so an ablation can run.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from app.config import settings
from app.models import Lease, Payment, Tenant, Unit

FESTIVAL_MONTHS = {10, 11, 4}
METHOD_CODES = {"upi": 0.0, "cash": 1.0, "bank_transfer": 2.0}
METHOD_NAMES = {0.0: "upi", 1.0: "cash", 2.0: "bank_transfer", -1.0: "unknown"}
MAX_HISTORY = 6

logger = logging.getLogger(__name__)

SAFE_FACTOR_SENTENCE = "This detail affected the late-risk estimate"


@dataclass(frozen=True)
class FeatureMeta:
    """Metadata for one feature column, with both wording directions."""

    name: str
    dtype: str
    raise_template: str
    lower_template: str
    audit_only: bool = False


FEATURE_METADATA: list[FeatureMeta] = [
    FeatureMeta(
        "late_count_1",
        "float64",
        "Was more than 5 days late {n} {times} in the last month",
        "Was not more than 5 days late in the last month",
    ),
    FeatureMeta(
        "late_share_1",
        "float64",
        "Was more than 5 days late last month",
        "Was not more than 5 days late last month",
    ),
    FeatureMeta(
        "late_count_3",
        "float64",
        "Paid more than 5 days late in {n} of the last 3 months",
        "Paid on time in all of the last 3 months",
    ),
    FeatureMeta(
        "late_share_3",
        "float64",
        "Paid more than 5 days late in {n} of the last 3 months",
        "Paid on time in all of the last 3 months",
    ),
    FeatureMeta(
        "late_count_6",
        "float64",
        "Paid more than 5 days late in {n} of the last 6 months",
        "Paid on time in all of the last 6 months",
    ),
    FeatureMeta(
        "late_share_6",
        "float64",
        "Paid more than 5 days late in {n} of the last 6 months",
        "Paid on time in all of the last 6 months",
    ),
    FeatureMeta(
        "mean_days_late_6",
        "float64",
        "Average delay was {d} days over the last 6 months",
        "Average delay was {d} days over the last 6 months",
    ),
    FeatureMeta(
        "max_days_late_6",
        "float64",
        "Worst delay was {d} days in the last 6 months",
        "Worst delay was {d} days in the last 6 months",
    ),
    FeatureMeta(
        "days_late_trend",
        "float64",
        "Delay trend is {d} days per cycle",
        "Delay trend is {d} days per cycle",
    ),
    FeatureMeta(
        "on_time_streak",
        "float64",
        "Has been on time {dur} in a row",
        "Has been on time {dur} in a row",
    ),
    FeatureMeta(
        "prev_cycle_outstanding_days",
        "float64",
        "Last cycle's rent was still unpaid {d} days after it was due",
        "No rent was outstanding from the last cycle",
    ),
    FeatureMeta(
        "tenure_months",
        "float64",
        "Has been a tenant for {dur}",
        "Has been a tenant for {dur}",
    ),
    FeatureMeta(
        "is_cold_start",
        "float64",
        "Is a new tenant with fewer than 3 payment cycles on record",
        "Has at least 3 payment cycles on record",
    ),
    FeatureMeta(
        "rent_amount",
        "float64",
        "Monthly rent is about Rs {amt}",
        "Monthly rent is about Rs {amt}",
    ),
    FeatureMeta(
        "rent_change_pct",
        "float64",
        "Rent went up {p} percent {dur} ago",
        "Rent has not changed",
    ),
    FeatureMeta(
        "cycles_since_rent_change",
        "float64",
        "Last rent change was {dur} ago",
        "Last rent change was {dur} ago",
    ),
    FeatureMeta(
        "cash_share_last_6",
        "float64",
        "Has paid in cash in {n} of the last 6 months",
        "Has paid cash in only {n} of the last 6 months",
    ),
    FeatureMeta(
        "last_payment_method",
        "float64",
        "Last settled payment is {method}",
        "Last settled payment is {method}",
    ),
    FeatureMeta(
        "due_day",
        "float64",
        "Rent is due on day {n} of the month",
        "Rent is due on day {n} of the month",
    ),
    FeatureMeta(
        "cycle_month_of_year",
        "float64",
        "This cycle is in month {n}",
        "This cycle is in month {n}",
    ),
    FeatureMeta(
        "is_festival_month",
        "float64",
        "This cycle falls in a festival month",
        "This cycle falls outside the festival months",
    ),
    FeatureMeta(
        "bhk",
        "float64",
        "Lives in a {n} BHK unit",
        "Lives in a {n} BHK unit",
    ),
    FeatureMeta("occupation_salaried", "float64", "Is a salaried tenant", "Is not a salaried tenant"),
    FeatureMeta("occupation_business", "float64", "Runs a business", "Does not run a business"),
    FeatureMeta("occupation_student", "float64", "Is a student tenant", "Is not a student tenant"),
    FeatureMeta("occupation_gig", "float64", "Works gig jobs", "Does not work gig jobs"),
]

AUDIT_METADATA: list[FeatureMeta] = [
    FeatureMeta(
        "preferred_language",
        "object",
        "Preferred language is {v}",
        "Preferred language is {v}",
        True,
    ),
    FeatureMeta("property_id", "float64", "Property is {n}", "Property is {n}", True),
]

_META_BY_NAME = {m.name: m for m in FEATURE_METADATA}

PAYMENT_METHOD_NAMES = {
    0.0: "UPI",
    1.0: "cash",
    2.0: "bank transfer",
    -1.0: "not recorded yet",
}


def _value(row: object, name: str, default: float = 0.0) -> float:
    """Read a numeric feature from a Series or dict, tolerating missing keys."""
    try:
        return float(row[name])  # type: ignore[index]
    except (KeyError, TypeError, ValueError, IndexError):
        return default


def _plural(count: int, noun: str) -> str:
    """Render a count with a singular or plural noun, for example 1 month."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _placeholders(feature: str, row: object) -> dict[str, object]:
    """Human-formatted template values: counts and days as integers, one decimal max."""
    if feature == "late_count_1":
        n = int(round(_value(row, feature)))
        return {"n": n, "times": "time" if n == 1 else "times"}
    if feature in ("late_count_3", "late_count_6"):
        return {"n": int(round(_value(row, feature)))}
    if feature in ("late_share_3", "late_share_6"):
        window = 3 if feature.endswith("_3") else 6
        return {"n": int(round(_value(row, feature) * window))}
    if feature in ("mean_days_late_6", "max_days_late_6", "prev_cycle_outstanding_days"):
        return {"d": int(round(_value(row, feature)))}
    if feature == "days_late_trend":
        return {"d": f"{_value(row, feature):.1f}"}
    if feature == "on_time_streak":
        return {"dur": _plural(int(round(_value(row, feature))), "month")}
    if feature == "tenure_months":
        return {"dur": _plural(int(round(_value(row, feature))), "month")}
    if feature == "rent_amount":
        return {"amt": f"{int(round(_value(row, feature))):,}"}
    if feature == "rent_change_pct":
        return {
            "p": int(round(_value(row, "rent_change_pct"))),
            "dur": _plural(int(round(_value(row, "cycles_since_rent_change"))), "month"),
        }
    if feature == "cycles_since_rent_change":
        return {"dur": _plural(int(round(_value(row, feature))), "month")}
    if feature == "cash_share_last_6":
        return {"n": int(round(_value(row, feature) * 6))}
    if feature == "last_payment_method":
        code = _value(row, feature, -1.0)
        return {"method": PAYMENT_METHOD_NAMES.get(code, "not recorded yet")}
    if feature in ("due_day", "cycle_month_of_year", "bhk"):
        return {"n": int(round(_value(row, feature)))}
    return {}


def _template_for(feature: str, row: object, direction: str, meta: FeatureMeta) -> str:
    """Pick the wording that matches the value, falling back to SHAP direction.

    For counts, shares, percentages and booleans the value itself decides which
    sentence is true, so the sentence never contradicts the feature.
    """
    positive: bool | None = None
    if feature in (
        "late_count_1",
        "late_count_3",
        "late_count_6",
        "late_share_1",
        "late_share_3",
        "late_share_6",
        "rent_change_pct",
        "prev_cycle_outstanding_days",
    ):
        positive = _value(row, feature) > 0
    elif feature in ("is_cold_start", "is_festival_month") or feature.startswith("occupation_"):
        positive = _value(row, feature) >= 0.5
    if positive is None:
        return meta.raise_template if direction == "raises" else meta.lower_template
    return meta.raise_template if positive else meta.lower_template


def render_feature_sentence(feature: str, row: object, direction: str) -> str:
    """Render one feature through its template, with a safe default on failure."""
    meta = _META_BY_NAME.get(feature)
    if meta is None:
        logger.warning(
            "No plain-language template for feature %r; using the safe default.", feature
        )
        return SAFE_FACTOR_SENTENCE
    template = _template_for(feature, row, direction, meta)
    try:
        return template.format(**_placeholders(feature, row)).strip()
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning(
            "Could not format the template for feature %r (%s); using the safe default.",
            feature,
            exc,
        )
        return SAFE_FACTOR_SENTENCE


def feature_columns(use_occupation: bool | None = None) -> list[str]:
    """Return the model feature column names in order."""
    if use_occupation is None:
        use_occupation = settings.use_occupation
    cols = [m.name for m in FEATURE_METADATA]
    if not use_occupation:
        cols = [c for c in cols if not c.startswith("occupation_")]
    return cols


@dataclass
class _LeaseContext:
    """Everything about a lease needed to build rows, loaded once."""

    lease: Lease
    unit: Unit
    tenant: Tenant
    payments: list[Payment]  # ordered by cycle_month


def _load_contexts(session: Session) -> list[_LeaseContext]:
    """Load leases with their unit, tenant and ordered payments."""
    leases = session.exec(select(Lease)).all()
    units = {u.id: u for u in session.exec(select(Unit)).all()}
    tenants = {t.id: t for t in session.exec(select(Tenant)).all()}
    payments = session.exec(select(Payment).order_by(Payment.cycle_month)).all()
    by_lease: dict[int, list[Payment]] = {}
    for p in payments:
        by_lease.setdefault(p.lease_id, []).append(p)
    return [
        _LeaseContext(lease=l, unit=units[l.unit_id], tenant=tenants[l.tenant_id], payments=by_lease.get(l.id, []))  # type: ignore[arg-type]
        for l in leases  # noqa: E741
    ]


def _month_diff(a: date, b: date) -> int:
    """Whole months from ``a`` to ``b`` (b >= a)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def _slope(ys: list[float]) -> float:
    """Least-squares slope of ys against 0..n-1; 0 when fewer than 3 points."""
    n = len(ys)
    if n < 3:
        return 0.0
    xs = np.arange(n, dtype=float)
    y = np.asarray(ys, dtype=float)
    xm, ym = xs.mean(), y.mean()
    denom = ((xs - xm) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((xs - xm) * (y - ym)).sum() / denom)


def _observed(payment: Payment, as_of: date) -> tuple[float, bool]:
    """Observed days-late for a prior payment at ``as_of`` and whether settled.

    Settled means ``paid_date`` is not None and <= as_of. Outstanding payments
    use elapsed days since the due date (never negative).
    """
    if payment.paid_date is not None and payment.paid_date <= as_of:
        return float((payment.paid_date - payment.due_date).days), True
    return float(max(0, (as_of - payment.due_date).days)), False


def _row_for_cycle(ctx: _LeaseContext, cycle: date, include_target: bool) -> dict | None:
    """Build one feature row for (lease, cycle). None when lease inactive."""
    due = next((p for p in ctx.payments if p.cycle_month == cycle), None)
    if due is None:
        # Lease not billed this cycle.
        last_day = date(cycle.year, cycle.month, calendar.monthrange(cycle.year, cycle.month)[1])
        if ctx.lease.start_date > last_day:
            return None
        if ctx.lease.end_date is not None and ctx.lease.end_date < cycle:
            return None
        return None
    as_of = due.due_date - timedelta(days=7)

    priors = [p for p in ctx.payments if p.cycle_month < cycle]
    obs: list[tuple[float, bool, Payment]] = []
    for p in priors:
        days, settled = _observed(p, as_of)
        obs.append((days, settled, p))
    recent = obs[-MAX_HISTORY:]

    def count_late(n: int) -> float:
        return float(sum(1 for d, _, _ in obs[-n:] if d > 5))

    def share_late(n: int) -> float:
        window = obs[-n:]
        return count_late(n) / len(window) if window else 0.0

    days_vals = [d for d, _, _ in recent]
    settled_amounts = [float(p.amount) for d, s, p in recent if s]
    known_rent = max(float(ctx.unit.rent_inr), *settled_amounts) if settled_amounts else float(ctx.unit.rent_inr)

    # Rent change detection over the full settled history (as-of filtered).
    # Partial payments never raise the running max because they are below rent.
    hist_rents: list[float] = [float(ctx.unit.rent_inr)]
    changed_at_cycle: date | None = None
    for d, s, p in obs:
        if s:
            amt = float(p.amount)
            if amt > hist_rents[-1]:
                hist_rents.append(amt)
                changed_at_cycle = p.cycle_month
    rent_change_pct = 0.0
    cycles_since_change = _month_diff(ctx.lease.start_date, cycle)
    if len(hist_rents) >= 2:
        rent_change_pct = (hist_rents[-1] - hist_rents[-2]) / hist_rents[-2] * 100.0
    if changed_at_cycle is not None:
        cycles_since_change = _month_diff(changed_at_cycle, cycle)

    cash_recent = [p.method == "cash" for d, s, p in recent if s]
    cash_share = sum(cash_recent) / len(cash_recent) if cash_recent else 0.0
    last_settled = next((p for d, s, p in reversed(obs) if s), None)
    last_method = METHOD_CODES.get(last_settled.method, -1.0) if last_settled else -1.0

    streak = 0
    for d, _, _ in reversed(obs):
        if d > 5:
            break
        streak += 1

    prev_outstanding = 0.0
    if priors:
        d_prev, settled_prev, p_prev = obs[-1]
        if not settled_prev:
            prev_outstanding = float(max(0, (as_of - p_prev.due_date).days))

    tenure = _month_diff(ctx.lease.start_date, cycle)
    prior_cycles = len(priors)
    is_cold = 1.0 if prior_cycles < 3 else 0.0

    row: dict = {
        "lease_id": ctx.lease.id,
        "cycle_month": cycle,
        "as_of": as_of,
        "late_count_1": count_late(1),
        "late_share_1": share_late(1),
        "late_count_3": count_late(3),
        "late_share_3": share_late(3),
        "late_count_6": count_late(MAX_HISTORY),
        "late_share_6": share_late(MAX_HISTORY),
        "mean_days_late_6": float(np.mean(days_vals)) if days_vals else 0.0,
        "max_days_late_6": float(np.max(days_vals)) if days_vals else 0.0,
        "days_late_trend": _slope(days_vals),
        "on_time_streak": float(streak),
        "prev_cycle_outstanding_days": prev_outstanding,
        "tenure_months": float(tenure),
        "is_cold_start": is_cold,
        "rent_amount": known_rent,
        "rent_change_pct": max(0.0, rent_change_pct),
        "cycles_since_rent_change": float(cycles_since_change),
        "cash_share_last_6": cash_share,
        "last_payment_method": last_method,
        "due_day": float(ctx.lease.due_day),
        "cycle_month_of_year": float(cycle.month),
        "is_festival_month": 1.0 if cycle.month in FESTIVAL_MONTHS else 0.0,
        "bhk": float(ctx.unit.bhk),
        "occupation_salaried": 1.0 if ctx.tenant.occupation_type == "salaried" else 0.0,
        "occupation_business": 1.0 if ctx.tenant.occupation_type == "business" else 0.0,
        "occupation_student": 1.0 if ctx.tenant.occupation_type == "student" else 0.0,
        "occupation_gig": 1.0 if ctx.tenant.occupation_type == "gig" else 0.0,
        "preferred_language": ctx.tenant.preferred_language,
        "property_id": float(ctx.unit.property_id),
        "occupation_type": ctx.tenant.occupation_type,
        "prior_cycles": prior_cycles,
    }

    if include_target:
        if due.paid_date is None:
            row["is_late"] = 1  # never paid within the window
            row["days_late"] = 31.0
        else:
            dl = float((due.paid_date - due.due_date).days)
            row["is_late"] = int(dl > 5)
            row["days_late"] = dl
    return row


def _build_frame(
    session: Session, include_target: bool, only_cycle: date | None = None
) -> tuple[pd.DataFrame, list[dict]]:
    """Core frame builder shared by training and scoring paths."""
    contexts = _load_contexts(session)
    cycles = sorted({p.cycle_month for ctx in contexts for p in ctx.payments})
    if only_cycle is not None:
        cycles = [only_cycle]
    rows: list[dict] = []
    for ctx in contexts:
        for cycle in cycles:
            row = _row_for_cycle(ctx, cycle, include_target)
            if row is not None:
                rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df, [m.__dict__ for m in FEATURE_METADATA]
    df["cycle_month"] = pd.to_datetime(df["cycle_month"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    meta = [m.__dict__ for m in FEATURE_METADATA + AUDIT_METADATA]
    return df, meta


def build_training_frame(session: Session) -> tuple[pd.DataFrame, list[dict]]:
    """Build all training rows for every billed (lease, cycle) pair."""
    return _build_frame(session, include_target=True)


def build_current_frame(session: Session, cycle_month: date) -> tuple[pd.DataFrame, list[dict]]:
    """Build scoring rows for one cycle (defaults to the open cycle)."""
    return _build_frame(session, include_target=False, only_cycle=cycle_month)


def feature_metadata() -> list[dict]:
    """Feature metadata (name, dtype, plain-language template) for the explainer."""
    return [m.__dict__ for m in FEATURE_METADATA]
