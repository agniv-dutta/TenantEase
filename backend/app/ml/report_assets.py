"""Report assets: figures for the reports and a generated eval report.

Everything here reads the artifacts produced by ``train``, ``evaluate``,
``simulate`` and ``llm.eval``. No number is hand-typed; the eval report is
assembled from ``metrics.json`` and friends at run time.

    python -m app.ml.report_assets

Writes PNGs into ``docs/figures`` and ``docs/eval_report.md``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.ml.train import ARTIFACTS  # noqa: E402

DOCS = Path(__file__).resolve().parents[3] / "docs"
FIGURES = DOCS / "figures"

# Khata palette, mirrored from frontend/src/styles/tokens.css
CHUNA = "#E8ECE5"
PAPER = "#F5F7F2"
RULE = "#B7C0D6"
INDIGO = "#1E2A5E"
INDIGO_SOFT = "#4B5788"
STAMP_RED = "#B3202A"
VERDIGRIS = "#2A7566"
HALDI = "#E2A200"


def _setup_style() -> str:
    """Apply the Khata styling to matplotlib and return the font family."""
    family = "DejaVu Sans"
    try:  # use Mukta when the machine has it, otherwise fall back cleanly
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        if "Mukta" in available:
            family = "Mukta"
    except Exception:  # pragma: no cover - font discovery is best effort
        pass
    plt.rcParams.update(
        {
            "font.family": family,
            "figure.facecolor": CHUNA,
            "axes.facecolor": CHUNA,
            "savefig.facecolor": CHUNA,
            "axes.edgecolor": INDIGO,
            "axes.labelcolor": INDIGO,
            "text.color": INDIGO,
            "xtick.color": INDIGO_SOFT,
            "ytick.color": INDIGO_SOFT,
            "axes.grid": False,
            "figure.dpi": 120,
        }
    )
    return family


def _clean(ax) -> None:
    """Drop the top and right spines and the grid for a quiet look."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(False)


def load_artifacts(artifacts_dir: Path = ARTIFACTS) -> dict[str, Any]:
    """Load every artifact the figures need, tolerating missing files."""
    import joblib

    def read_json(name: str) -> Any:
        path = artifacts_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    preds = None
    pred_path = artifacts_dir / "test_predictions.joblib"
    if pred_path.exists():
        preds = joblib.load(pred_path)
    return {
        "metrics": read_json("metrics.json"),
        "slices": read_json("slices.json"),
        "simulation": read_json("simulation.json"),
        "shap": read_json("shap_top_features.json"),
        "llm_eval": read_json("llm_eval.json"),
        "triage_eval": read_json("triage_eval.json"),
        "preds": preds,
    }


def _save(fig, figures_dir: Path, name: str) -> Path:
    figures_dir.mkdir(parents=True, exist_ok=True)
    out = figures_dir / name
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def fig_cumulative_late_rate(preds: pd.DataFrame, figures_dir: Path) -> Path:
    """1. Cumulative late rate per cycle."""
    rate = preds.groupby("cycle_month")["is_late"].mean().sort_index()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(rate.index, rate.values, marker="o", color=INDIGO, linewidth=2)
    ax.axhline(preds["is_late"].mean(), color=STAMP_RED, linestyle="--", linewidth=1)
    ax.text(
        rate.index[0],
        preds["is_late"].mean(),
        " overall base rate",
        color=STAMP_RED,
        fontsize=9,
        va="bottom",
    )
    ax.set_title("Late rate per cycle")
    ax.set_ylabel("Share more than 5 days late")
    ax.set_ylim(bottom=0)
    _clean(ax)
    return _save(fig, figures_dir, "01_cumulative_late_rate.png")


def fig_pr_curves(preds: pd.DataFrame, metrics: dict, figures_dir: Path) -> Path:
    """2. PR curves for B0, B1 and M on the test set."""
    from sklearn.metrics import precision_recall_curve

    test = preds[preds["split"] == "test"]
    fig, ax = plt.subplots(figsize=(6, 5))
    series = [
        ("B0 rule baseline", "b0", HALDI),
        ("B1 logistic", "b1", VERDIGRIS),
        ("M LightGBM", "m", INDIGO),
    ]
    for label, col, color in series:
        precision, recall, _ = precision_recall_curve(test["is_late"], test[col])
        pr_auc = metrics["models"][
            {"b0": "B0_rule_baseline", "b1": "B1_logistic", "m": "M_lgbm_isotonic"}[col]
        ]["pr_auc"]
        ax.plot(recall, precision, color=color, linewidth=2, label=f"{label} (PR-AUC {pr_auc:.3f})")
    ax.axhline(test["is_late"].mean(), color=RULE, linestyle="--", linewidth=1)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-recall on the test set")
    ax.legend(frameon=False, fontsize=9)
    _clean(ax)
    return _save(fig, figures_dir, "02_pr_curves.png")


