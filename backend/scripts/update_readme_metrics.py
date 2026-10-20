"""Refresh the README metrics table from the generated metrics JSON."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT / "backend" / "app" / "ml" / "artifacts" / "metrics.json"
README_PATH = ROOT / "README.md"
START = "<!-- metrics:start -->"
END = "<!-- metrics:end -->"


def update_readme_metrics() -> None:
    """Replace the marked README table with values in metrics.json."""
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    shipped = metrics["models"][metrics["shipped_model_key"]]
    baseline = metrics["models"]["B0_rule_baseline"]
    rows = [
        "| Model | PR-AUC | ROC-AUC | Brier score | Top 10% precision |",
        "|---|---:|---:|---:|---:|",
        f"| Shipped calibrated model | {shipped['pr_auc']:.4f} | {shipped['roc_auc']:.4f} | {shipped['brier']:.4f} | {shipped['top_k']['10']['precision']:.4f} |",
        f"| Late-last-cycle baseline | {baseline['pr_auc']:.4f} | {baseline['roc_auc']:.4f} | {baseline['brier']:.4f} | {baseline['top_k']['10']['precision']:.4f} |",
        "",
        f"Evaluation set: {metrics['n_test_rows']} lease-cycle rows; base rate {metrics['test_base_rate']:.4f}. Synthetic data only; not a forecast of production accuracy.",
    ]
    block = f"{START}\n" + "\n".join(rows) + f"\n{END}"
    readme = README_PATH.read_text(encoding="utf-8")
    start = readme.index(START)
    end = readme.index(END, start) + len(END)
    README_PATH.write_text(readme[:start] + block + readme[end:], encoding="utf-8")


if __name__ == "__main__":
    update_readme_metrics()
