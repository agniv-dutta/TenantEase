"""Evaluation on the held-out test set.

Writes ``metrics.json``, ``slices.json`` and ``docs/model_card.md`` under the
artifacts/docs directories, then runs the explanation and simulation modules
so every artifact is regenerated together. All numbers come from the
predictions produced by ``app.ml.train`` — nothing is hand-typed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from app.ml.train import ARTIFACTS, SEED, load_training_dataframe, train_main_model

DOCS = Path(__file__).resolve().parents[3] / "docs"
TOP_K_PERCENTS = [5, 10, 15, 20]
N_BOOT = 1000
ECE_BINS = 10
GAP_FLAG_PP = 10.0


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = ECE_BINS) -> tuple[float, list]:
    """Equal-count-bin ECE plus the calibration curve points."""
    order = np.argsort(p)
    chunks = np.array_split(order, bins)
    ece = 0.0
    curve: list[dict] = []
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        mean_p = float(p[chunk].mean())
        frac_pos = float(y[chunk].mean())
        ece += len(chunk) / len(y) * abs(mean_p - frac_pos)
        curve.append({"mean_predicted": round(mean_p, 4), "fraction_positive": round(frac_pos, 4), "n": int(len(chunk))})
    return float(ece), curve


def top_k_metrics(y: np.ndarray, p: np.ndarray, cycle: pd.Series) -> dict[str, dict]:
    """Precision/recall at the top K percent of leases per cycle."""
    out: dict[str, dict] = {}
    frame = pd.DataFrame({"y": y, "p": p, "cycle": cycle.to_numpy()})
    for pct in TOP_K_PERCENTS:
        precs, recalls = [], []
        for _, sub in frame.groupby("cycle"):
            k = max(1, int(round(pct / 100 * len(sub))))
            top = sub.nlargest(k, "p")
            precs.append(float(top["y"].mean()))
            recalls.append(float(top["y"].sum() / max(1, sub["y"].sum())))
        out[str(pct)] = {
            "precision": round(float(np.mean(precs)), 4),
            "recall": round(float(np.mean(recalls)), 4),
        }
    return out


def bootstrap_ci(y: np.ndarray, p: np.ndarray, lease_ids: np.ndarray, metric_fn, n_boot: int = N_BOOT) -> list[float]:
    """Percentile 95% CI for a metric, resampling whole leases."""
    rng = np.random.default_rng(SEED)
    unique = np.unique(lease_ids)
    stats: list[float] = []
    for _ in range(n_boot):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        idx = np.concatenate([np.flatnonzero(lease_ids == lid) for lid in chosen])
        if len(np.unique(y[idx])) < 2:
            continue
        stats.append(float(metric_fn(y[idx], p[idx])))
    if not stats:
        return [float("nan"), float("nan")]
    return [round(float(np.percentile(stats, 2.5)), 4), round(float(np.percentile(stats, 97.5)), 4)]


def model_metrics(y: np.ndarray, p: np.ndarray, lease_ids: np.ndarray, cycles: pd.Series) -> dict[str, Any]:
    """All headline metrics for one model on the test set."""
    ece, curve = expected_calibration_error(y, p)
    return {
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "pr_auc_ci": bootstrap_ci(y, p, lease_ids, average_precision_score),
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "roc_auc_ci": bootstrap_ci(y, p, lease_ids, roc_auc_score),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "brier_ci": bootstrap_ci(y, p, lease_ids, brier_score_loss),
        "ece": round(ece, 4),
        "calibration_curve": curve,
        "top_k": top_k_metrics(y, p, cycles),
    }


def slice_metrics(preds: pd.DataFrame, score_col: str, threshold: float, group_col: str) -> dict[str, dict]:
    """Recall, FPR, base rate and n per slice value at the operating threshold."""
    out: dict[str, dict] = {}
    flags = (preds[score_col] >= threshold).astype(int)
    for value, sub in preds.groupby(group_col):
        y = sub["is_late"].to_numpy()
        f = flags.loc[sub.index]
        tp = int(((f == 1) & (y == 1)).sum())
        fn = int(((f == 0) & (y == 1)).sum())
        fp = int(((f == 1) & (y == 0)).sum())
        tn = int(((f == 0) & (y == 0)).sum())
        out[str(value)] = {
            "n": int(len(sub)),
            "late_rate": round(float(y.mean()), 4),
            "recall": round(tp / max(1, tp + fn), 4),
            "fpr": round(fp / max(1, fp + tn), 4),
        }
    return out


def gap_flags(slice_table: dict[str, dict]) -> list[dict]:
    """Flag any pairwise gap above 10 percentage points within a slice family."""
    flags: list[dict] = []
    for family, groups in slice_table.items():
        for metric in ("recall", "fpr"):
            vals = {k: v[metric] for k, v in groups.items()}
            keys = list(vals)
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    gap = abs(vals[keys[i]] - vals[keys[j]]) * 100
                    if gap > GAP_FLAG_PP:
                        flags.append(
                            {
                                "slice": family,
                                "metric": metric,
                                "a": keys[i],
                                "b": keys[j],
                                "gap_pp": round(gap, 1),
                            }
                        )
    return flags


def rent_band(row: pd.Series) -> str:
    """Simple rent bands for slicing."""
    r = float(row["rent_amount"]) if "rent_amount" in row else 0.0
    if r < 10_000:
        return "under_10k"
    if r < 20_000:
        return "10k_to_20k"
    return "20k_plus"


def build_slices(preds: pd.DataFrame, threshold: float, full_test: pd.DataFrame) -> dict[str, Any]:
    """Slice table + gap flags. Language is audited, never a feature."""
    merged = preds.merge(
        full_test[["lease_id", "cycle_month", "occupation_type", "preferred_language", "rent_amount", "is_cold_start", "prior_cycles"]],
        on=["lease_id", "cycle_month"],
        how="left",
        suffixes=("", "_f"),
    )
    merged["rent_band"] = merged.apply(rent_band, axis=1)
    merged["tenure_group"] = np.where(merged["is_cold_start"] == 1.0, "cold_start", "established")
    table = {
        "occupation_type": slice_metrics(merged, "m", threshold, "occupation_type"),
        "tenure_group": slice_metrics(merged, "m", threshold, "tenure_group"),
        "rent_band": slice_metrics(merged, "m", threshold, "rent_band"),
        "preferred_language_audit_only": slice_metrics(merged, "m", threshold, "preferred_language"),
    }
    return {"slices": table, "gap_flags": gap_flags(table), "threshold": threshold}


def ablation_use_occupation(df: pd.DataFrame) -> dict[str, Any]:
    """Retrain M with occupation removed and report the PR-AUC change."""
    from sklearn.metrics import average_precision_score

    from app.ml.features import feature_columns

    feats_no_occ = feature_columns(use_occupation=False)
    bundle = train_main_model(df, feats_no_occ)
    test = df[df["split"] == "test"]
    raw = bundle["lgbm"].predict_proba(test[feats_no_occ])[:, 1]
    p = bundle["isotonic"].predict(raw)
    return {
        "pr_auc": round(float(average_precision_score(test["is_late"], p)), 4),
        "roc_auc": round(float(roc_auc_score(test["is_late"], p)), 4),
        "features_used": feats_no_occ,
    }


def main() -> None:
    """CLI entrypoint: evaluate all models and write artifacts."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    bundle = joblib.load(ARTIFACTS / "model.joblib")
    preds: pd.DataFrame = joblib.load(ARTIFACTS / "test_predictions.joblib")
    threshold = float(bundle["threshold"])

    y = preds["is_late"].to_numpy().astype(int)
    lease_ids = preds["lease_id"].to_numpy()
    metrics: dict[str, Any] = {
        "synthetic_data": True,
        "note": "All numbers come from synthetic data with planted effects. Not a forecast of production accuracy.",
        "n_test_rows": int(len(preds)),
        "test_base_rate": round(float(y.mean()), 4),
        "operating_threshold": round(threshold, 4),
        "models": {
            "B0_rule_baseline": model_metrics(y, preds["b0"].to_numpy(), lease_ids, preds["cycle_month"]),
            "B1_logistic": model_metrics(y, preds["b1"].to_numpy(), lease_ids, preds["cycle_month"]),
            "M_lgbm_raw": model_metrics(y, preds["m_raw"].to_numpy(), lease_ids, preds["cycle_month"]),
            "M_lgbm_isotonic": model_metrics(y, preds["m"].to_numpy(), lease_ids, preds["cycle_month"]),
        },
        "calibration_note": (
            "Isotonic calibration maps many distinct raw scores onto a few "
            "probability levels. That improves probability quality (Brier, ECE) "
            "but creates ties that reduce ranking metrics such as PR-AUC. The "
            "uncalibrated M is reported alongside the calibrated M for honesty."
        ),
    }

    full = load_training_dataframe()
    full_test = full[full["split"] == "test"].copy()
    slices = build_slices(preds, threshold, full_test)
    metrics["ablation_no_occupation"] = ablation_use_occupation(full)

    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (ARTIFACTS / "slices.json").write_text(json.dumps(slices, indent=2), encoding="utf-8")

    from app.ml.explain import build_shap_artifact
    from app.ml.simulate import build_simulation

    build_shap_artifact()
    simulation = build_simulation()
    metrics["simulation"] = simulation
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    card = render_model_card(metrics, slices)
    (DOCS / "model_card.md").write_text(card, encoding="utf-8")
    (ARTIFACTS / "model_card.md").write_text(card, encoding="utf-8")
    print(f"Wrote metrics, slices, shap, simulation and model card. Test PR-AUC M={metrics['models']['M_lgbm_isotonic']['pr_auc']}")


