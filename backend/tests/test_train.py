"""Tests for model training utilities."""

from __future__ import annotations

import pandas as pd

from app.ml.train import load_training_dataframe, rule_baseline_scores


def test_split_is_time_based_and_disjoint() -> None:
    """Cycles fall into exactly one split; the open cycle is excluded."""
    df = load_training_dataframe()
    assert set(df["split"]) == {"train", "val", "test"}
    cycles_by_split = {s: sorted(g["cycle_month"].unique()) for s, g in df.groupby("split")}
    assert max(cycles_by_split["train"]) < min(cycles_by_split["val"])
    assert max(cycles_by_split["val"]) < min(cycles_by_split["test"])
    assert len(cycles_by_split["train"]) == 16
    assert len(cycles_by_split["val"]) == 4
    assert len(cycles_by_split["test"]) == 4
    # No open cycle (target would be fabricated).
    assert df["is_late"].notna().all()


def test_rule_baseline_uses_previous_cycle() -> None:
    """B0 scores 1 exactly when the previous cycle was late."""
    df = pd.DataFrame(
        {
            "lease_id": [1, 1, 1, 2, 2],
            "cycle_month": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-01-01", "2026-02-01"]),
            "is_late": [1, 0, 1, 0, 1],
        }
    )
    scores = rule_baseline_scores(df)
    assert list(scores) == [0.0, 1.0, 0.0, 0.0, 0.0]


def test_scores_are_seeded() -> None:
    """Two loads of the same database produce identical frames."""
    a = load_training_dataframe()
    b = load_training_dataframe()
    pd.testing.assert_frame_equal(a, b)


def test_features_have_no_excluded_columns() -> None:
    """The frame never carries raw PII columns."""
    df = load_training_dataframe()
    for col in ("name", "phone", "locality", "preferred_channel"):
        assert col not in df.columns
    assert "preferred_language" in df.columns  # audit-only column, not a feature
