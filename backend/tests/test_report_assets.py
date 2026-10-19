"""Tests for the report asset generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ml import report_assets
from app.ml.train import ARTIFACTS


def _have_artifacts() -> bool:
    return (ARTIFACTS / "metrics.json").exists() and (ARTIFACTS / "simulation.json").exists()


def test_shap_importance_ranks_by_mean_abs():
    shap = {
        "leases": {
            "1": [
                {"feature": "a", "contribution": 0.2},
                {"feature": "b", "contribution": -0.9},
            ],
            "2": [
                {"feature": "a", "contribution": 0.4},
                {"feature": "c", "contribution": 0.1},
            ],
        }
    }
    ranked = report_assets._shap_importance(shap)
    assert [f for f, _ in ranked][:2] == ["b", "a"]  # b mean 0.9, a mean 0.3
    assert ranked[0][1] == pytest.approx(0.9)


def test_render_eval_report_has_sections(tmp_path: Path):
    metrics = {
        "note": "synthetic",
        "n_test_rows": 10,
        "test_base_rate": 0.2,
        "operating_threshold": 0.2,
        "calibration_note": "note",
        "ablation_no_occupation": {"pr_auc": 0.1, "roc_auc": 0.6},
        "shipped_model_key": "M_lgbm_shipped",
        "calibration_choice": {"name": "smoothed_isotonic_sigmoid", "reason": "lowest brier"},
        "models": {
            k: {
                "pr_auc": 0.3,
                "roc_auc": 0.7,
                "brier": 0.2,
                "ece": 0.1,
                "top_k": {"5": {"precision": 0.5, "recall": 0.2}},
                "calibration_curve": [{"mean_predicted": 0.1, "fraction_positive": 0.1, "n": 2}],
            }
            for k in (
                "B0_rule_baseline",
                "B1_logistic",
                "M_lgbm_raw",
                "M_lgbm_isotonic",
                "M_lgbm_sigmoid",
                "M_lgbm_smoothed",
                "M_lgbm_shipped",
            )
        },
    }
    slices = {
        "slices": {"occupation_type": {"gig": {"n": 5, "late_rate": 0.3, "recall": 0.6, "fpr": 0.4}}},
        "gap_flags": [{"slice": "occupation_type", "metric": "fpr", "a": "gig", "b": "student", "gap_pp": 12.0}],
        "threshold": 0.2,
    }
    simulation = {
        "label": "assumption-based, not measured",
        "caveat": "not measured",
        "effect_sweep": [0.1],
        "rows": [
            {
                "follow_up_per_cycle": 5,
                "expected_late_avoided_model": {"0.10": 1.0},
                "expected_late_avoided_rule_baseline": {"0.10": 2.0},
                "actual_lates_in_model_top_n": 3,
                "actual_lates_in_baseline_top_n": 3,
            }
        ],
    }
    llm_eval = {
        "n_drafts": 90,
        "provider": "none",
        "fallback_rate": 0.0,
        "guardrails": {"length": {"pass_rate": 1.0, "passed": 90, "failed": 0}},
    }
    text = report_assets.render_eval_report(
        {"metrics": metrics, "slices": slices, "simulation": simulation, "shap": None, "llm_eval": llm_eval, "preds": None}
    )
    assert "# Evaluation report" in text
    assert "Model comparison" in text
    assert "Limitations and failure modes" in text
    assert "0.500" in text  # precision pulled from metrics, not typed by hand


@pytest.mark.skipif(not _have_artifacts(), reason="model artifacts not built")
def test_main_writes_figures_and_report(tmp_path: Path):
    figures = tmp_path / "figures"
    report = tmp_path / "eval_report.md"
    written = report_assets.main(figures_dir=figures, report_path=report)
    pngs = sorted(figures.glob("*.png"))
    assert len(pngs) >= 7
    assert report.exists()
    body = report.read_text(encoding="utf-8")
    assert "Evaluation report" in body
    # every referenced metric comes from the artifact files
    metrics = json.loads((ARTIFACTS / "metrics.json").read_text(encoding="utf-8"))
    assert f"{metrics['models']['M_lgbm_shipped']['pr_auc']:.3f}" in body
    assert any(p == report for p in written)
