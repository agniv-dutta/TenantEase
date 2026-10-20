# Model card: TenantEase Khata late-payment risk model

> **This model is trained on fully synthetic data with planted effects.**
> Metrics show the pipeline works under known conditions; they are not a
> forecast of production accuracy.

## Intended use

Rank leases by the risk of paying rent more than 5 days late in the coming
cycle so a property manager can schedule reminders earlier or personally
follow up with a few tenants.

## Out-of-scope use

Never use this score for eviction, rent pricing, tenant screening, or any
decision about a person. It only decides who gets an earlier or more
personal nudge.

## Why this model

The synthetic process uses logistic effects, so near parity between logistic regression and boosted trees is expected. Logistic coefficients are directly readable; SHAP explanations for LightGBM are an approximation. Boosting was kept because it handles missing values and interactions without manual feature engineering, and the pipeline is the thing being demonstrated. Paired lease bootstrap comparisons are reported in metrics.json.

## Data

Synthetic: 6 properties, ~140 units, 24 closed cycles, 528 test rows.
Test base rate of >5-days-late: 16.7%.
Time split: train first 16 cycles, validate 17-20, test 21-24.
Excluded from features: name, phone, property, locality, preferred language,
preferred channel. Occupation type is included behind a config flag and ablated below.

## Metrics (test set only)

| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Brier | ECE |
|---|---|---|---|---|
| B0 rule baseline | 0.275 [0.191, 0.366] | 0.653 | 0.191 | 0.188 |
| B1 logistic | 0.403 [0.271, 0.531] | 0.701 | 0.124 | 0.057 |
| M LightGBM (raw) | 0.353 [0.226, 0.482] | 0.680 | 0.128 | 0.043 |
| M LightGBM + isotonic | 0.318 [0.204, 0.442] | 0.688 | 0.131 | 0.060 |
| M LightGBM + sigmoid (Platt) | 0.353 [0.226, 0.482] | 0.680 | 0.128 | 0.040 |
| M LightGBM + smoothed isotonic | 0.353 [0.226, 0.482] | 0.680 | 0.128 | 0.038 |
| M shipped calibrator (isotonic) | 0.318 [0.204, 0.442] | 0.688 | 0.131 | 0.060 |

Shipped calibration: isotonic (M_lgbm_isotonic). Selected on validation set by lowest Brier score, with ECE as tie-breaker; PR-AUC is reported for ranking transparency.
Ranking in product uses `raw_score`; calibrated probabilities are used for display, tiers and outlook simulation.

Operating threshold (Youden's J on validation): 0.200.

### Follow-up capacity (top K% of leases per cycle)

| K | Precision | Recall |
|---|---|---|
| top 5% | 46.4% | 14.6% |
| top 10% | 44.2% | 26.6% |
| top 15% | 38.8% | 35.4% |
| top 20% | 34.6% | 40.6% |

## Slices and fairness audit

Ablation without occupation type: PR-AUC 0.319 (with occupation 0.318).

Gap flags (any pairwise gap above 10 percentage points at the operating threshold):
- occupation_type: recall gap of 76.1 points between business and salaried
- occupation_type: recall gap of 75.6 points between gig and salaried
- occupation_type: recall gap of 70.0 points between salaried and student
- occupation_type: fpr gap of 10.3 points between business and gig
- occupation_type: fpr gap of 66.3 points between business and salaried
- occupation_type: fpr gap of 76.7 points between gig and salaried
- occupation_type: fpr gap of 12.9 points between gig and student
- occupation_type: fpr gap of 63.8 points between salaried and student
- tenure_group: recall gap of 37.9 points between cold_start and established
- tenure_group: fpr gap of 21.8 points between cold_start and established
- rent_band: recall gap of 18.4 points between 10k_to_20k and 20k_plus
- rent_band: recall gap of 11.4 points between 20k_plus and under_10k
- preferred_language_audit_only: recall gap of 29.0 points between en and hinglish
- preferred_language_audit_only: recall gap of 34.5 points between hi and hinglish
- preferred_language_audit_only: fpr gap of 16.6 points between en and hinglish
- preferred_language_audit_only: fpr gap of 17.8 points between hi and hinglish

## Limitations

- Synthetic data with planted effects; real accuracy is unknown.
- The nudge-effect simulation is assumption-based, not measured. Proving
  that nudges change behaviour needs a real A/B test.
- Occupation type and locality can act as proxies for protected characteristics
  in India; locality and language are excluded, occupation is ablated and audited.
- Reminders are only drafted and approved in the prototype, never sent.
