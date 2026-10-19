"""Score the open cycle and persist results to the risk_scores table."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app import clock
from app.config import settings
from app.ml.explain import explain_frame, load_model
from app.ml.features import build_current_frame
from app.models import Payment, RiskScore


def tier_for(probability: float) -> str:
    """Map a calibrated probability to a risk tier using config thresholds."""
    if probability < settings.tier_low_max:
        return "low"
    if probability <= settings.tier_medium_max:
        return "medium"
    return "high"


def current_cycle(session: Session) -> date:
    """The open cycle: the month containing ``DEMO_TODAY``.

    The ledger shows this cycle plus the six closed months before it, so the
    seed must contain all of them. If a month is missing the data is stale and
    the fix belongs in ``make seed``, never in this query.
    """
    required = clock.recent_cycles()
    present = set(
        session.exec(select(Payment.cycle_month).where(Payment.cycle_month.in_(required))).all()
    )
    missing = [cycle for cycle in required if cycle not in present]
    if missing:
        months = ", ".join(c.month_name() + " " + str(c.year) for c in reversed(missing))
        raise FileNotFoundError(
            f"The data has no payments for {months}; it does not cover the open "
            f"cycle {required[0].isoformat()}. Reseed the database with `make seed`."
        )
    return required[0]


def score_open_cycle(session: Session, cycle_month: date | None = None) -> int:
    """Score every active lease for the open cycle and store the results."""
    import json

    if cycle_month is None:
        cycle_month = current_cycle(session)
    bundle = load_model()
    frame, _ = build_current_frame(session, cycle_month)
    if frame.empty:
        return 0
    raw = bundle["lgbm"].predict_proba(frame[bundle["features"]])[:, 1]
    calibrated = bundle["isotonic"].predict(raw)
    explained = explain_frame(bundle, frame)

    existing = session.exec(
        select(RiskScore).where(RiskScore.cycle_month == cycle_month)
    ).all()
    for row in existing:
        session.delete(row)

    for (_, frow), prob in zip(frame.iterrows(), calibrated):
        lease_id = int(frow["lease_id"])
        factors = explained.get(lease_id, [])
        session.add(
            RiskScore(
                lease_id=lease_id,
                cycle_month=cycle_month,
                probability=float(prob),
                tier=tier_for(float(prob)),
                top_factors_json=json.dumps(factors),
            )
        )
    session.commit()
    return len(frame)
