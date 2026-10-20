"""Tests for evaluation helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.evaluate import (
    expected_calibration_error,
    gap_flags,
    model_metrics,
    paired_bootstrap_comparison,
    top_k_metrics,
)


def test_ece_perfect_predictions() -> None:
    """Perfectly calibrated predictions have ECE near zero."""
    y = np.array([0, 0, 1, 1] * 50)
    p = y.astype(float)
    ece, curve = expected_calibration_error(y, p, bins=4)
    assert ece < 0.02
    assert len(curve) == 4


def test_top_k_per_cycle() -> None:
    """Top-k metrics rank within each cycle and average across cycles."""
    y = np.array([1, 0, 0, 0, 1, 0, 0, 0])
    p = np.array([0.9, 0.8, 0.1, 0.2, 0.7, 0.6, 0.3, 0.4])
    cycles = pd.Series(["c1"] * 4 + ["c2"] * 4)
    out = top_k_metrics(y, p, cycles)
    assert out["20"]["precision"] == 1.0  # top-1 of each cycle is late
    assert out["20"]["recall"] == 1.0  # each cycle has one late, and it is picked


def test_gap_flags_detects_large_gap() -> None:
    """A pairwise gap above 10 points is flagged; smaller gaps are not."""
    table = {
        "lang": {
            "en": {"n": 10, "late_rate": 0.2, "recall": 0.8, "fpr": 0.1},
            "hi": {"n": 10, "late_rate": 0.2, "recall": 0.6, "fpr": 0.1},
            "hinglish": {"n": 10, "late_rate": 0.2, "recall": 0.75, "fpr": 0.1},
        }
    }
    flags = gap_flags(table)
    assert any(f["metric"] == "recall" and f["gap_pp"] == 20.0 for f in flags)


def test_model_metrics_keys() -> None:
    """model_metrics returns every headline metric and CIs."""
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 200)
    p = rng.random(200)
    leases = rng.integers(0, 20, 200)
    cycles = pd.Series(rng.integers(0, 4, 200))
    out = model_metrics(y, p, leases, cycles)
    for key in ("pr_auc", "pr_auc_ci", "roc_auc", "roc_auc_ci", "brier", "brier_ci", "ece", "calibration_curve", "top_k"):
        assert key in out
    assert len(out["pr_auc_ci"]) == 2


def test_paired_bootstrap_comparison_returns_point_and_interval() -> None:
    """Paired lease bootstrap reports finite estimates and 95% intervals."""
    y = np.array([0, 1, 0, 1, 1, 0, 1, 0])
    p_a = np.array([0.1, 0.8, 0.2, 0.7, 0.9, 0.3, 0.6, 0.4])
    p_b = np.array([0.2, 0.7, 0.3, 0.6, 0.8, 0.4, 0.5, 0.5])
    leases = np.repeat(np.arange(4), 2)
    result = paired_bootstrap_comparison(y, p_a, p_b, leases, n_boot=100)
    assert set(result) == {"pr_auc", "roc_auc", "brier"}
    for values in result.values():
        assert set(values) == {"estimate", "ci95"}
        assert len(values["ci95"]) == 2
        assert values["ci95"][0] <= values["ci95"][1]
