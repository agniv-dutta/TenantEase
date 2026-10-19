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

On the synthetic data, the paired lease bootstrap PR-AUC difference for raw LightGBM minus logistic regression is 0.010 (95% interval -0.042 to 0.058), so the models cannot be distinguished here. The synthetic process was built with logistic effects, so near parity is expected. Logistic coefficients are directly readable; SHAP explanations for LightGBM are an approximation. Boosting was kept because it handles missing values and interactions without manual feature engineering, and the pipeline is the thing being demonstrated. Against B0, the raw LightGBM minus rule baseline PR-AUC difference is 0.209 (95% interval 0.144 to 0.274); paired differences for ROC-AUC and Brier are available in metrics.json.

## Data

Synthetic: 6 properties, ~140 units, 24 closed cycles, 540 test rows.
Test base rate of >5-days-late: 16.9%.
Time split: train first 16 cycles, validate 17-20, test 21-24.
Excluded from features: name, phone, property, locality, preferred language,
preferred channel. Occupation type is included behind a config flag and ablated below.

## Metrics (test set only)

| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Brier | ECE |
|---|---|---|---|---|
| B0 rule baseline | 0.286 [0.187, 0.388] | 0.667 | 0.196 | 0.193 |
| B1 logistic | 0.485 [0.354, 0.621] | 0.774 | 0.113 | 0.031 |
| M LightGBM (raw) | 0.495 [0.355, 0.625] | 0.779 | 0.115 | 0.044 |
| M LightGBM + isotonic | 0.448 [0.314, 0.571] | 0.778 | 0.113 | 0.053 |
| M LightGBM + sigmoid (Platt) | 0.495 [0.355, 0.625] | 0.779 | 0.122 | 0.083 |
| M LightGBM + smoothed isotonic | 0.495 [0.355, 0.625] | 0.779 | 0.116 | 0.053 |
| M shipped calibrator (isotonic) | 0.448 [0.314, 0.571] | 0.778 | 0.113 | 0.053 |

Shipped calibration: isotonic (M_lgbm_isotonic). Selected on validation set by lowest Brier score, with ECE as tie-breaker; PR-AUC is reported for ranking transparency.
Ranking in product uses `raw_score`; calibrated probabilities are used for display, tiers and outlook simulation.

Operating threshold (Youden's J on validation): 0.200.

### Follow-up capacity (top K% of leases per cycle)

| K | Precision | Recall |
|---|---|---|
| top 5% | 67.9% | 21.1% |
| top 10% | 62.5% | 38.4% |
| top 15% | 51.2% | 45.2% |
| top 20% | 45.4% | 54.3% |

## Slices and fairness audit

Ablation without occupation type: PR-AUC 0.415 (with occupation 0.448).

Gap flags (any pairwise gap above 10 percentage points at the operating threshold):
- occupation_type: recall gap of 77.3 points between business and salaried
- occupation_type: recall gap of 80.7 points between gig and salaried
- occupation_type: recall gap of 83.3 points between salaried and student
- occupation_type: fpr gap of 25.7 points between business and gig
- occupation_type: fpr gap of 21.7 points between business and salaried
- occupation_type: fpr gap of 54.8 points between business and student
- occupation_type: fpr gap of 47.4 points between gig and salaried
- occupation_type: fpr gap of 29.1 points between gig and student
- occupation_type: fpr gap of 76.5 points between salaried and student
- tenure_group: recall gap of 37.8 points between cold_start and established
- tenure_group: fpr gap of 18.1 points between cold_start and established
- rent_band: recall gap of 18.0 points between 10k_to_20k and 20k_plus
- rent_band: recall gap of 17.7 points between 10k_to_20k and under_10k
- rent_band: recall gap of 35.7 points between 20k_plus and under_10k
- rent_band: fpr gap of 12.4 points between 10k_to_20k and 20k_plus
- preferred_language_audit_only: recall gap of 12.3 points between hi and hinglish

## Limitations

- Synthetic data with planted effects; real accuracy is unknown.
- The nudge-effect simulation is assumption-based, not measured. Proving
  that nudges change behaviour needs a real A/B test.
- Occupation type and locality can act as proxies for protected characteristics
  in India; locality and language are excluded, occupation is ablated and audited.
- Reminders are only drafted and approved in the prototype, never sent.
