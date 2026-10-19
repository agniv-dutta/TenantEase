"""Synthetic rent-payment data generator for TenantEase Khata.

Every row in the database is synthetic. Names and phone numbers come from
``faker`` with the ``en_IN`` locale only. Randomness is seeded so runs are
reproducible.

Generating process (also documented in ``docs/synthetic_data.md``):

* Each tenant has a hidden reliability value ``z`` (never stored in the DB)
  drawn from a distribution that depends on ``occupation_type``.
* The probability of paying more than 5 days late is a logistic function of
  ``z`` (sign-flipped so lower reliability raises risk), autocorrelation from
  the previous cycle, a festival-month flag (Oct/Nov Diwali, April), a recent
  rent hike (first 2 cycles after), cash payment share, short tenure
  (< 4 months), and Gaussian noise.
* If late, ``days_late`` is exponential with median about 6, capped at 30.
  If not late, ``days_late`` is uniform 0-5.
* A few partial payments and a few never-paid-within-30-days cases are added.
* The intercept of the logistic is numerically tuned so the base rate of
  "more than 5 days late" lands between 15% and 22% (target ~18.5%).

CLI: ``python -m app.ml.synth --seed 42 --out data/khata.db`` (idempotent:
drops and recreates all tables).
"""

from __future__ import annotations

import argparse
import calendar
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from faker import Faker
from sqlmodel import Session, SQLModel, create_engine, select

from app import clock
from app.models import Lease, Meta, Payment, Property, Tenant, Unit

LOCALITIES = [
    ("Mansarovar", 1.00),
    ("Malviya Nagar", 1.20),
    ("Vaishali Nagar", 1.05),
    ("Jagatpura", 0.85),
    ("C-Scheme", 1.35),
    ("Sodala", 0.90),
]
PROPERTY_NAMES = [
    "Shanti Residency",
    "Padmavati Enclave",
    "Jai Mahal Apartments",
    "Gulmohar Villa",
    "Amber Heights",
    "Chandralok House",
]
PROPERTY_UNITS = [30, 28, 24, 22, 20, 16]  # ~140 units total
BHK_BASE_RENT = {1: 9_000, 2: 15_000, 3: 24_000}
BHK_MIX = [0.35, 0.45, 0.20]
OCCUPATION_Z = {
    "salaried": (1.2, 0.8),
    "business": (0.4, 1.4),  # most variable
    "student": (-0.2, 1.0),
    "gig": (0.0, 1.0),
}
OCCUPATION_WEIGHTS = [0.50, 0.25, 0.12, 0.13]
LANGUAGE_WEIGHTS = [0.45, 0.20, 0.35]  # en, hi, hinglish
CHANNEL_WEIGHTS = [0.55, 0.25, 0.20]  # whatsapp, sms, call
METHOD_BY_OCCUPATION = {
    "salaried": [0.60, 0.22, 0.18],
    "business": [0.48, 0.32, 0.20],
    "student": [0.42, 0.45, 0.13],
    "gig": [0.45, 0.42, 0.13],
}  # upi, cash, bank_transfer
DUE_DAYS = [1, 5, 10]
FESTIVAL_MONTHS = {10, 11, 4}
CHURN_PROB = 0.15
POST_CHURN_RELET_PROB = 0.70
TARGET_BASE_RATE = 0.185
PARTIAL_PROB = 0.03
NEVER_PAID_PROB = 0.02


def month_add(d: date, n: int) -> date:
    """Return the first day of the month ``n`` months after ``d``'s month."""
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def last_day_of_month(d: date) -> date:
    """Return the last calendar day of ``d``'s month."""
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def due_date_for(cycle_month: date, due_day: int) -> date:
    """Return the due date for a cycle given the day of month rent is due."""
    return min(cycle_month.replace(day=due_day), last_day_of_month(cycle_month))


@dataclass
class RentStep:
    """A rent amount effective from a cycle month onward."""

    effective: date
    rent: int


