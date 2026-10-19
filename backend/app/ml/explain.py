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
from sqlmodel import Session

from app import clock
from app.db import engine
from app.ml.features import build_current_frame, render_feature_sentence
from app.ml.train import ARTIFACTS


def load_model() -> dict:
    """Load the trained model bundle."""
    path = ARTIFACTS / "model.joblib"
    if not path.exists():
        raise FileNotFoundError("No trained model yet; run `make train` first.")
    return joblib.load(path)


def render_factor(feature: str, row: object, shap_value: float) -> dict[str, Any]:
    """Render one factor as a human sentence plus its SHAP direction.

    The row (not just one value) is passed so templates can combine features,
    for example rent change percent with the months since that change.
    """
    direction = "raises" if shap_value > 0 else "lowers"
    return {
        "feature": feature,
        "sentence": render_feature_sentence(feature, row, direction),
        "direction": direction,
        "contribution": round(float(shap_value), 5),
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
            render_factor(features[j], row, float(contributions[j]))
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
            cycle_month = clock.open_cycle()
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