def fig_calibration(metrics: dict, figures_dir: Path) -> Path:
    """3. Calibration before and after isotonic."""
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot([0, 1], [0, 1], color=RULE, linestyle="--", linewidth=1, label="Perfect")
    for key, color, label in [
        ("M_lgbm_raw", HALDI, "M raw"),
        ("M_lgbm_isotonic", INDIGO, "M isotonic"),
    ]:
        curve = metrics["models"][key]["calibration_curve"]
        x = [c["mean_predicted"] for c in curve]
        y = [c["fraction_positive"] for c in curve]
        ax.plot(x, y, marker="o", color=color, linewidth=2, label=label)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Observed late rate")
    ax.set_title("Calibration before and after isotonic")
    ax.legend(frameon=False, fontsize=9)
    _clean(ax)
    return _save(fig, figures_dir, "03_calibration.png")


def fig_topk_capture(metrics: dict, figures_dir: Path) -> Path:
    """4. Top-k follow-up capture vs the rule baseline."""
    ks = list(metrics["models"]["M_lgbm_isotonic"]["top_k"].keys())
    m_recall = [metrics["models"]["M_lgbm_isotonic"]["top_k"][k]["recall"] for k in ks]
    b0_recall = [metrics["models"]["B0_rule_baseline"]["top_k"][k]["recall"] for k in ks]
    x = np.arange(len(ks))
    width = 0.38
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.bar(x - width / 2, b0_recall, width, color=HALDI, label="B0 rule baseline")
    ax.bar(x + width / 2, m_recall, width, color=INDIGO, label="M LightGBM")
    ax.set_xticks(x, [f"top {k}%" for k in ks])
    ax.set_ylabel("Share of lates captured")
    ax.set_title("Follow-up capture by capacity")
    ax.legend(frameon=False, fontsize=9)
    _clean(ax)
    return _save(fig, figures_dir, "04_topk_capture.png")


def _shap_importance(shap: dict) -> list[tuple[str, float]]:
    """Mean absolute SHAP contribution per feature across leases."""
    totals: dict[str, list[float]] = defaultdict(list)
    for factors in shap.get("leases", {}).values():
        for f in factors:
            totals[f["feature"]].append(abs(f["contribution"]))
    ranked = sorted(((k, float(np.mean(v))) for k, v in totals.items()), key=lambda t: t[1], reverse=True)
    return ranked[:10]


def fig_shap_summary(shap: dict, figures_dir: Path) -> Path:
    """5. SHAP summary, top 10 features."""
    ranked = _shap_importance(shap)
    names = [r[0] for r in reversed(ranked)]
    values = [r[1] for r in reversed(ranked)]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(names, values, color=INDIGO)
    ax.set_xlabel("Mean absolute contribution")
    ax.set_title("Top 10 features by SHAP impact")
    _clean(ax)
    return _save(fig, figures_dir, "05_shap_summary.png")


