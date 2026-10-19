"""Tests for maintenance triage: safety override, fallback, fixtures, API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.llm import triage
from app.llm.triage import Category, Triage, Urgency, classify, emergency_reasons, keyword_classify
from app.llm.triage_eval import evaluate, load_fixtures
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Test client with startup/shutdown events fired."""
    with TestClient(app) as c:
        yield c


def test_keyword_classify_is_deterministic() -> None:
    """The keyword classifier returns the same answer twice."""
    first = keyword_classify("The kitchen tap is dripping slowly.")
    second = keyword_classify("The kitchen tap is dripping slowly.")
    assert first == second
    assert first.category is Category.plumbing


@pytest.mark.parametrize(
    "text",
    [
        "There is a gas leak smell near the stove.",
        "The switchboard is throwing sparks.",
        "A small fire started in the meter box.",
        "The flat is flooding, water everywhere.",
        "There is a big crack in the wall.",
    ],
)
def test_safety_override_forces_emergency(text: str) -> None:
    """Each safety phrase forces an emergency whatever the classifier said."""
    result = classify(text)
    assert result.triage.urgency is Urgency.emergency
    assert result.forced_emergency is True
    assert emergency_reasons(text)


def test_gas_is_its_own_category() -> None:
    """Gas issues get their own category and a gas technician trade."""
    result = classify("The gas stove in the kitchen will not light.")
    assert result.triage.category is Category.gas
    assert result.triage.suggested_trade == "gas technician"


def test_provider_json_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid provider reply is used and validated."""
    payload = (
        '{"category": "pest", "urgency": "soon", "suggested_trade": "pest control", '
        '"one_line_summary": "Rats in the kitchen."}'
    )
    monkeypatch.setattr(triage.provider_mod, "provider_available", lambda: True)
    monkeypatch.setattr(triage.provider_mod, "complete", lambda *a, **k: payload)
    result = classify("Kaafi machhar aa gaye hain.")
    assert result.method == "llm"
    assert result.triage == Triage(
        category=Category.pest,
        urgency=Urgency.soon,
        suggested_trade="pest control",
        one_line_summary="Rats in the kitchen.",
    )


def test_invalid_provider_reply_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid provider JSON falls back to the keyword classifier."""
    monkeypatch.setattr(triage.provider_mod, "provider_available", lambda: True)
    monkeypatch.setattr(triage.provider_mod, "complete", lambda *a, **k: "not json at all")
    result = classify("The kitchen tap is dripping.")
    assert result.method == "keyword"
    assert result.triage.category is Category.plumbing


def test_model_emergency_is_never_downgraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if the model says routine, a safety phrase forces an emergency."""
    payload = (
        '{"category": "other", "urgency": "routine", "suggested_trade": "handyman", '
        '"one_line_summary": "Smell in the kitchen."}'
    )
    monkeypatch.setattr(triage.provider_mod, "provider_available", lambda: True)
    monkeypatch.setattr(triage.provider_mod, "complete", lambda *a, **k: payload)
    result = classify("There is a strong smell of gas in the kitchen.")
    assert result.method == "llm"
    assert result.triage.urgency is Urgency.emergency


def test_fixtures_are_labelled() -> None:
    """The fixture set is complete and uses only valid labels."""
    fixtures = load_fixtures()
    assert len(fixtures) == 60
    for item in fixtures:
        assert set(item) >= {"id", "text", "language", "category", "urgency"}
        assert item["category"] in {c.value for c in Category}
        assert item["urgency"] in {u.value for u in Urgency}
        assert item["text"].strip()


def test_emergency_recall_is_full() -> None:
    """The gate: emergency recall must be 100 percent on the fixtures."""
    report = evaluate(load_fixtures())
    assert report["emergency_recall"] == 1.0
    assert report["emergency_precision"] >= 0.9
    assert report["category_accuracy"] >= 0.9
    assert report["urgency_accuracy"] >= 0.9


def test_maintenance_endpoint_creates_and_lists(client: TestClient) -> None:
    """Raising a complaint triages it, stores it and lists it for the lease."""
    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    r = client.post(
        "/api/maintenance",
        json={"lease_id": lease_id, "text": "There is a gas leak smell in the kitchen."},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["urgency"] == "emergency"
    assert body["forced_emergency"] is True
    assert body["method"] == "keyword"

    listed = client.get(f"/api/maintenance?lease_id={lease_id}")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())


def test_maintenance_endpoint_errors(client: TestClient) -> None:
    """Unknown lease is a 404 and blank text is a validation error."""
    r = client.post("/api/maintenance", json={"lease_id": 999999, "text": "Something broke."})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

    lease_id = client.get("/api/ledger").json()["rows"][0]["lease_id"]
    r2 = client.post("/api/maintenance", json={"lease_id": lease_id, "text": "   "})
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "validation_error"
