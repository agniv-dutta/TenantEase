"""Portfolio summary and collections outlook endpoints."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import clock
from app.db import get_session
from app.ml.scoring import current_cycle
from app.models import Lease, Payment, Property, RiskScore, Unit
from app.schemas import OutlookPoint, OutlookResponse, PortfolioSummary, TierCounts

router = APIRouter()


@router.get("/occupancy")
def occupancy(session: Session = Depends(get_session)) -> dict:
    """Return current occupancy grouped by property and vacant unit detail."""
    today = clock.today()
    properties = session.exec(select(Property)).all()
    units = session.exec(select(Unit)).all()
    leases = session.exec(select(Lease)).all()
    active_by_unit: dict[int, Lease] = {}
    for lease in leases:
        if lease.start_date <= today and (lease.end_date is None or lease.end_date >= today):
            active_by_unit[lease.unit_id] = lease
    props = []
    vacant = []
    for prop in properties:
        rows = [u for u in units if u.property_id == prop.id]
        occupied = sum(u.id in active_by_unit for u in rows)
        props.append({"property_id": prop.id, "property": prop.name, "units": len(rows), "occupied": occupied,
                      "vacant": len(rows)-occupied, "occupancy_rate": occupied / len(rows) if rows else 0})
        for unit in rows:
            if unit.id not in active_by_unit:
                start = unit.vacant_since or today
                vacant.append({"unit": unit.label, "property": prop.name, "bhk": unit.bhk,
                               "rent_inr": unit.rent_inr, "vacant_since": start,
                               "days_vacant": max(0, (today-start).days)})
    total_units = len(units)
    total_occupied = len(active_by_unit)
    return {"properties": props, "total": {"units": total_units, "occupied": total_occupied,
            "vacant": total_units-total_occupied, "occupancy_rate": total_occupied/total_units if total_units else 0},
            "vacant_units": sorted(vacant, key=lambda x: x["days_vacant"], reverse=True),
            "as_of_date": today}


@router.get("/revenue")
def revenue(months: int = 24, session: Session = Depends(get_session)) -> dict:
    """Return billed and collected rent totals for recent ledger cycles."""
    if not 1 <= months <= 60:
        raise HTTPException(status_code=422, detail={"code": "invalid_months", "message": "Months must be between 1 and 60."})
    current = current_cycle(session)
    first = _month_offset(current, -(months - 1))
    payments = session.exec(select(Payment).where(Payment.cycle_month >= first, Payment.cycle_month <= current)).all()
    cycles = []
    for i in range(months):
        cycle = _month_offset(first, i)
        rows = [p for p in payments if p.cycle_month == cycle]
        cycles.append({"cycle_month": cycle, "billed": sum(p.amount for p in rows),
                       "collected": sum(p.amount for p in rows if p.paid_date is not None),
                       "within_grace": sum(p.amount for p in rows if p.paid_date is not None and p.paid_date <= p.due_date + timedelta(days=5))})
    return {"months": cycles, "as_of_date": clock.today()}


@router.get("/collection-efficiency")
def collection_efficiency(session: Session = Depends(get_session)) -> dict:
    """Return monthly on-time collection share and risk-model open-cycle forecast."""
    series = revenue(25, session)
    months = [{"cycle_month": row["cycle_month"], "billed": row["billed"], "within_grace": row["within_grace"],
               "share": row["within_grace"] / row["billed"] if row["billed"] else 0.0}
              for row in series["months"][:-1]]
    current = current_cycle(session)
    rows = session.exec(select(Payment).where(Payment.cycle_month == current)).all()
    scores = {s.lease_id: s for s in session.exec(select(RiskScore).where(RiskScore.cycle_month == current)).all()}
    billed = sum(p.amount for p in rows)
    expected = sum(p.amount * (1 - scores[p.lease_id].probability if p.lease_id in scores else 1.0) for p in rows)
    return {"months": months, "forecast": {"cycle_month": current, "billed": billed,
            "expected_within_grace": expected, "share": expected / billed if billed else 0.0}, "as_of_date": clock.today()}


def _month_offset(value: date, offset: int) -> date:
    """Return the first day of a month offset from value."""
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


@router.get("/spotlight")
def spotlight(session: Session = Depends(get_session)) -> dict[str, int]:
    """Return the eligible lease with the highest raw late-risk score."""
    cycle = current_cycle(session)
    scores = session.exec(select(RiskScore).where(RiskScore.cycle_month == cycle)).all()
    eligible: list[tuple[float, int]] = []
    for score in scores:
        history = session.exec(
            select(Payment).where(Payment.lease_id == score.lease_id, Payment.cycle_month < cycle)
        ).all()
        if len(history) >= 3:
            eligible.append((score.raw_score, score.lease_id))
    if not eligible:
        raise HTTPException(status_code=404, detail={"code": "no_spotlight", "message": "No lease has three closed cycles yet."})
    return {"lease_id": max(eligible)[1]}

MC_DRAWS = 500


def _as_of_for(target: date) -> date:
    """The demo date, capped at the last day of the cycle being viewed.

    The open cycle is observed up to ``DEMO_TODAY``; an older cycle was
    already fully observed by then.
    """
    last_day = date(target.year, target.month, calendar.monthrange(target.year, target.month)[1])
    return min(clock.today(), last_day)


def _active_leases(session: Session, cycle: date) -> list[Lease]:
    """Leases billed in the given cycle."""
    lease_ids = {
        p.lease_id for p in session.exec(select(Payment).where(Payment.cycle_month == cycle)).all()
    }
    return [l for l in session.exec(select(Lease)).all() if l.id in lease_ids]  # noqa: E741


@router.get("/summary", response_model=PortfolioSummary)
def summary(session: Session = Depends(get_session)) -> PortfolioSummary:
    """Portfolio numbers for the open cycle."""
    cycle = current_cycle(session)
    leases = _active_leases(session, cycle)
    payments = session.exec(select(Payment).where(Payment.cycle_month == cycle)).all()
    total_due = int(sum(p.amount for p in payments))

    scores = {
        s.lease_id: s
        for s in session.exec(select(RiskScore).where(RiskScore.cycle_month == cycle)).all()
    }
    counts = {"low": 0, "medium": 0, "high": 0}
    expected = 0.0
    for p in payments:
        score = scores.get(p.lease_id)
        prob = score.probability if score else 0.0
        tier = score.tier if score else "low"
        counts[tier] = counts.get(tier, 0) + 1
        expected += p.amount * (1.0 - prob)
    return PortfolioSummary(
        properties=len(session.exec(select(Property)).all()),
        active_leases=len(leases),
        expected_collection_inr=int(round(expected)),
        total_rent_due_inr=total_due,
        tiers=TierCounts(**counts),
        cycle_month=cycle,
        as_of_date=clock.today(),
    )


@router.get("/outlook", response_model=OutlookResponse)
def outlook(cycle: str | None = None, session: Session = Depends(get_session)) -> OutlookResponse:
    """Per-day expected cumulative collections with a p10-p90 band.

    Uses 500 Monte Carlo draws over per-lease late probabilities and a simple
    days-late distribution. The distribution is synthetic and illustrative.
    """
    target = current_cycle(session) if cycle is None else _parse_cycle(cycle)
    payments = session.exec(select(Payment).where(Payment.cycle_month == target)).all()
    scores = {
        s.lease_id: s
        for s in session.exec(select(RiskScore).where(RiskScore.cycle_month == target)).all()
    }
    rng = np.random.default_rng(42)
    n = len(payments)
    probs = np.array([scores[p.lease_id].probability if p.lease_id in scores else 0.0 for p in payments])
    amounts = np.array([float(p.amount) for p in payments])
    due_days = np.array([p.due_date.day for p in payments])
    last_day = max((p.due_date.day for p in payments), default=30)
    last_day = max(last_day, 28)

    # Draw: late/when paid. Not late -> paid 0-5 days after due. Late -> exponential.
    draws = np.zeros((MC_DRAWS, n))
    for d in range(MC_DRAWS):
        late = rng.random(n) < probs
        offset = np.where(
            late,
            np.minimum(30, 6 + rng.exponential(6, n)),
            rng.integers(0, 6, n),
        )
        draws[d] = np.round(due_days + offset)

    points: list[OutlookPoint] = []
    for day in range(1, last_day + 1):
        collected = (amounts * (draws <= day)).sum(axis=1)  # per draw
        points.append(
            OutlookPoint(
                day=day,
                p10=float(np.percentile(collected, 10)),
                expected=float(np.mean(collected)),
                p90=float(np.percentile(collected, 90)),
            )
        )
    likely_late = int(round(float(probs.sum())))
    return OutlookResponse(
        cycle_month=target,
        total_due=int(amounts.sum()),
        points=points,
        likely_late_count=likely_late,
        as_of_date=_as_of_for(target),
    )


def _parse_cycle(text: str) -> date:
    """Parse YYYY-MM into the first day of that month."""
    try:
        y, m = text.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_cycle", "message": "Cycle must look like 2026-10."})