def fig_slices(slices: dict, figures_dir: Path) -> Path:
    """6. Slice recall and false positive rate by occupation and language."""
    groups = ["occupation_type", "preferred_language_audit_only"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, group in zip(axes, groups):
        buckets = slices["slices"][group]
        labels = list(buckets)
        recall = [buckets[b]["recall"] for b in labels]
        fpr = [buckets[b]["fpr"] for b in labels]
        x = np.arange(len(labels))
        width = 0.38
        ax.bar(x - width / 2, recall, width, color=VERDIGRIS, label="Recall")
        ax.bar(x + width / 2, fpr, width, color=STAMP_RED, label="False positive rate")
        ax.set_xticks(x, labels, rotation=20, ha="right")
        ax.set_ylim(0, 1)
        ax.set_title(group.replace("_", " "))
        ax.legend(frameon=False, fontsize=8)
        _clean(ax)
    return _save(fig, figures_dir, "06_slices_recall_fpr.png")


def fig_sensitivity(simulation: dict, figures_dir: Path) -> Path:
    """7. Sensitivity heatmap of lates avoided across capacity and effect."""
    sweeps = simulation["effect_sweep"]
    rows = simulation["rows"]
    data = np.array(
        [[row["expected_late_avoided_model"][f"{s:.2f}"] for s in sweeps] for row in rows]
    )
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    im = ax.imshow(data, cmap="viridis", aspect="auto")
    ax.set_xticks(np.arange(len(sweeps)), [f"{int(s * 100)}%" for s in sweeps])
    ax.set_yticks(np.arange(len(rows)), [f"top {row['follow_up_per_cycle']}" for row in rows])
    ax.set_xlabel("Assumed effect of a follow-up")
    ax.set_ylabel("Follow-ups per cycle")
    ax.set_title("Lates avoided (assumption-based)")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", color="white", fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    _clean(ax)
    return _save(fig, figures_dir, "07_sensitivity_heatmap.png")


def fig_guardrails(llm_eval: dict, figures_dir: Path) -> Path:
    """8. Guardrail pass rates from llm/eval.py."""
    rates = llm_eval["guardrails"]
    names = list(rates)
    values = [rates[n]["pass_rate"] for n in names]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.bar(names, values, color=VERDIGRIS)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Pass rate")
    ax.set_title(f"Guardrail pass rates over {llm_eval['n_drafts']} drafts")
    ax.tick_params(axis="x", rotation=20)
    _clean(ax)
    return _save(fig, figures_dir, "08_guardrail_pass_rates.png")


def fig_triage(triage_eval: dict, figures_dir: Path) -> Path:
    """9. Triage accuracy and the emergency-recall number."""
    labels = [
        ("category\naccuracy", triage_eval["category_accuracy"], INDIGO),
        ("urgency\naccuracy", triage_eval["urgency_accuracy"], INDIGO_SOFT),
        ("emergency\nrecall", triage_eval["emergency_recall"], STAMP_RED),
        ("emergency\nprecision", triage_eval["emergency_precision"], VERDIGRIS),
    ]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.bar([item[0] for item in labels], [item[1] for item in labels], color=[item[2] for item in labels])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Score")
    ax.set_title(f"Maintenance triage over {triage_eval['n']} labelled complaints")
    for i, (_, value, _) in enumerate(labels):
        ax.text(i, value + 0.02, f"{value:.2f}", ha="center", color=INDIGO, fontsize=9)
    _clean(ax)
    return _save(fig, figures_dir, "09_triage_scores.png")


def render_eval_report(arts: dict[str, Any]) -> str:
    """Assemble docs/eval_report.md from the artifacts, no hand-typed numbers."""
    metrics = arts["metrics"]
    slices = arts["slices"]
    simulation = arts["simulation"]
    llm_eval = arts["llm_eval"]

    lines: list[str] = []
    lines.append("# Evaluation report")
    lines.append("")
    lines.append(f"> {metrics['note']}")
    lines.append("")
    lines.append(
        f"Test rows: {metrics['n_test_rows']}. "
        f"Test base rate (>5 days late): {metrics['test_base_rate']:.3f}. "
        f"Operating threshold: {metrics['operating_threshold']:.3f}."
    )
    lines.append("")
    lines.append("## Model comparison (test set)")
    lines.append("")
    lines.append("| Model | PR-AUC | ROC-AUC | Brier | ECE |")
    lines.append("|---|---|---|---|---|")
    labels = {
        "B0_rule_baseline": "B0 rule baseline",
        "B1_logistic": "B1 logistic",
        "M_lgbm_raw": "M LightGBM (raw)",
        "M_lgbm_isotonic": "M LightGBM (isotonic)",
    }
    for key, label in labels.items():
        m = metrics["models"][key]
        lines.append(
            f"| {label} | {m['pr_auc']:.3f} | {m['roc_auc']:.3f} | {m['brier']:.3f} | {m['ece']:.3f} |"
        )
    lines.append("")
    lines.append(metrics["calibration_note"])
    lines.append("")
    lines.append("## Ablation (occupation removed)")
    lines.append("")
    ab = metrics["ablation_no_occupation"]
    lines.append(f"PR-AUC {ab['pr_auc']:.3f}, ROC-AUC {ab['roc_auc']:.3f}.")
    lines.append("")
    lines.append("## Follow-up capacity (top share of leases per cycle)")
    lines.append("")
    ks = list(metrics["models"]["M_lgbm_isotonic"]["top_k"])
    lines.append("| Share | " + " | ".join(f"{k}%" for k in ks) + " |")
    lines.append("|---" * (len(ks) + 1) + "|")
    for metric_name in ("precision", "recall"):
        vals = [metrics["models"]["M_lgbm_isotonic"]["top_k"][k][metric_name] for k in ks]
        label = metric_name.capitalize()
        lines.append(f"| {label} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    lines.append("")
    lines.append("## Slices")
    lines.append("")
    for group, buckets in slices["slices"].items():
        lines.append(f"### {group.replace('_', ' ')}")
        lines.append("")
        lines.append("| Bucket | n | Late rate | Recall | False positive rate |")
        lines.append("|---|---|---|---|---|")
        for bucket, s in buckets.items():
            lines.append(
                f"| {bucket} | {s['n']} | {s['late_rate']:.3f} | {s['recall']:.3f} | {s['fpr']:.3f} |"
            )
        lines.append("")
    lines.append("Gap flags (differences above the threshold are called out):")
    lines.append("")
    for flag in slices["gap_flags"]:
        lines.append(
            f"- {flag['slice']} {flag['metric']}: {flag['a']} vs {flag['b']} gap {flag['gap_pp']:.1f} points"
        )
    lines.append("")
    lines.append("## Simulation")
    lines.append("")
    lines.append(f"Label: {simulation['label']}. {simulation['caveat']}")
    lines.append("")
    lines.append("| Follow-ups | " + " | ".join(f"{int(s * 100)}%" for s in simulation["effect_sweep"]) + " |")
    lines.append("|---" * (len(simulation["effect_sweep"]) + 1) + "|")
    for row in simulation["rows"]:
        vals = [f"{row['expected_late_avoided_model'][f'{s:.2f}']:.2f}" for s in simulation["effect_sweep"]]
        lines.append(f"| top {row['follow_up_per_cycle']} | " + " | ".join(vals) + " |")
    lines.append("")
    if llm_eval:
        lines.append("## Guardrails")
        lines.append("")
        lines.append(
            f"{llm_eval['n_drafts']} drafts, provider: {llm_eval['provider']}, "
            f"fallback rate {llm_eval['fallback_rate']:.3f}."
        )
        lines.append("")
        lines.append("| Guardrail | Pass rate | Passed | Failed |")
        lines.append("|---|---|---|---|")
        for name, r in llm_eval["guardrails"].items():
            lines.append(f"| {name} | {r['pass_rate']:.3f} | {r['passed']} | {r['failed']} |")
        lines.append("")
    triage_eval = arts.get("triage_eval")
    if triage_eval:
        lines.append("## Maintenance triage")
        lines.append("")
        lines.append(
            f"{triage_eval['n']} labelled complaints. Category accuracy "
            f"{triage_eval['category_accuracy']:.3f}, urgency accuracy "
            f"{triage_eval['urgency_accuracy']:.3f}."
        )
        lines.append("")
        lines.append(
            f"Emergency recall {triage_eval['emergency_recall']:.3f} over "
            f"{triage_eval['emergency_support']} emergencies; emergency precision "
            f"{triage_eval['emergency_precision']:.3f}. Gas smell, sparks, fire, flooding and "
            "structural cracks are always forced to emergency, so recall does not depend on the model."
        )
        lines.append("")
    lines.append("## Limitations and failure modes")
    lines.append("")
    lines.append("- Synthetic data with planted effects; do not read these as production accuracy.")
    lines.append("- Small test set, so slice gaps and confidence intervals are noisy.")
    lines.append("- Isotonic calibration trades ranking (PR-AUC) for probability quality (Brier, ECE).")
    lines.append("- The simulation is assumption-based; it does not measure behaviour change.")
    lines.append("- Reminder messages are drafts; a human approves every one before it is sent.")
    lines.append("- Maintenance triage is keyword/LLM assisted; an emergency is always escalated but a "
                 "human still dispatches the trade.")
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    for n in range(1, 10):
        matches = sorted((DOCS / "figures").glob(f"{n:02d}_*.png"))
        for m in matches:
            lines.append(f"- ![{m.stem}](figures/{m.name})")
    lines.append("")
    return "\n".join(lines)


def main(figures_dir: Path = FIGURES, report_path: Path | None = None) -> list[Path]:
    """Generate every figure and write the eval report. Returns figure paths."""
    _setup_style()
    arts = load_artifacts()
    written: list[Path] = []

    if arts["preds"] is not None and arts["metrics"]:
        written.append(fig_cumulative_late_rate(arts["preds"], figures_dir))
        written.append(fig_pr_curves(arts["preds"], arts["metrics"], figures_dir))
    if arts["metrics"]:
        written.append(fig_calibration(arts["metrics"], figures_dir))
        written.append(fig_topk_capture(arts["metrics"], figures_dir))
    if arts["shap"]:
        written.append(fig_shap_summary(arts["shap"], figures_dir))
    if arts["slices"]:
        written.append(fig_slices(arts["slices"], figures_dir))
    if arts["simulation"]:
        written.append(fig_sensitivity(arts["simulation"], figures_dir))
    if arts["llm_eval"]:
        written.append(fig_guardrails(arts["llm_eval"], figures_dir))
    if arts["triage_eval"]:
        written.append(fig_triage(arts["triage_eval"], figures_dir))

    report = report_path or (DOCS / "eval_report.md")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_eval_report(arts), encoding="utf-8")
    written.append(report)
    return written


if __name__ == "__main__":
    paths = main()
    for path in paths:
        print(f"Wrote {path}")
