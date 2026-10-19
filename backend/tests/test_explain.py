"""Plain-language factor rendering: coverage, formatting, and snapshots."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.explain import load_model, render_factor
from app.ml.features import FEATURE_METADATA

RAW_DECIMALS = re.compile(r"\d+\.\d{3,}")
VERBS = {
    "was",
    "were",
    "is",
    "are",
    "has",
    "have",
    "had",
    "paid",
    "went",
    "falls",
    "lives",
    "runs",
    "works",
    "affected",
    "due",
    "been",
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Test client with startup/shutdown events fired."""
    with TestClient(app) as c:
        yield c


def test_every_model_feature_has_a_template() -> None:
    """No feature the model can use is missing raise/lower wording."""
    bundle = load_model()
    templates = {m.name: m for m in FEATURE_METADATA}
    missing = [f for f in bundle["features"] if f not in templates]
    assert missing == []
    for meta in FEATURE_METADATA:
        assert meta.raise_template.strip()
        assert meta.lower_template.strip()


def test_sentences_are_human_readable(client: TestClient) -> None:
    """Across 50 scored leases, sentences have no raw floats, a verb and are short."""
    rows = client.get("/api/ledger").json()["rows"][:50]
    sentences = 0
    for row in rows:
        detail = client.get(f"/api/tenants/{row['lease_id']}").json()
        for factor in detail["top_factors"]:
            sentence = factor["sentence"]
            sentences += 1
            assert not RAW_DECIMALS.search(sentence), sentence
            assert len(sentence) < 90, f"{factor['feature']}: {sentence}"
            words = set(sentence.lower().split())
            assert words & VERBS, f"no verb in {factor['feature']}: {sentence}"
    assert sentences >= 50


def test_factor_snapshot_for_three_fixed_leases() -> None:
    """Three fixed lease rows render to exact, stable sentences."""
    serial_late = {
        "late_count_1": 1.0,
        "late_count_3": 2.0,
        "late_count_6": 3.0,
        "late_share_1": 1.0,
        "late_share_3": 2 / 3,
        "late_share_6": 0.5,
        "mean_days_late_6": 7.5,
        "max_days_late_6": 12.0,
        "days_late_trend": 0.8,
        "on_time_streak": 0.0,
        "prev_cycle_outstanding_days": 6.0,
        "tenure_months": 14.0,
        "is_cold_start": 0.0,
        "rent_amount": 9500.0,
        "rent_change_pct": 8.0,
        "cycles_since_rent_change": 4.0,
        "cash_share_last_6": 0.5,
        "last_payment_method": 1.0,
        "due_day": 5.0,
        "cycle_month_of_year": 11.0,
        "is_festival_month": 1.0,
        "bhk": 2.0,
    }
    clean_payer = {
        "late_count_6": 0.0,
        "late_share_6": 0.0,
        "on_time_streak": 30.0,
        "tenure_months": 30.0,
        "rent_change_pct": 0.0,
        "cycles_since_rent_change": 18.0,
        "is_cold_start": 0.0,
        "last_payment_method": 0.0,
        "prev_cycle_outstanding_days": 0.0,
    }
    cold_start = {
        "is_cold_start": 1.0,
        "tenure_months": 1.0,
        "late_count_1": 0.0,
        "last_payment_method": -1.0,
    }

    assert render_factor("late_count_6", serial_late, 0.42) == {
        "feature": "late_count_6",
        "sentence": "Paid more than 5 days late in 3 of the last 6 months",
        "direction": "raises",
        "contribution": 0.42,
    }
    assert render_factor("cash_share_last_6", serial_late, 0.18) == {
        "feature": "cash_share_last_6",
        "sentence": "Has paid in cash in 3 of the last 6 months",
        "direction": "raises",
        "contribution": 0.18,
    }
    assert render_factor("tenure_months", serial_late, -0.12) == {
        "feature": "tenure_months",
        "sentence": "Has been a tenant for 14 months",
        "direction": "lowers",
        "contribution": -0.12,
    }
    assert render_factor("late_count_6", clean_payer, -0.3) == {
        "feature": "late_count_6",
        "sentence": "Paid on time in all of the last 6 months",
        "direction": "lowers",
        "contribution": -0.3,
    }
    assert render_factor("rent_change_pct", clean_payer, -0.05) == {
        "feature": "rent_change_pct",
        "sentence": "Rent has not changed",
        "direction": "lowers",
        "contribution": -0.05,
    }
    assert render_factor("is_cold_start", cold_start, 0.35) == {
        "feature": "is_cold_start",
        "sentence": "Is a new tenant with fewer than 3 payment cycles on record",
        "direction": "raises",
        "contribution": 0.35,
    }
    assert render_factor("tenure_months", cold_start, 0.1) == {
        "feature": "tenure_months",
        "sentence": "Has been a tenant for 1 month",
        "direction": "raises",
        "contribution": 0.1,
    }
