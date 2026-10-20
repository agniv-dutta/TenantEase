"""Match parsed fields to candidate leases (never a decision).

Scores every active lease's tenant name against the payer-name guess with
rapidfuzz, then adds deterministic boosts when the message amount equals the
rent and when the lease has an open cycle. The result is a ranked short list
with plain-language reasons; a person always makes the final call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz
from sqlmodel import Session, select

from app import clock
from app.config import settings
from app.models import Lease, Payment, Tenant, Unit


@dataclass
class LeaseMatch:
    """One candidate lease with its score and the reasons behind it."""

    lease_id: int
    tenant: str
    unit: str
    cycle_month: date | None
    score: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """JSON-serialisable form."""
        return {
            "lease_id": self.lease_id,
            "tenant": self.tenant,
            "unit": self.unit,
            "cycle_month": self.cycle_month.isoformat() if self.cycle_month else None,
            "score": round(self.score, 1),
            "reasons": self.reasons,
        }


def _best_name_score(name_guess: str, tenant_name: str) -> float:
    """Best of several fuzzy comparisons between the guess and the real name.

    ``WRatio`` handles word reordering and abbreviations better than the plain
    ratio, and comparing against the individual name tokens avoids the way
    ``partial_ratio`` inflates a short guess against a longer string.
    """
    guess = name_guess.strip().lower()
    if not guess:
        return 0.0
    full = tenant_name.strip().lower()
    tokens = [t for t in full.split() if t]
    if not tokens:
        tokens = [full]
    candidates = [full, *tokens]
    return float(max(fuzz.WRatio(guess, candidate) for candidate in candidates))


def match_leases(
    session: Session,
    payer_name_guess: str | None,
    amount: int | None,
    limit: int = 3,
) -> list[LeaseMatch]:
    """Rank active leases for a parsed message and return the top ``limit``.

    Only leases that have a bill for the open cycle are candidates, so the
    short list can never point at a former tenant.
    """
    open_cycle = clock.open_cycle()
    units = {u.id: u for u in session.exec(select(Unit)).all()}
    tenants = {t.id: t for t in session.exec(select(Tenant)).all()}

    results: list[LeaseMatch] = []
    for lease in session.exec(select(Lease)).all():
        payments = session.exec(
            select(Payment).where(Payment.lease_id == lease.id).order_by(Payment.cycle_month)
        ).all()
        if not payments or payments[-1].cycle_month != open_cycle:
            continue  # not active in the open cycle
        tenant = tenants[lease.tenant_id]
        unit = units[lease.unit_id]

        name_score = _best_name_score(payer_name_guess or "", tenant.name)
        score = name_score
        reasons: list[str] = []
        if payer_name_guess:
            if name_score >= 85:
                reasons.append("Name matches closely")
            elif name_score >= 60:
                reasons.append("Name is a partial match")
            else:
                reasons.append("Name does not match closely")

        open_payment = payments[-1]
        if amount is not None and amount == open_payment.amount:
            score += 25
            reasons.append("Amount equals the rent due")
        elif amount is not None and amount == lease.monthly_rent:
            score += 20
            reasons.append("Amount equals the rent")

        score += 10
        reasons.append(f"{open_cycle.strftime('%B')} is the open cycle")

        results.append(
            LeaseMatch(
                lease_id=lease.id,  # type: ignore[arg-type]
                tenant=tenant.name,
                unit=unit.label,
                cycle_month=open_cycle,
                score=min(score, 100.0),
                reasons=reasons,
            )
        )

    results.sort(key=lambda m: (-m.score, m.tenant))
    return [m for m in results if m.score >= settings.payment_match_cutoff][:limit]
