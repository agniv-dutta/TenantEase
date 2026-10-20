"""Ledger month columns must be contiguous: six closed cycles, then the open one.

Regression tests for the missing-month bug, where the ledger showed Mar..Aug
and then the open cycle because the seed left a gap, and for short rows where
a recently re-let lease returned fewer than six month cells.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.api.common import payment_cell
from app.main import app
from app.models import Payment, Reminder


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _month_index(iso: str) -> int:
    """Turn an ISO month start into a comparable month number."""
    year, month = iso.split("-")[:2]
    return int(year) * 12 + int(month)


def _expected_closed_months(months: int) -> list[str]:
    """The ``months`` closed cycles immediately before the open cycle."""
    open_cycle = clock.open_cycle()
    out: list[str] = []
    for offset in range(months, 0, -1):
        index = open_cycle.year * 12 + open_cycle.month - 1 - offset
        out.append(f"{index // 12:04d}-{index % 12 + 1:02d}-01")
    return out


def test_ledger_cycles_are_contiguous_for_every_property(client: TestClient) -> None:
    """Each lease shows 6 consecutive closed months, then the open cycle."""
    open_cycle = clock.open_cycle().isoformat()
    expected = _expected_closed_months(6)
    body = client.get("/api/ledger?months=6").json()
    assert body["cycle_month"] == open_cycle
    assert body["rows"], "the ledger has no rows"

    property_ids = {row["property_id"] for row in body["rows"]}
    for property_id in sorted(property_ids):
        rows = [row for row in body["rows"] if row["property_id"] == property_id]
        assert rows
        for row in rows:
            months = [cell["cycle_month"] for cell in row["cycles"]]
            assert months == expected, f"lease {row['lease_id']} months: {months}"
            assert row["current"]["cycle_month"] == open_cycle
            for earlier, later in zip(months, months[1:]):
                assert _month_index(later) - _month_index(earlier) == 1


def test_short_histories_are_padded_not_truncated(client: TestClient) -> None:
    """A lease billed for fewer prior months still shows every month column."""
    expected = _expected_closed_months(6)
    rows = client.get("/api/ledger?months=6").json()["rows"]
    vacant_cells = 0
    for row in rows:
        months = [cell["cycle_month"] for cell in row["cycles"]]
        assert months == expected, f"lease {row['lease_id']} is short: {months}"
        for cell in row["cycles"]:
            if cell["status"] == "vacant":
                vacant_cells += 1
                assert cell["paid_date"] is None, "a vacant cell cannot carry a payment"
            else:
                assert cell["status"] in {
                    "paid_on_time",
                    "paid_late",
                    "unpaid_overdue",
                    "unpaid_upcoming",
                }
    assert vacant_cells > 0, "expected at least one padded month for a re-let lease"


def test_months_query_returns_the_same_window(client: TestClient) -> None:
    """A shorter window still ends on the open cycle, with no gap."""
    body = client.get("/api/ledger?months=3").json()
    expected = _expected_closed_months(3)
    for row in body["rows"]:
        assert [cell["cycle_month"] for cell in row["cycles"]] == expected


def test_summary_reports_as_of_date(client: TestClient) -> None:
    """The summary states the demo clock it describes."""
    summary = client.get("/api/portfolio/summary").json()
    assert summary["as_of_date"] == clock.today().isoformat()
    assert summary["cycle_month"] == clock.open_cycle().isoformat()


def test_outlook_reports_as_of_date(client: TestClient) -> None:
    """The outlook marks the day it projects from, never later than today."""
    outlook = client.get("/api/portfolio/outlook?months=2026-10").json()
    as_of = outlook["as_of_date"]
    assert as_of == clock.today().isoformat()
    assert _month_index(as_of[:8] + "01") == _month_index(outlook["cycle_month"])


def test_outbox_dates_never_run_ahead_of_the_demo_clock() -> None:
    """Reminders stamped by the app stay on or before DEMO_TODAY."""
    from sqlmodel import Session, select

    from app.db import engine

    with Session(engine) as session:
        reminders = session.exec(select(Reminder)).all()
    for reminder in reminders:
        created = reminder.created_at.date()
        assert created <= clock.today(), f"reminder {reminder.id} created {created}"
        if reminder.approved_at is not None:
            assert reminder.approved_at.date() <= clock.today()


def test_due_soon_cell_follows_the_demo_clock() -> None:
    """An unpaid bill due after the demo date is still upcoming."""
    open_cycle = clock.open_cycle()
    due_today = Payment(
        lease_id=1,
        cycle_month=open_cycle,
        due_date=clock.today(),
        amount=12000,
        method="upi",
    )
    due_tomorrow = Payment(
        lease_id=1,
        cycle_month=open_cycle,
        due_date=clock.today() + timedelta(days=1),
        amount=12000,
        method="upi",
    )
    assert payment_cell(due_today, open_cycle).status == "open"
    assert payment_cell(due_tomorrow, open_cycle).status == "unpaid_upcoming"


def test_seed_writes_a_row_per_lease_for_the_ledger_window(client: TestClient) -> None:
    """Every lease in the ledger has a payment row for each open-cycle month."""
    rows = client.get("/api/ledger?months=6").json()["rows"]
    assert all(len(row["cycles"]) == 6 for row in rows)