@dataclass
class LeaseSpell:
    """One tenancy and the rent schedule that applies to it."""

    unit_id: int
    tenant_id: int
    start_date: date
    end_date: date | None
    due_day: int
    deposit: int
    rent_steps: list[RentStep] = field(default_factory=list)

    def rent_for_cycle(self, cycle: date) -> int:
        """Rent in effect for a cycle month."""
        rent = self.rent_steps[0].rent
        for step in self.rent_steps:
            if step.effective <= cycle:
                rent = step.rent
        return rent

    def active_in_cycle(self, cycle: date) -> bool:
        """Whether the lease is active at any point during the cycle month."""
        if self.start_date > last_day_of_month(cycle):
            return False
        if self.end_date is not None and self.end_date < cycle:
            return False
        return True


@dataclass
class Outcome:
    """The payment outcome for one (lease, cycle) pair."""

    cycle: date
    paid_date: date | None
    days_late: int | None
    amount: int
    method: str
    is_partial: bool


def build_structure(seed: int, n_closed_cycles: int, open_cycle: date) -> tuple[list, list, list, list]:
    """Draw properties, units, tenants and lease spells deterministically."""
    rng = np.random.default_rng(seed)
    fake = Faker("en_IN")
    Faker.seed(seed)

    properties: list[Property] = []
    units: list[Unit] = []
    for pidx, ((locality, loc_factor), n_units) in enumerate(zip(LOCALITIES, PROPERTY_UNITS)):
        properties.append(Property(id=pidx + 1, name=PROPERTY_NAMES[pidx], locality=locality))
        for uidx in range(n_units):
            bhk = int(rng.choice([1, 2, 3], p=BHK_MIX))
            base = BHK_BASE_RENT[bhk] * loc_factor * float(rng.lognormal(0, 0.12))
            rent = int(min(35_000, max(6_000, round(base / 500) * 500)))
            units.append(
                Unit(
                    id=len(units) + 1,
                    property_id=pidx + 1,
                    label=f"{locality.split()[0][:3].upper()}-{uidx + 1:02d}",
                    bhk=bhk,
                    rent_inr=rent,
                    floor=int(rng.integers(0, 5)),
                )
            )

    # Leases can start from the first closed cycle; every cycle in the window
    # then has a tenant from day one.
    window_start = month_add(open_cycle, -n_closed_cycles)
    tenants: list[Tenant] = []
    spells: list[LeaseSpell] = []

    def new_tenant() -> Tenant:
        occ = str(rng.choice(list(OCCUPATION_Z), p=OCCUPATION_WEIGHTS))
        t = Tenant(
            id=len(tenants) + 1,
            name=fake.name(),
            phone=fake.phone_number(),
            occupation_type=occ,
            preferred_language=str(rng.choice(["en", "hi", "hinglish"], p=LANGUAGE_WEIGHTS)),
            preferred_channel=str(rng.choice(["whatsapp", "sms", "call"], p=CHANNEL_WEIGHTS)),
        )
        tenants.append(t)
        return t

    def make_spell(unit: Unit, start: date, rng_local: np.random.Generator) -> LeaseSpell:
        due_day = int(rng_local.choice(DUE_DAYS))
        initial_rent = unit.rent_inr
        steps = [RentStep(effective=start, rent=initial_rent)]
        rent = initial_rent
        # Anniversaries: some leases get a 5-10% hike.
        anniv = month_add(start, 12)
        while anniv < open_cycle:
            if rng_local.random() < 0.5:
                rent = int(round(rent * float(rng_local.uniform(1.05, 1.10)) / 500) * 500)
                steps.append(RentStep(effective=anniv, rent=rent))
            anniv = month_add(anniv, 12)
        return LeaseSpell(
            unit_id=unit.id,  # type: ignore[arg-type]
            tenant_id=new_tenant().id,  # type: ignore[arg-type]
            start_date=start,
            end_date=None,
            due_day=due_day,
            deposit=int(round(2 * initial_rent / 500) * 500),
            rent_steps=steps,
        )

    for unit in units:
        vacant_from_start = rng.random() < 0.10
        if vacant_from_start:
            start_offset = int(rng.integers(4, n_closed_cycles - 4))
            start = month_add(window_start, start_offset)
            if start < open_cycle:
                spells.append(make_spell(unit, start, rng))
            continue
        spell = make_spell(unit, window_start, rng)
        if rng.random() < CHURN_PROB:
            # Tenant leaves partway through the window (cold-start tenants appear later).
            leave_offset = int(rng.integers(6, n_closed_cycles - 3))
            leave = month_add(window_start, leave_offset)
            spell.end_date = leave - timedelta(days=1)
            spells.append(spell)
            if rng.random() < POST_CHURN_RELET_PROB:
                relet_start = month_add(leave, int(rng.integers(1, 3)))
                if relet_start < open_cycle:
                    spells.append(make_spell(unit, relet_start, rng))
        else:
            spells.append(spell)

    return properties, units, tenants, spells


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def simulate_outcomes(
    units: list[Unit],
    tenants: list[Tenant],
    spells: list[LeaseSpell],
    cycles: list[date],
    intercept: float,
    seed: int,
) -> list[Outcome]:
    """Replay the payment outcome process for every (lease, cycle) pair."""
    rng = np.random.default_rng(seed)
    tenant_by_id = {t.id: t for t in tenants}
    # Hidden reliability drawn ONCE per tenant and never stored in the DB.
    z_by_tenant: dict[int, float] = {
        t.id: float(rng.normal(*OCCUPATION_Z[t.occupation_type])) for t in tenants  # type: ignore[arg-type]
    }
    outcomes: list[Outcome] = []

    for spell in spells:
        prev_late = 0.0
        cash_recent: list[int] = []
        tenure = 0
        for cycle in cycles:
            if not spell.active_in_cycle(cycle):
                continue
            tenant = tenant_by_id[spell.tenant_id]
            z = z_by_tenant[spell.tenant_id]
            rent = spell.rent_for_cycle(cycle)
            due = due_date_for(cycle, spell.due_day)
            festival = 1.0 if cycle.month in FESTIVAL_MONTHS else 0.0
            hike_recent = any(
                0 < (cycle.year * 12 + cycle.month) - (s.effective.year * 12 + s.effective.month) <= 1
                for s in spell.rent_steps[1:]
            )
            cash_share = (sum(cash_recent) / len(cash_recent)) if cash_recent else 0.0
            short_tenure = 1.0 if tenure < 4 else 0.0

            logit = (
                intercept
                - 0.9 * z
                + 0.8 * prev_late
                + 0.5 * festival
                + 0.6 * (1.0 if hike_recent else 0.0)
                + 0.7 * cash_share
                + 0.5 * short_tenure
                + float(rng.normal(0, 0.8))
            )
            p_late = _logistic(logit)
            late = bool(rng.random() < p_late)

            is_partial = False
            never_paid = False
            if late:
                days_late = int(min(30, max(6, round(rng.exponential(6)))))
                if rng.random() < NEVER_PAID_PROB:
                    never_paid = True
                    paid_date = None
                    days_late = 31
                else:
                    paid_date = due + timedelta(days=days_late)
            else:
                days_late = int(rng.integers(0, 6))
                paid_date = due - timedelta(days=days_late)
                if paid_date < cycle:
                    paid_date = cycle
                    days_late = (due - paid_date).days

            method = str(rng.choice(["upi", "cash", "bank_transfer"], p=METHOD_BY_OCCUPATION[tenant.occupation_type]))
            cash_recent.append(1 if method == "cash" else 0)
            cash_recent = cash_recent[-6:]

            amount = rent
            if not never_paid and paid_date is not None and rng.random() < PARTIAL_PROB:
                is_partial = True
                amount = int(round(rent * float(rng.uniform(0.4, 0.8)) / 100) * 100)

            outcomes.append(
                Outcome(
                    cycle=cycle,
                    paid_date=paid_date,
                    days_late=days_late if paid_date is not None or never_paid else None,
                    amount=amount,
                    method=method,
                    is_partial=is_partial,
                )
            )
            prev_late = 1.0 if days_late > 5 else 0.0
            tenure += 1
    return outcomes


