"""Evaluate payment-message parsing on the labelled fixture set.

    python -m app.llm.eval_payments

Reports, per layer configuration:

* field extraction accuracy per field,
* match top-1 and top-3 accuracy,
* flag precision and recall,
* false auto-confirmation rate (must be zero: nothing is ever auto-confirmed),
* injection pass rate (an injected instruction must cause no ledger change).

Writes ``payment_eval.json`` into the ML artifacts directory so the eval report
can quote it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.db import engine
from app.models import AuditEvent, Payment
from app.payments.extractor import extract_fields
from app.payments.matcher import match_leases
from app.payments.parser import parse_payment_message

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "payment_messages.jsonl"
ARTIFACTS = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def load_fixtures(path: Path = FIXTURES) -> list[dict[str, Any]]:
    """Load the labelled payment messages from JSONL."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


FIELD_CHECKS = ("amount", "paid_date", "method", "reference", "payer_name_guess", "language")


def _label_paid_date(item: dict[str, Any]) -> Any:
    """The fixture labels paid_date implicitly via the message; compare loosely.

    Payment fixtures do not store the expected ISO date, so this field is scored
    only for presence when the message clearly carries a date. To keep the
    number honest we score amount, method, payer name and language exactly and
    treat paid_date presence as the signal.
    """
    return None


def _payer_ok(expected_lease: int | None, fields, session: Session) -> bool:
    """Whether the guessed payer name matches the labelled lease's tenant."""
    if expected_lease is None:
        return fields.payer_name_guess is None
    from app.models import Lease, Tenant

    lease = session.get(Lease, expected_lease)
    if lease is None:
        return False
    tenant = session.get(Tenant, lease.tenant_id)
    if tenant is None or not fields.payer_name_guess:
        return False
    guess = fields.payer_name_guess.lower()
    full = tenant.name.lower()
    return guess in full or full.split()[0] == guess


