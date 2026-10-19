"""Model training: rule baseline, logistic regression, LightGBM + calibration.

Time-based split only: train on the first 16 closed cycles, validate on cycles
17-20, test on 21-24. The open (current) cycle is excluded from training
because its outcome is unknown.

Artifacts written to ``app/ml/artifacts``:

* ``model.joblib`` — dict with the LightGBM model, isotonic calibrator,
  logistic pipeline, feature list and the operating threshold.
* ``test_predictions.joblib`` — per-row test predictions for evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, early_stopping
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlmodel import Session

from app import clock
from app.db import engine
from app.ml.features import build_training_frame, feature_columns

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
SEED = 42
N_TRAIN_CYCLES = 16
N_VAL_CYCLES = 4
N_TEST_CYCLES = 4


def _expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Equal-count-bin expected calibration error."""
    order = np.argsort(p)
    chunks = np.array_split(order, bins)
    ece = 0.0
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        ece += len(chunk) / len(y) * abs(float(p[chunk].mean()) - float(y[chunk].mean()))
    return float(ece)


def _select_calibration(y_val: pd.Series, val_scores: dict[str, np.ndarray]) -> tuple[str, dict[str, dict[str, float]]]:
    """Pick the shipped calibration using validation Brier then ECE."""
    y = y_val.to_numpy().astype(int)
    summary = {
        name: {
            "pr_auc": round(float(average_precision_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4),
            "ece": round(float(_expected_calibration_error(y, p)), 4),
        }
        for name, p in val_scores.items()
    }
    shipped = min(
        summary,
        key=lambda name: (
            summary[name]["brier"],
            summary[name]["ece"],
            -summary[name]["pr_auc"],
            name,
        ),
    )
    return shipped, summary


def load_training_dataframe() -> pd.DataFrame:
    """Build the full training frame and split it by time."""
    with Session(engine) as session:
        df, _ = build_training_frame(session)
    if df.empty:
        raise FileNotFoundError("No data found. Run `make seed` first.")
    # Drop the open cycle: its outcome is unknown (no paid_date yet).
    cycles = sorted(df["cycle_month"].unique())
    if pd.Timestamp(cycles[-1]) != pd.Timestamp(clock.open_cycle()):
        raise FileNotFoundError(
            f"The newest cycle {pd.Timestamp(cycles[-1]).date()} is not the open cycle "
            f"{clock.open_cycle().isoformat()}; run `make seed`."
        )
    closed = cycles[:-1]
    df = df[df["cycle_month"].isin(closed)].copy()
    df = df.sort_values(["cycle_month", "lease_id"]).reset_index(drop=True)

    val_cycles = set(closed[N_TRAIN_CYCLES : N_TRAIN_CYCLES + N_VAL_CYCLES])
    test_cycles = set(closed[-N_TEST_CYCLES:])
    df["split"] = "train"
    df.loc[df["cycle_month"].isin(val_cycles), "split"] = "val"
    df.loc[df["cycle_month"].isin(test_cycles), "split"] = "test"
    return df


def rule_baseline_scores(df: pd.DataFrame) -> np.ndarray:
    """B0: score 1 when the previous observed cycle was late, else 0."""
    scores = pd.Series(0.0, index=df.index)
    for _, sub in df.groupby("lease_id"):
        sub = sub.sort_values("cycle_month")
        scores.loc[sub.index] = sub["is_late"].astype(float).shift(1).fillna(0.0)
    return scores.to_numpy()


def train_main_model(df: pd.DataFrame, features: list[str]) -> dict:
    """Train B1 (logistic) and M (LightGBM + isotonic on validation)."""
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    x_train, y_train = train[features], train["is_late"].astype(int)
    x_val, y_val = val[features], val["is_late"].astype(int)

    lr = Pipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, random_state=SEED))]
    )
    lr.fit(x_train, y_train)

    lgbm = LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.9,
        subsample_freq=1,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=SEED,
        verbose=-1,
    )
    lgbm.fit(
        x_train,
        y_train,
        eval_set=[(x_val, y_val)],
        eval_metric="aucpr",
        callbacks=[early_stopping(50, verbose=False)],
    )

    # Calibrators fitted on validation-set raw scores.
    val_proba = lgbm.predict_proba(x_val)[:, 1]
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(val_proba, y_val.to_numpy())
    sigmoid = LogisticRegression(max_iter=2000, random_state=SEED)
    sigmoid.fit(val_proba.reshape(-1, 1), y_val.to_numpy())
    val_iso = iso.predict(val_proba)
    val_sigmoid = sigmoid.predict_proba(val_proba.reshape(-1, 1))[:, 1]
    val_smoothed = 0.5 * (val_iso + val_sigmoid)
    shipped_calibrator, calibration_validation = _select_calibration(
        y_val,
        {
            "isotonic": val_iso,
            "sigmoid": val_sigmoid,
            "smoothed_isotonic_sigmoid": val_smoothed,
        },
    )

    # Operating threshold: maximize Youden's J on shipped calibrated scores.
    from sklearn.metrics import roc_curve

    val_cal = {
        "isotonic": val_iso,
        "sigmoid": val_sigmoid,
        "smoothed_isotonic_sigmoid": val_smoothed,
    }[shipped_calibrator]
    if len(np.unique(y_val)) < 2:
        threshold = 0.5
    else:
        fpr, tpr, thresholds = roc_curve(y_val.to_numpy(), val_cal)
        threshold = float(thresholds[int(np.argmax(tpr - fpr))])

    return {
        "logistic": lr,
        "lgbm": lgbm,
        "isotonic": iso,
        "sigmoid": sigmoid,
        "shipped_calibrator": shipped_calibrator,
        "calibration_validation": calibration_validation,
        "features": features,
        "threshold": threshold,
        "best_iteration": int(getattr(lgbm, "best_iteration_", 0) or 0),
    }


