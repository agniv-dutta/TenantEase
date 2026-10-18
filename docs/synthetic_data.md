# Synthetic data: generating process

Every row in `data/khata.db` is synthetic. Names and phone numbers come from
`faker` with the `en_IN` locale. The generator is seeded (default 42) so every
run is byte-for-byte reproducible. **Nothing here describes real tenants.**

## Portfolio shape

- 6 properties in Jaipur localities (Mansarovar, Malviya Nagar, Vaishali
  Nagar, Jagatpura, C-Scheme, Sodala), 140 units total.
- 1–3 BHK mix (35/45/20), rent correlated with BHK and a locality factor
  (C-Scheme highest, Jagatpura lowest), noise log-normal, clamped to
  6,000–35,000 INR and rounded to 500.
- About 10% of units start vacant; overall occupancy sits near 88%.
- 24 fully closed monthly cycles ending at the last completed month, plus one
  open current cycle whose payment rows exist but have no `paid_date`.
- About 15% of initial tenants churn mid-window; most re-let units get a new
  tenant 1–2 months later, so cold-start leases appear throughout.
- At each lease anniversary there is a 50% chance of a 5–10% rent hike,
  rounded to 500.

## Payment behaviour (planted effects and directions)

Each tenant has a **hidden reliability `z`, never stored in the database**,
drawn from a distribution that depends on `occupation_type`:

| Occupation | z distribution | Direction |
|---|---|---|
| salaried | N(1.2, 0.8) | most reliable on average |
| business | N(0.4, 1.4) | most variable |
| student | N(-0.2, 1.0) | less reliable |
| gig | N(0.0, 1.0) | middling, variable |

The probability of paying **more than 5 days late** is a logistic function:

```
logit = intercept - 0.9*z + 0.8*prev_late + 0.5*festival + 0.6*hike_recent
        + 0.7*cash_share + 0.5*short_tenure + N(0, 0.8)
```

Planted effects and their **direction**:

| Effect | Definition | Direction on late risk |
|---|---|---|
| reliability z | hidden per-tenant | higher z lowers risk |
| autocorrelation | previous cycle was >5 days late | raises risk |
| festival month | cycle month in Oct, Nov (Diwali) or April | raises risk |
| recent rent hike | first 2 cycles after a hike | raises risk |
| cash share | share of cash payments in last 6 cycles | raises risk |
| short tenure | fewer than 4 months in the lease | raises risk |
| logistic noise | N(0, 0.8) per cycle | adds irreducible variance |

The intercept is binary-searched at generation time so the base rate of
"> 5 days late" lands between 15% and 22% (target 18.5%). If a trained model
scores above 0.95 ROC-AUC, that is a bug to investigate, not a result: the
noise term and the unobserved `z` keep a performance ceiling around 0.78–0.86.

**Days late.** If late, `days_late` is drawn from an exponential with mean 6
(median ≈ 6), capped at 30. If not late, `days_late` is uniform 0–5 and the
paid date can be up to 5 days early (never before the cycle month). About 3%
of payments are partial (40–80% of rent). About 2% of late cases are
never-paid-within-30-days (`paid_date` NULL, counted as 31 days late for the
target).

## What the model is expected to recover

Because every effect above is planted, a well-built pipeline should beat the
"late last cycle implies late this cycle" rule baseline on PR-AUC. The metrics
show the **pipeline works under known conditions**; they are not a forecast of
production accuracy.
