"""Assumption-based simulation of follow-up impact.

Every output is labelled **assumption-based, not measured**. The prototype has
no A/B test; these numbers sweep an assumed relative reduction in late
probability for leases the manager personally follows up with.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.ml.train import ARTIFACTS

EFFECT_SWEEP = [0.05, 0.10, 0.15, 0.25]
FOLLOW_UP_SIZES = [5, 10, 15, 20, 30]
LABEL = "assumption-based, not measured"


def build_simulation(preds: pd.DataFrame | None = None) -> dict[str, Any]:
    """Sensitivity table: late payments avoided across size x effect.

    Compares the calibrated model's top-N picks against the rule baseline's
    top-N picks for the same assumed effect.
    """
    if preds is None:
        preds = joblib.load(ARTIFACTS / "test_predictions.joblib")
    rows: list[dict[str, Any]] = []
    for n in FOLLOW_UP_SIZES:
        model_avoided_by_effect: dict[str, float] = {}
        baseline_avoided_by_effect: dict[str, float] = {}
        model_picked_probs: list[float] = []
        baseline_picked_probs: list[float] = []
        actual_late_model = 0
        actual_late_baseline = 0
        for _, sub in preds.groupby("cycle_month"):
            ranked = sub.sort_values(
                by=["m_raw", "prev_cycle_outstanding_days", "lease_id"],
                ascending=[False, False, True],
            )
            top_m = ranked.head(n)
            top_b = sub.nlargest(n, "b0")  # ties broken by lease id order
            model_picked_probs.extend(top_m["m"].tolist())
            baseline_picked_probs.extend(top_b["b0"].tolist())
            actual_late_model += int(top_m["is_late"].sum())
            actual_late_baseline += int(top_b["is_late"].sum())
        sum_p_model = sum(model_picked_probs)
        sum_p_base = sum(baseline_picked_probs)
        for eff in EFFECT_SWEEP:
            model_avoided_by_effect[f"{eff:.2f}"] = round(eff * sum_p_model, 2)
            baseline_avoided_by_effect[f"{eff:.2f}"] = round(eff * sum_p_base, 2)
        rows.append(
            {
                "follow_up_per_cycle": n,
                "label": LABEL,
                "expected_late_avoided_model": model_avoided_by_effect,
                "expected_late_avoided_rule_baseline": baseline_avoided_by_effect,
                "actual_lates_in_model_top_n": actual_late_model,
                "actual_lates_in_baseline_top_n": actual_late_baseline,
            }
        )
    return {
        "label": LABEL,
        "caveat": (
            "These are assumption-based projections with a swept nudge effect, "
            "not measured outcomes. Proving that nudges change behaviour needs "
            "a real A/B test."
        ),
        "effect_sweep": EFFECT_SWEEP,
        "rows": rows,
    }


def write_simulation() -> Path:
    """Write simulation.json and return its path."""
    sim = build_simulation()
    out = ARTIFACTS / "simulation.json"
    out.write_text(json.dumps(sim, indent=2), encoding="utf-8")
    return out


def main() -> None:
    """CLI entrypoint."""
    path = write_simulation()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
