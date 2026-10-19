"""Evaluate maintenance triage on the labelled fixture set.

Reports category accuracy, urgency accuracy and — the number that matters most
for safety — the emergency recall. Writes ``triage_eval.json`` into the ML
artifacts directory so the eval report can quote it.

    python -m app.llm.triage_eval
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.llm.triage import Urgency, classify
from app.ml.train import ARTIFACTS

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "maintenance_complaints.json"


def load_fixtures(path: Path = FIXTURES) -> list[dict[str, Any]]:
    """Load the labelled complaints."""
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify every fixture and compute accuracies and emergency recall."""
    category_hits = 0
    urgency_hits = 0
    emergency_support = 0
    emergency_predicted = 0
    emergency_hits = 0
    methods: Counter[str] = Counter()
    category_confusion: Counter[str] = Counter()
    misses: list[dict[str, Any]] = []

    for item in fixtures:
        result = classify(item["text"])
        triage = result.triage
        methods[result.method] += 1
        category_ok = triage.category.value == item["category"]
        urgency_ok = triage.urgency.value == item["urgency"]
        category_hits += category_ok
        urgency_hits += urgency_ok
        if not category_ok:
            category_confusion[f"{item['category']} -> {triage.category.value}"] += 1
            misses.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "label_category": item["category"],
                    "pred_category": triage.category.value,
                    "label_urgency": item["urgency"],
                    "pred_urgency": triage.urgency.value,
                }
            )
        if item["urgency"] == Urgency.emergency.value:
            emergency_support += 1
            emergency_hits += triage.urgency is Urgency.emergency
        if triage.urgency is Urgency.emergency:
            emergency_predicted += 1

    n = len(fixtures)
    return {
        "n": n,
        "category_accuracy": category_hits / n,
        "urgency_accuracy": urgency_hits / n,
        "emergency_support": emergency_support,
        "emergency_recall": emergency_hits / emergency_support if emergency_support else 1.0,
        "emergency_precision": (
            emergency_hits / emergency_predicted if emergency_predicted else 1.0
        ),
        "methods": dict(methods),
        "category_confusion": dict(category_confusion),
        "misses": misses,
    }


def main(artifacts_dir: Path = ARTIFACTS) -> Path:
    """Evaluate and write the artifact. Returns the artifact path."""
    report = evaluate(load_fixtures())
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "triage_eval.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"n={report['n']} category_accuracy={report['category_accuracy']:.3f}", end=" ")
    print(f"urgency_accuracy={report['urgency_accuracy']:.3f}", end=" ")
    print(f"emergency_recall={report['emergency_recall']:.3f}", end=" ")
    print(f"emergency_precision={report['emergency_precision']:.3f}")
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    main()