def predict_test(model_bundle: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Produce test-set predictions for all three models.

    B0 is computed over the full frame so the first test cycle can see the
    previous (validation) cycle's outcome.
    """
    test_mask = df["split"] == "test"
    test = df.loc[test_mask].copy()
    features = model_bundle["features"]
    x_test = test[features]
    b0_full = rule_baseline_scores(df)
    test["b0"] = b0_full[test_mask.to_numpy()]
    test["b1"] = model_bundle["logistic"].predict_proba(x_test)[:, 1]
    raw = model_bundle["lgbm"].predict_proba(x_test)[:, 1]
    test["m_raw"] = raw
    test["m_isotonic"] = model_bundle["isotonic"].predict(raw)
    test["m_sigmoid"] = model_bundle["sigmoid"].predict_proba(raw.reshape(-1, 1))[:, 1]
    test["m_smoothed"] = 0.5 * (test["m_isotonic"] + test["m_sigmoid"])
    test["m"] = test[
        {
            "isotonic": "m_isotonic",
            "sigmoid": "m_sigmoid",
            "smoothed_isotonic_sigmoid": "m_smoothed",
        }[model_bundle["shipped_calibrator"]]
    ]
    return test[
        [
            "lease_id",
            "cycle_month",
            "split",
            "is_late",
            "b0",
            "b1",
            "m_raw",
            "m_isotonic",
            "m_sigmoid",
            "m_smoothed",
            "m",
            "prev_cycle_outstanding_days",
        ]
    ]


def main() -> None:
    """CLI entrypoint: train all models and persist artifacts."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    df = load_training_dataframe()
    features = feature_columns(use_occupation=True)
    bundle = train_main_model(df, features)
    test_preds = predict_test(bundle, df)

    # Sanity: model should beat the rule baseline on test PR-AUC.
    pr_m = average_precision_score(test_preds["is_late"], test_preds["m"])
    pr_b0 = average_precision_score(test_preds["is_late"], test_preds["b0"])
    joblib.dump(
        {
            "lgbm": bundle["lgbm"],
            "isotonic": bundle["isotonic"],
            "sigmoid": bundle["sigmoid"],
            "logistic": bundle["logistic"],
            "shipped_calibrator": bundle["shipped_calibrator"],
            "calibration_validation": bundle["calibration_validation"],
            "features": features,
            "threshold": bundle["threshold"],
            "best_iteration": bundle["best_iteration"],
            "trained_on": {"n_rows": int(len(df)), "seed": SEED},
        },
        ARTIFACTS / "model.joblib",
    )
    joblib.dump(test_preds, ARTIFACTS / "test_predictions.joblib")
    summary = {
        "n_rows": int(len(df)),
        "n_test": int(len(test_preds)),
        "test_base_rate": float(test_preds["is_late"].mean()),
        "pr_auc_m": float(pr_m),
        "pr_auc_b0": float(pr_b0),
        "threshold": bundle["threshold"],
        "best_iteration": bundle["best_iteration"],
        "shipped_calibrator": bundle["shipped_calibrator"],
        "beats_baseline": bool(pr_m > pr_b0),
    }
    (ARTIFACTS / "train_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
