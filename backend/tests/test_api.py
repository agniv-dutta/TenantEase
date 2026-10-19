"""Endpoint tests using FastAPI's TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import RiskScore


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Test client with startup/shutdown events fired."""
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    """Liveness probe."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_portfolio_summary(client: TestClient) -> None:
    """Summary returns counts and tiers that sum to active leases."""
    r = client.get("/api/portfolio/summary")
    assert r.status_code == 200
    body = r.json()
    tiers = body["tiers"]
    assert sum(tiers.values()) == body["active_leases"]
    assert body["total_rent_due_inr"] > 0
    assert 0 <= body["expected_collection_inr"] <= body["total_rent_due_inr"]


def test_ledger_rows_and_filter(client: TestClient) -> None:
    """Ledger returns rows with a current cell and honours the property filter."""
    r = client.get("/api/ledger?months=6")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) > 50
    row = body["rows"][0]
    assert row["current"]["status"] == "open"
    assert len(row["cycles"]) == 6
    pid = row["property_id"]
    r2 = client.get(f"/api/ledger?property_id={pid}")
    assert all(x["property_id"] == pid for x in r2.json()["rows"])


def test_risk_ranking_distinct_and_stable(client: TestClient) -> None:
    """Raw score ranking is mostly distinct and deterministic."""
    first = client.get("/api/ledger?months=6").json()["rows"]
    second = client.get("/api/ledger?months=6").json()["rows"]
    first_ids = [row["lease_id"] for row in first]
    second_ids = [row["lease_id"] for row in second]
    assert first_ids == second_ids

    with Session(engine) as session:
        scores = session.exec(select(RiskScore)).all()
    raw_values = [round(float(s.raw_score), 8) for s in scores]
    distinct_share = len(set(raw_values)) / max(1, len(raw_values))
    assert distinct_share >= 0.90


def test_ledger_invalid_months(client: TestClient) -> None:
    """Invalid months returns the consistent error body."""
    r = client.get("/api/ledger?months=99")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_months"


def test_tenant_detail_and_404(client: TestClient) -> None:
    """Tenant detail returns top factors and a plan; unknown lease is a 404 error body."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    r = client.get(f"/api/tenants/{lease_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_name"]
    assert isinstance(body["top_factors"], list)
    for factor in body["top_factors"]:
        assert factor["sentence"]
        assert factor["direction"] in {"raises", "lowers"}
        assert factor["strength"] in {"main", "moderate", "minor"}
        assert "contribution" not in factor
        assert "weight" not in factor
    assert isinstance(body["plan"], list)
    r2 = client.get("/api/tenants/999999")
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "not_found"


def test_tenant_validation_error(client: TestClient) -> None:
    """A non-integer path parameter yields a validation error body."""
    r = client.get("/api/tenants/not-a-number")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_outlook_band_ordering(client: TestClient) -> None:
    """The p10-p90 band brackets the expected curve."""
    r = client.get("/api/portfolio/outlook")
    assert r.status_code == 200
    body = r.json()
    assert len(body["points"]) >= 28
    for point in body["points"]:
        assert point["p10"] <= point["expected"] + 1e-6 <= point["p90"] + 2e-6
    assert body["total_due"] > 0


def test_model_card(client: TestClient) -> None:
    """Model card returns metrics, slices and markdown."""
    r = client.get("/api/model/card")
    assert r.status_code == 200
    body = r.json()
    assert "models" in body["metrics"]
    choice = body["metrics"].get("calibration_choice")
    if choice:
        shipped = body["metrics"]["models"]["M_lgbm_shipped"]["brier"]
        isotonic = body["metrics"]["models"]["M_lgbm_isotonic"]["brier"]
        assert shipped <= isotonic + 0.002
    assert "synthetic" in body["card_markdown"].lower() or "synthetic" in body["metrics"].get("note", "").lower()


def test_admin_reseed_disabled(client: TestClient) -> None:
    """Admin reseed is disabled by default."""
    r = client.post("/api/model/admin/reseed")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "disabled"


def test_reminder_draft_and_approve(client: TestClient) -> None:
    """Drafting then approving a reminder works and is never tenant-facing."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    r = client.post(
        "/api/reminders/draft",
        json={"lease_id": lease_id, "language": "hinglish", "tone": "friendly"},
    )
    assert r.status_code == 200
    draft = r.json()
    assert draft["status"] == "draft"
    assert "{PAY_LINK}" in draft["message"]
    assert draft["message"].count("{PAY_LINK}") == 1

    a = client.post(f"/api/reminders/{draft['id']}/approve")
    assert a.status_code == 200
    assert a.json()["status"] == "approved"
    assert a.json()["approved_at"] is not None


def test_reminder_draft_validation(client: TestClient) -> None:
    """Bad language rejects with a validation error body."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    r = client.post(
        "/api/reminders/draft",
        json={"lease_id": lease_id, "language": "fr", "tone": "friendly"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_language"


def test_reminder_approve_missing(client: TestClient) -> None:
    """Approving a missing reminder is a 404 error body."""
    r = client.post("/api/reminders/999999/approve")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_tenant_payload_never_contains_probability_text(client: TestClient) -> None:
    """Tenant-facing reminder text must not mention a probability or score."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    detail = client.get(f"/api/tenants/{lease_id}").json()
    for reminder in detail["reminders"]:
        text = reminder["message"].lower()
        for banned in ("probability", "risk score", "%", "score"):
            assert banned not in text
