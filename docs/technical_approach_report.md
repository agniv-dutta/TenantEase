# Technical approach report

## System design

The seed generator creates a reproducible SQLite portfolio using Faker's
`en_IN` locale and seed 42. A feature builder creates lease-cycle examples at
their as-of timestamps. The pipeline trains and calibrates the late-payment
model, persists its artifacts, and serves current-cycle scores through FastAPI.
The React and TypeScript client reads the ledger, portfolio, reminder, payment,
audit and outlook APIs. Reminder generation can use a configured LLM, with
templates as the offline fallback; guardrails gate approval. See the diagram in
the root README and [`synthetic_data.md`](synthetic_data.md).

## Data and model

The target is payment more than five days after the due date. Features are
limited to data available before the prediction cutoff. Tenant names and phones,
property and locality, and message language are not model inputs. Occupation is
optional behind `USE_OCCUPATION`. The model card and evaluation report describe
the chronological split, calibration, comparisons, subgroup slices and
uncertainty: [`model_card.md`](model_card.md),
[`eval_report.md`](eval_report.md).

## Product and service boundaries

FastAPI endpoints serve ledger, portfolio summaries, outlook, reminders,
payments, audit events and maintenance triage. Payment parsing proposes fields
and a ranked lease shortlist; a person selects the lease and confirms the
payment. Audit events are server-authored and append-only. Reminder messages are
drafts until approval and are never sent by this prototype. The risk score is
for scheduling reminders only.

## Reproduction and verification

Run `make setup`, `make seed`, `make train`, and `make eval`; `make check` runs
the backend and frontend checks. `backend/scripts/update_readme_metrics.py`
refreshes the README metrics block from the evaluation artifact. Feature
leakage, seed invariants, API routes and audit event kinds have pytest coverage.
Frontend accessibility, screenshot and walkthrough scripts live under
`frontend/scripts/`.

## Limitations

All data and results are synthetic, with planted effects. The model has no
demonstrated production accuracy, fairness, tenant outcomes, or causal reminder
effect. The outlook what-if is assumption-based. Deployment security,
authentication, real payment provider integration and real-world validation are
outside this prototype.