def render_model_card(metrics: dict, slices: dict) -> str:
    """Render the model card markdown from computed artifacts."""
    m = metrics["models"]["M_lgbm_isotonic"]
    m_raw = metrics["models"]["M_lgbm_raw"]
    b0 = metrics["models"]["B0_rule_baseline"]
    b1 = metrics["models"]["B1_logistic"]
    abl = metrics["ablation_no_occupation"]
    lines = [
        "# Model card: TenantEase Khata late-payment risk model",
        "",
        "> **This model is trained on fully synthetic data with planted effects.**",
        "> Metrics show the pipeline works under known conditions; they are not a",
        "> forecast of production accuracy.",
        "",
        "## Intended use",
        "",
        "Rank leases by the risk of paying rent more than 5 days late in the coming",
        "cycle so a property manager can schedule reminders earlier or personally",
        "follow up with a few tenants.",
        "",
        "## Out-of-scope use",
        "",
        "Never use this score for eviction, rent pricing, tenant screening, or any",
        "decision about a person. It only decides who gets an earlier or more",
        "personal nudge.",
        "",
        "## Data",
        "",
        f"Synthetic: 6 properties, ~140 units, 24 closed cycles, {metrics['n_test_rows']} test rows.",
        f"Test base rate of >5-days-late: {metrics['test_base_rate']:.1%}.",
        "Time split: train first 16 cycles, validate 17-20, test 21-24.",
        "Excluded from features: name, phone, property, locality, preferred language,",
        "preferred channel. Occupation type is included behind a config flag and ablated below.",
        "",
        "## Metrics (test set only)",
        "",
        "| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Brier | ECE |",
        "|---|---|---|---|---|",
        f"| B0 rule baseline | {b0['pr_auc']:.3f} {fmt_ci(b0['pr_auc_ci'])} | {b0['roc_auc']:.3f} | {b0['brier']:.3f} | {b0['ece']:.3f} |",
        f"| B1 logistic | {b1['pr_auc']:.3f} {fmt_ci(b1['pr_auc_ci'])} | {b1['roc_auc']:.3f} | {b1['brier']:.3f} | {b1['ece']:.3f} |",
        f"| M LightGBM (raw) | {m_raw['pr_auc']:.3f} {fmt_ci(m_raw['pr_auc_ci'])} | {m_raw['roc_auc']:.3f} | {m_raw['brier']:.3f} | {m_raw['ece']:.3f} |",
        f"| M LightGBM + isotonic | {m['pr_auc']:.3f} {fmt_ci(m['pr_auc_ci'])} | {m['roc_auc']:.3f} | {m['brier']:.3f} | {m['ece']:.3f} |",
        "",
        metrics["calibration_note"],
        "",
        "Operating threshold (Youden's J on validation): "
        f"{metrics['operating_threshold']:.3f}.",
        "",
        "### Follow-up capacity (top K% of leases per cycle)",
        "",
        "| K | Precision | Recall |",
        "|---|---|---|",
    ]
    for k, v in m["top_k"].items():
        lines.append(f"| top {k}% | {v['precision']:.1%} | {v['recall']:.1%} |")
    lines += [
        "",
        "## Slices and fairness audit",
        "",
        f"Ablation without occupation type: PR-AUC {abl['pr_auc']:.3f} "
        f"(with occupation {m['pr_auc']:.3f}).",
        "",
        "Gap flags (any pairwise gap above 10 percentage points at the operating threshold):",
    ]
    flags = slices.get("gap_flags", [])
    if flags:
        for f in flags:
            lines.append(
                f"- {f['slice']}: {f['metric']} gap of {f['gap_pp']:.1f} points between "
                f"{f['a']} and {f['b']}"
            )
    else:
        lines.append("- none")
    lines += [
        "",
        "## Limitations",
        "",
        "- Synthetic data with planted effects; real accuracy is unknown.",
        "- The nudge-effect simulation is assumption-based, not measured. Proving",
        "  that nudges change behaviour needs a real A/B test.",
        "- Occupation type and locality can act as proxies for protected characteristics",
        "  in India; locality and language are excluded, occupation is ablated and audited.",
        "- Reminders are only drafted and approved in the prototype, never sent.",
        "",
    ]
    return "\n".join(lines)


def fmt_ci(ci: list[float]) -> str:
    """Format a 95% CI as text."""
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


if __name__ == "__main__":
    main()