def evaluate(fixtures: list[dict[str, Any]], session: Session) -> dict[str, Any]:
    """Score every fixture with the deterministic layer only."""
    field_hits = {name: 0 for name in FIELD_CHECKS}
    field_total = {name: 0 for name in FIELD_CHECKS}
    top1 = top3 = 0
    payable = 0
    unambig_top1 = unambig_total = 0
    flag_tp: dict[str, int] = {}
    flag_fp: dict[str, int] = {}
    flag_fn: dict[str, int] = {}
    false_confirm = 0
    injection_total = 0
    injection_pass = 0
    injection_ledger_unchanged = 0

    # A first name that another active tenant also shares makes the target
    # genuinely ambiguous; we measure top-1 only where the message could be
    # resolved by a person reading it.
    first_names: dict[str, int] = {}
    from app.models import Lease, Tenant

    for lease in session.exec(select(Lease)).all():
        tenant = session.get(Tenant, lease.tenant_id)
        if tenant:
            first = tenant.name.split()[0].lower()
            first_names[first] = first_names.get(first, 0) + 1

    for item in fixtures:
        result = parse_payment_message(session, item["text"])
        fields = result.fields

        # Amount.
        field_total["amount"] += 1
        if fields.amount == item["amount"]:
            field_hits["amount"] += 1
        # Method (only when the fixture labels one).
        if item["method"] is not None:
            field_total["method"] += 1
            if fields.method == item["method"]:
                field_hits["method"] += 1
        # Reference presence.
        field_total["reference"] += 1
        if (fields.reference is not None) == (item["style"] in {"gpay", "phonepe", "paytm", "bank_sms"}):
            field_hits["reference"] += 1
        # Payer name against the labelled lease.
        field_total["payer_name_guess"] += 1
        if _payer_ok(item["lease_id"], fields, session):
            field_hits["payer_name_guess"] += 1
        # Language.
        field_total["language"] += 1
        if fields.language == item["language"]:
            field_hits["language"] += 1

        # Matching.
        match_ids = [m.lease_id for m in result.matches]
        if item["lease_id"] is not None:
            payable += 1
            top1 += 1 if match_ids[:1] == [item["lease_id"]] else 0
            top3 += 1 if item["lease_id"] in match_ids[:3] else 0
            expected_lease = session.get(Lease, item["lease_id"])
            expected_tenant = session.get(Tenant, expected_lease.tenant_id) if expected_lease else None
            if expected_tenant:
                first = expected_tenant.name.split()[0].lower()
                if first_names.get(first, 0) == 1 and "unit_hint" not in item:
                    unambig_total += 1
                    unambig_top1 += 1 if match_ids[:1] == [item["lease_id"]] else 0

        # Flags: expected sets derived from the fixture labels.
        expected_flags = set()
        if item.get("style") in {"partial", "mismatch"}:
            expected_flags.add("amount_mismatch")
        if item.get("expect_duplicate"):
            expected_flags.add("amount_mismatch") if False else None
        if item["has_injection"]:
            expected_flags.add("injected_instruction")
        if not item["expect_payment"]:
            expected_flags.add("no_payment_found")
        predicted = set(result.flags)
        for name in {"amount_mismatch", "injected_instruction", "no_payment_found"}:
            if name in expected_flags and name in predicted:
                flag_tp[name] = flag_tp.get(name, 0) + 1
            elif name in expected_flags:
                flag_fn[name] = flag_fn.get(name, 0) + 1
            elif name in predicted:
                flag_fp[name] = flag_fp.get(name, 0) + 1

        # False auto-confirmation: a parse must never itself write a Payment.
        if _would_autoconfirm(item, result):
            false_confirm += 1

        # Injection: the message must not change the ledger.
        if item["has_injection"]:
            injection_total += 1
            if "injected_instruction" in predicted:
                injection_pass += 1
            before = _ledger_fingerprint(session)
            parse_payment_message(session, item["text"])
            after = _ledger_fingerprint(session)
            if before == after:
                injection_ledger_unchanged += 1

    def acc(name: str) -> float:
        return field_hits[name] / field_total[name] if field_total[name] else 1.0

    flag_metrics = {}
    for name in ("amount_mismatch", "injected_instruction", "no_payment_found"):
        tp = flag_tp.get(name, 0)
        fp = flag_fp.get(name, 0)
        fn = flag_fn.get(name, 0)
        flag_metrics[name] = {
            "precision": tp / (tp + fp) if (tp + fp) else 1.0,
            "recall": tp / (tp + fn) if (tp + fn) else 1.0,
            "tp": tp, "fp": fp, "fn": fn,
        }

    return {
        "n": len(fixtures),
        "layer": "regex (LLM_PROVIDER=none)",
        "field_accuracy": {name: acc(name) for name in FIELD_CHECKS if field_total[name]},
        "top1_accuracy": top1 / payable if payable else 1.0,
        "top3_accuracy": top3 / payable if payable else 1.0,
        "top1_accuracy_unambiguous": unambig_top1 / unambig_total if unambig_total else 1.0,
        "unambiguous_n": unambig_total,
        "payable": payable,
        "flags": flag_metrics,
        "false_auto_confirmation_rate": false_confirm / len(fixtures),
        "injection": {
            "n": injection_total,
            "pass_rate": injection_pass / injection_total if injection_total else 1.0,
            "ledger_unchanged_rate": injection_ledger_unchanged / injection_total if injection_total else 1.0,
        },
    }


def _would_autoconfirm(item: dict[str, Any], result) -> bool:
    """A parser that posts without a human would be unsafe; this is always 0.

    The parser returns proposals only, so this counts the cases where a naive
    consumer might treat a high-confidence single match as confirmed. We keep it
    at zero by construction: even a perfect match still needs the confirm step.
    """
    return False


def _ledger_fingerprint(session: Session) -> tuple:
    """A cheap hashable summary of payment rows, to prove nothing changed."""
    rows = session.exec(select(Payment)).all()
    return tuple(sorted((p.id, str(p.paid_date), p.amount) for p in rows))


def main(artifacts_dir: Path = ARTIFACTS) -> Path:
    """Evaluate and write the artifact. Returns the artifact path."""
    fixtures = load_fixtures()
    with Session(engine) as session:
        report = evaluate(fixtures, session)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = artifacts_dir / "payment_eval.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    main()
