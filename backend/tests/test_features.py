"""Leakage tests for the as-of feature pipeline."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlmodel import Session, create_engine, select

from app import clock
from app.ml.features import build_current_frame, build_training_frame, feature_columns
from app.ml.synth import write_db
from app.models import Lease, Payment, Tenant, Unit


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """One seeded database shared by this module."""
    path = str(tmp_path_factory.mktemp("data") / "khata.db")
    write_db(path, seed=42)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    with Session(engine) as s:
        yield s


def _independent_features(
    lease: Lease, unit: Unit, tenant: Tenant, payments: list[Payment], cycle: date
) -> dict[str, float]:
    """Recompute each feature from only records with timestamps <= as_of."""
    due = next(p for p in payments if p.cycle_month == cycle)
    # Same rule as the pipeline: seven days before the due date, never later
    # than the demo clock.
    as_of = min(due.due_date - timedelta(days=7), clock.today())
    priors = [p for p in payments if p.cycle_month < cycle]

    obs: list[tuple[float, bool]] = []
    for p in priors:
        if p.paid_date is not None and p.paid_date <= as_of:
            obs.append((float((p.paid_date - p.due_date).days), True))
        else:
            obs.append((float(max(0, (as_of - p.due_date).days)), False))
    recent = obs[-6:]

    def cnt(n: int) -> float:
        return float(sum(1 for d, _ in obs[-n:] if d > 5))

    def shr(n: int) -> float:
        w = obs[-n:]
        return cnt(n) / len(w) if w else 0.0

    days_vals = [d for d, _ in recent]
    settled_amts = [float(p.amount) for (d, s), p in list(zip(obs, priors))[-6:] if s]
    known_rent = max([float(unit.rent_inr)] + settled_amts)

    hist_rents = [float(unit.rent_inr)]
    changed_at: date | None = None
    for (d, s), p in zip(obs, priors):
        if s and float(p.amount) > hist_rents[-1]:
            hist_rents.append(float(p.amount))
            changed_at = p.cycle_month
    rent_change_pct = 0.0
    if len(hist_rents) >= 2:
        rent_change_pct = (hist_rents[-1] - hist_rents[-2]) / hist_rents[-2] * 100.0
    start_m = (lease.start_date.year * 12 + lease.start_date.month)
    cyc_m = cycle.year * 12 + cycle.month
    cycles_since = (cyc_m - start_m) if changed_at is None else (cyc_m - (changed_at.year * 12 + changed_at.month))

    cash_flags = [p.method == "cash" for (d, s), p in list(zip(obs, priors))[-6:] if s]
    cash_share = sum(cash_flags) / len(cash_flags) if cash_flags else 0.0
    last_method_code = -1.0
    for (d, s), p in zip(reversed(obs), reversed(priors)):
        if s:
            last_method_code = {"upi": 0.0, "cash": 1.0, "bank_transfer": 2.0}.get(p.method, -1.0)
            break
    streak = 0
    for d, _ in reversed(obs):
        if d > 5:
            break
        streak += 1
    prev_out = 0.0
    if obs and not obs[-1][1]:
        prev_out = float(max(0, (as_of - priors[-1].due_date).days))
    tenure = (cyc_m - start_m)
    ys = np.asarray(days_vals, dtype=float)
    slope = 0.0
    if len(ys) >= 3:
        xs = np.arange(len(ys), dtype=float)
        xm, ym = xs.mean(), ys.mean()
        denom = ((xs - xm) ** 2).sum()
        if denom:
            slope = float(((xs - xm) * (ys - ym)).sum() / denom)

    return {
        "late_count_1": cnt(1),
        "late_share_1": shr(1),
        "late_count_3": cnt(3),
        "late_share_3": shr(3),
        "late_count_6": cnt(6),
        "late_share_6": shr(6),
        "mean_days_late_6": float(np.mean(days_vals)) if days_vals else 0.0,
        "max_days_late_6": float(np.max(days_vals)) if days_vals else 0.0,
        "days_late_trend": slope,
        "on_time_streak": float(streak),
        "prev_cycle_outstanding_days": prev_out,
        "tenure_months": float(tenure),
        "is_cold_start": 1.0 if len(priors) < 3 else 0.0,
        "rent_amount": known_rent,
        "rent_change_pct": max(0.0, rent_change_pct),
        "cycles_since_rent_change": float(cycles_since),
        "cash_share_last_6": cash_share,
        "last_payment_method": last_method_code,
        "due_day": float(lease.due_day),
        "cycle_month_of_year": float(cycle.month),
        "is_festival_month": 1.0 if cycle.month in {10, 11, 4} else 0.0,
        "bhk": float(unit.bhk),
        "occupation_salaried": 1.0 if tenant.occupation_type == "salaried" else 0.0,
        "occupation_business": 1.0 if tenant.occupation_type == "business" else 0.0,
        "occupation_student": 1.0 if tenant.occupation_type == "student" else 0.0,
        "occupation_gig": 1.0 if tenant.occupation_type == "gig" else 0.0,
    }


def test_no_excluded_columns(session: Session) -> None:
    """Name, phone, property, locality and language never become features."""
    cols = set(feature_columns())
    assert not any(c in cols for c in ("name", "phone", "property", "locality", "preferred_language"))
    assert "occupation_salaried" in cols  # default flag on


def test_as_of_recompute_sample(session: Session) -> None:
    """For 200 sampled rows, independently recomputed features match exactly."""
    df, _ = build_training_frame(session)
    leases = {l.id: l for l in session.exec(select(Lease)).all()}  # noqa: E741
    units = {u.id: u for u in session.exec(select(Unit)).all()}
    tenants = {t.id: t for t in session.exec(select(Tenant)).all()}
    pays_by_lease: dict[int, list[Payment]] = {}
    for p in session.exec(select(Payment).order_by(Payment.cycle_month)).all():
        pays_by_lease.setdefault(p.lease_id, []).append(p)

    rng = np.random.default_rng(7)
    sample_idx = rng.choice(len(df), size=min(200, len(df)), replace=False)
    cols = feature_columns()
    for i in sample_idx:
        row = df.iloc[int(i)]
        lease = leases[int(row["lease_id"])]
        cycle = row["cycle_month"].date()
        expected = _independent_features(
            lease, units[lease.unit_id], tenants[lease.tenant_id], pays_by_lease[lease.id], cycle  # type: ignore[index]
        )
        for c in cols:
            assert abs(float(row[c]) - expected[c]) < 1e-9, (
                f"row {i} feature {c}: frame={row[c]} independent={expected[c]}"
            )


def test_shuffling_future_payments_does_not_change_features(session: Session) -> None:
    """Shuffling payment outcomes after a cutoff must not move as-of features."""
    df, _ = build_training_frame(session)
    all_cycles = sorted(df["cycle_month"].unique())
    cutoff_cycle = pd.Timestamp(all_cycles[19])  # rows up to cycle index 19
    horizon = pd.Timestamp(all_cycles[19]) + pd.offsets.MonthEnd(0)

    payments = session.exec(select(Payment)).all()
    future = [p for p in payments if p.cycle_month > cutoff_cycle.date()]
    rng = np.random.default_rng(3)
    dates = [p.paid_date for p in future]
    methods = [p.method for p in future]
    rng.shuffle(dates)
    rng.shuffle(methods)
    for p, d, m in zip(future, dates, methods):
        p.paid_date = d
        p.method = m
    session.commit()

    df2, _ = build_training_frame(session)
    key = ["lease_id", "cycle_month"]
    m1 = df[df["cycle_month"] <= horizon].set_index(key).sort_index()
    m2 = df2[df2["cycle_month"] <= horizon].set_index(key).sort_index()
    pd.testing.assert_frame_equal(
        m1[feature_columns()], m2[feature_columns()], check_exact=False, rtol=0, atol=1e-12
    )


def test_current_frame_shape(session: Session) -> None:
    """The open cycle frame has one row per active lease and no target."""
    cycles = sorted({p.cycle_month for p in session.exec(select(Payment)).all()})
    open_cycle = cycles[-1]
    df, _ = build_current_frame(session, open_cycle)
    assert len(df) > 100
    assert "is_late" not in df.columns
    assert (df["cycle_month"] == pd.Timestamp(open_cycle)).all()
