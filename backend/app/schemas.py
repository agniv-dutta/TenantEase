"""Pydantic response/request schemas for the Khata API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Consistent error envelope."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Wrapper matching ``{"error": {...}}``."""

    error: ErrorBody


class TierCounts(BaseModel):
    """Number of leases per risk tier for the open cycle."""

    low: int
    medium: int
    high: int


class PortfolioSummary(BaseModel):
    """High-level portfolio numbers for the open cycle."""

    properties: int
    active_leases: int
    expected_collection_inr: int
    total_rent_due_inr: int
    tiers: TierCounts
    cycle_month: date
    as_of_date: date


class PaymentCell(BaseModel):
    """One cycle cell in the ledger."""

    cycle_month: date
    due_date: date
    status: str  # paid_on_time | paid_late | unpaid_overdue | unpaid_upcoming | open
    paid_date: date | None = None
    days_late: int | None = None
    amount: int
    probability: float | None = None
    tier: str | None = None


class LedgerRow(BaseModel):
    """One lease row in the ledger table."""

    lease_id: int
    tenant_name: str
    unit_label: str
    property_name: str
    property_id: int
    occupation_type: str
    preferred_language: str
    preferred_channel: str
    cycles: list[PaymentCell]
    current: PaymentCell


class LedgerResponse(BaseModel):
    """Ledger payload."""

    cycle_month: date
    rows: list[LedgerRow]


class Factor(BaseModel):
    """One plain-language explanation factor.

    There is deliberately no weight field: a SHAP value is not a share of the
    probability, so showing it as a percentage would be misleading.
    """

    feature: str
    sentence: str
    direction: str  # raises | lowers
    strength: str  # main | moderate | minor


class PlanStep(BaseModel):
    """One step in the reminder plan."""

    offset_days: int
    date: date
    channel: str
    tone: str
    owner: str  # system | manager


class TenantDetail(BaseModel):
    """Full tenant drawer payload."""

    lease_id: int
    tenant_id: int
    tenant_name: str
    unit_label: str
    property_name: str
    rent_inr: int
    due_day: int
    occupation_type: str
    preferred_language: str
    preferred_channel: str
    tenure_months: int
    prior_cycles: int
    history: list[PaymentCell]
    probability: float | None = None
    tier: str | None = None
    top_factors: list[Factor]
    plan: list[PlanStep]
    reminders: list[ReminderOut]
    cold_start: bool = False


class ReminderOut(BaseModel):
    """A reminder as returned by the API."""

    id: int
    lease_id: int
    cycle_month: date
    channel: str
    tone: str
    language: str
    message: str
    status: str
    created_at: datetime
    approved_at: datetime | None = None
    guardrails: list[dict[str, Any]] = Field(default_factory=list)
    fallback: bool = False


class DraftRequest(BaseModel):
    """Request body for drafting a reminder."""

    lease_id: int
    language: str  # en | hi | hinglish
    tone: str  # friendly | neutral | polite_firm


class CheckRequest(BaseModel):
    """Request body for re-checking an edited reminder message."""

    lease_id: int
    language: str
    message: str


class GuardrailResult(BaseModel):
    """One guardrail outcome."""

    name: str
    passed: bool
    reason: str


class MaintenanceCreate(BaseModel):
    """Request body for triaging a maintenance complaint."""

    lease_id: int
    text: str


class MaintenanceOut(BaseModel):
    """A triaged maintenance request as returned by the API."""

    id: int
    lease_id: int
    text: str
    category: str
    urgency: str
    suggested_trade: str
    summary: str
    method: str
    forced_emergency: bool
    created_at: datetime


class OutlookPoint(BaseModel):
    """One point on the cumulative collections curve."""

    day: int
    p10: float
    expected: float
    p90: float


class OutlookResponse(BaseModel):
    """Outlook chart payload."""

    cycle_month: date
    total_due: int
    points: list[OutlookPoint]
    likely_late_count: int
    as_of_date: date


class ModelCardResponse(BaseModel):
    """Model notes payload."""

    metrics: dict[str, Any]
    slices: dict[str, Any]
    card_markdown: str
