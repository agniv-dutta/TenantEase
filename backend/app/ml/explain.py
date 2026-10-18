"""SHAP-based explanations rendered through plain-language templates."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
from sqlmodel import Session, select

from app.db import engine
from app.ml.features import build_current_frame, feature_metadata
from app.ml.train import ARTIFACTS
from app.models import Payment

METHOD_TEMPLATES = {
    -1.0: "No settled payment yet",
    0.0: "Last settled payment method was UPI",
    1.0: "Last settled payment method was cash",
    2.0: "Last settled payment method was bank transfer",
}


def load_model() -> dict:
    """Load the trained model bundle."""
    return joblib.load(ARTIFACTS / "model.joblib")


def _template_value(feature: str, value: float) -> str:
    """Human display value for a feature (templates use {value})."""
    if feature == "last_payment_method":
        return METHOD_TEMPLATES.get(float(value), str(value))
    return value


def render_factor(feature: str, value: float, direction: str, shap_value: float) -> dict[str, Any]:
    """Render one factor through its plain-language template."""
    meta = {m["name"]: m for m in feature_metadata()}
    entry = meta.get(feature)
    template = entry["plain_language_template"] if entry else feature
    display = _template_value(feature, value)
    try:
        sentence = template.format(value=display)
    except (KeyError, ValueError):
        sentence = f"{feature}: {display}"
    return {
        "feature": feature,
        "template_value": str(display),
        "direction": "raises" if shap_value > 0 else "lowers",
        "contribution": round(float(shap_value), 5),
        "sentence": sentence,
    }


def explain_frame(bundle: dict, frame: pd.DataFrame, top_n: int = 3) -> dict[int, list[dict]]:
    """Explain every row of a scoring frame; returns lease_id -> top factors."""
    features = bundle["features"]
    x = frame[features]
    explainer = shap.TreeExplainer(bundle["lgbm"])
    values = explainer.shap_values(x)
    if isinstance(values, list):
        values = values[1] if len(values) > 1 else values[0]
    out: dict[int, list[dict]] = {}
    for i, (_, row) in enumerate(frame.iterrows()):
        contributions = values[i]
        order = np.argsort(-np.abs(contributions))[:top_n]
        lease_id = int(row["lease_id"])
        out[lease_id] = [
            render_factor(
                features[j],
                float(row[features[j]]),
                "raises" if contributions[j] > 0 else "lowers",
                float(contributions[j]),
            )
            for j in order
        ]
    return out


def explain_lease(bundle: dict, frame: pd.DataFrame, lease_id: int, top_n: int = 3) -> list[dict]:
    """Explain a single lease from a scoring frame."""
    sub = frame[frame["lease_id"] == lease_id]
    if sub.empty:
        return []
    return explain_frame(bundle, sub, top_n=top_n).get(lease_id, [])


def build_shap_artifact(cycle_month: date | None = None) -> Path:
    """Write shap_top_features.json for the scored cycle."""
    bundle = load_model()
    with Session(engine) as session:
        if cycle_month is None:
            cycles = sorted({p.cycle_month for p in session.exec(select(Payment)).all()})
            cycle_month = cycles[-1]
        frame, _ = build_current_frame(session, cycle_month)
    if frame.empty:
        result: dict[str, Any] = {"cycle_month": str(cycle_month), "leases": {}}
    else:
        explained = explain_frame(bundle, frame)
        result = {
            "cycle_month": str(cycle_month),
            "leases": {str(k): v for k, v in explained.items()},
        }
    out = ARTIFACTS / "shap_top_features.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out
