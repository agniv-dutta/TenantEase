"""Score the open cycle and persist results to the risk_scores table."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

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
    """The open cycle is the latest cycle_month present in payments."""
    cycles = sorted({p.cycle_month for p in session.exec(select(Payment)).all()})
    if not cycles:
        raise FileNotFoundError("No payments found. Run `make seed` first.")
    return cycles[-1]


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
    iso = bundle["isotonic"].predict(raw)
    sigmoid = bundle["sigmoid"].predict_proba(raw.reshape(-1, 1))[:, 1]
    smoothed = 0.5 * (iso + sigmoid)
    calibrated = {
        "isotonic": iso,
        "sigmoid": sigmoid,
        "smoothed_isotonic_sigmoid": smoothed,
    }[bundle.get("shipped_calibrator", "isotonic")]
    explained = explain_frame(bundle, frame)

    existing = session.exec(
        select(RiskScore).where(RiskScore.cycle_month == cycle_month)
    ).all()
    for row in existing:
        session.delete(row)

    for (_, frow), raw_score, prob in zip(frame.iterrows(), raw, calibrated):
        lease_id = int(frow["lease_id"])
        factors = explained.get(lease_id, [])
        session.add(
            RiskScore(
                lease_id=lease_id,
                cycle_month=cycle_month,
                raw_score=float(raw_score),
                probability=float(prob),
                tier=tier_for(float(prob)),
                prev_cycle_outstanding_days=float(frow.get("prev_cycle_outstanding_days", 0.0)),
                top_factors_json=json.dumps(factors),
            )
        )
    session.commit()
    return len(frame)