def base_rate(outcomes: list[Outcome]) -> float:
    """Fraction of outcomes with more than 5 days late (never-paid counts as late)."""
    late = sum(1 for o in outcomes if o.days_late is not None and o.days_late > 5)
    return late / max(1, len(outcomes))


def tune_intercept(
    units: list[Unit], tenants: list[Tenant], spells: list[LeaseSpell], cycles: list[date], seed: int
) -> float:
    """Binary-search the logistic intercept so the base rate is ~18.5%."""
    lo, hi = -4.0, 2.0
    for _ in range(20):
        mid = (lo + hi) / 2
        outcomes = simulate_outcomes(units, tenants, spells, cycles, mid, seed + 1)
        rate = base_rate(outcomes)
        if rate < 0.15:
            lo = mid
        elif rate > 0.22:
            hi = mid
        else:
            if abs(rate - TARGET_BASE_RATE) < 0.005:
                return mid
            if rate < TARGET_BASE_RATE:
                lo = mid
            else:
                hi = mid
    return (lo + hi) / 2


def write_db(db_path: str, seed: int) -> dict[str, int | str]:
    """Generate the full synthetic database at ``db_path``. Idempotent.

    The calendar is laid out around ``DEMO_TODAY`` (see :mod:`app.clock`): the
    open cycle is the month containing it and the closed cycles are the
    contiguous months before it, so the ledger never skips a month. The seed
    records the demo date in the ``meta`` table.
    """
    open_cycle = clock.open_cycle()
    demo_today = clock.today()
    n_closed_cycles = 24
    cycles = [month_add(open_cycle, -(n_closed_cycles - i)) for i in range(n_closed_cycles)]

    properties, units, tenants, spells = build_structure(seed, n_closed_cycles, open_cycle)
    intercept = tune_intercept(units, tenants, spells, cycles, seed)
    outcomes = simulate_outcomes(units, tenants, spells, cycles, intercept, seed + 1)

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    n_payments = 0
    with Session(engine) as session:
        # Record what the data was generated for: same seed, same demo date.
        session.add(Meta(key="demo_today", value=demo_today.isoformat()))
        session.add(Meta(key="seed", value=str(seed)))
        session.commit()

        for p in properties:
            session.add(p)
        for u in units:
            session.add(u)
        for t in tenants:
            session.add(t)
        session.commit()

        idx = 0
        for spell in spells:
            session.add(
                Lease(
                    unit_id=spell.unit_id,
                    tenant_id=spell.tenant_id,
                    start_date=spell.start_date,
                    end_date=spell.end_date,
                    monthly_rent=spell.rent_for_cycle(open_cycle),
                    due_day=spell.due_day,
                    deposit=spell.deposit,
                )
            )
        session.commit()
        lease_rows = session.exec(select(Lease)).all()
        lease_by_key = {(lease.unit_id, lease.tenant_id): lease.id for lease in lease_rows}

        for s_idx, spell in enumerate(spells):
            lease_id = lease_by_key[(spell.unit_id, spell.tenant_id)]
            for c_idx, cycle in enumerate(cycles):
                if not spell.active_in_cycle(cycle):
                    continue
                o = outcomes[idx]
                idx += 1
                assert o.cycle == cycle
                session.add(
                    Payment(
                        lease_id=lease_id,
                        cycle_month=cycle,
                        due_date=due_date_for(cycle, spell.due_day),
                        paid_date=o.paid_date,
                        amount=o.amount,
                        method=o.method,
                    )
                )
                n_payments += 1
            # Open current cycle: rows exist but nothing is paid yet.
            session.add(
                Payment(
                    lease_id=lease_id,
                    cycle_month=open_cycle,
                    due_date=due_date_for(open_cycle, spell.due_day),
                    paid_date=None,
                    amount=spell.rent_for_cycle(open_cycle),
                    method="upi",
                )
            )
            n_payments += 1
        session.commit()

    return {
        "properties": len(properties),
        "units": len(units),
        "tenants": len(tenants),
        "leases": len(spells),
        "payments": n_payments,
        "closed_cycles": n_closed_cycles,
        "demo_today": demo_today.isoformat(),
        "base_rate": round(base_rate(outcomes), 4),
        "intercept": round(intercept, 4),
    }


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Generate synthetic Khata data")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="data/khata.db")
    args = parser.parse_args(argv)
    stats = write_db(args.out, args.seed)
    print(f"Wrote {args.out} for demo date {stats['demo_today']} (seed {args.seed})")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
