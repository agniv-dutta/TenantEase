# AI opportunity report

## Opportunity

Small residential landlords often notice late rent only after a due date has
passed. TenantEase already has a payment ledger, so a Khata view can turn past
payment behaviour into a reminder worklist that helps a manager contact tenants
earlier. The opportunity is earlier, more consistent follow-up, not an automated
decision about a tenant.

## Users and workflow

The primary user is a property manager reviewing monthly rent collection. The
manager opens the highest-risk leases, reads the plain-language reasons and
reminder plan, checks a drafted message, and approves it. Payments remain
manually confirmed. The score only schedules reminders; it is not used for rent
pricing, eviction, or tenant screening.

## Evidence and success measures

The prototype evaluates a fixed, synthetic, held-out set. The README metrics
table is generated from `backend/app/ml/artifacts/metrics.json`; detailed
comparisons, slice analysis and uncertainty are in
[`eval_report.md`](eval_report.md) and [`model_card.md`](model_card.md). Success
for this proof of concept means the features obey the as-of cutoff, the ranked
worklist beats the simple late-last-cycle baseline on the synthetic test set,
and a manager can inspect and approve a guarded message. It does not establish
real-world lift or production accuracy.

## Risks and controls

- Leakage: features are computed only from information available at their
  as-of timestamp, with a test that shuffles future payments.
- Unfair or sensitive use: name, phone, property, locality and message language
  are excluded from risk features. Occupation is gated by a configuration flag.
- Harmful action: the score may schedule reminders only. A person reviews the
  proposed action; no message is sent automatically.
- Synthetic-to-real gap: all demonstration records are synthetic and seeded.
  Results must not be treated as evidence about real tenants.

Supporting implementation: [`features.py`](../backend/app/ml/features.py),
[`test_features.py`](../backend/tests/test_features.py),
[`reminders.py`](../backend/app/api/reminders.py),
[`synthetic_data.md`](synthetic_data.md), and
[`model_card.md`](model_card.md).
