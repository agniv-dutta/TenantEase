# Evaluation report

> All numbers come from synthetic data with planted effects. Not a forecast of production accuracy.

Test rows: 540. Test base rate (>5 days late): 0.169. Operating threshold: 0.200.

## Model comparison (test set)

| Model | PR-AUC | ROC-AUC | Brier | ECE |
|---|---|---|---|---|
| B0 rule baseline | 0.286 | 0.667 | 0.196 | 0.193 |
| B1 logistic | 0.485 | 0.774 | 0.113 | 0.031 |
| M LightGBM (raw) | 0.495 | 0.779 | 0.115 | 0.044 |
| M LightGBM (isotonic) | 0.448 | 0.778 | 0.113 | 0.053 |

Isotonic calibration maps many distinct raw scores onto a few probability levels. That improves probability quality (Brier, ECE) but creates ties that reduce ranking metrics such as PR-AUC. The uncalibrated M is reported alongside the calibrated M for honesty.

## Ablation (occupation removed)

PR-AUC 0.415, ROC-AUC 0.748.

## Follow-up capacity (top share of leases per cycle)

| Share | 5% | 10% | 15% | 20% |
|---|---|---|---|---|
| Precision | 0.679 | 0.625 | 0.512 | 0.454 |
| Recall | 0.211 | 0.384 | 0.452 | 0.543 |

## Slices

### occupation type

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| business | 144 | 0.153 | 0.773 | 0.221 |
| gig | 100 | 0.310 | 0.806 | 0.478 |
| salaried | 252 | 0.079 | 0.000 | 0.004 |
| student | 44 | 0.409 | 0.833 | 0.769 |

### tenure group

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| cold_start | 3 | 0.333 | 1.000 | 0.000 |
| established | 537 | 0.168 | 0.622 | 0.181 |

### rent band

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| 10k_to_20k | 300 | 0.213 | 0.656 | 0.225 |
| 20k_plus | 140 | 0.150 | 0.476 | 0.101 |
| under_10k | 100 | 0.060 | 0.833 | 0.170 |

### preferred language audit only

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| en | 208 | 0.183 | 0.632 | 0.171 |
| hi | 112 | 0.152 | 0.706 | 0.210 |
| hinglish | 220 | 0.164 | 0.583 | 0.174 |

Gap flags (differences above the threshold are called out):

- occupation_type recall: business vs salaried gap 77.3 points
- occupation_type recall: gig vs salaried gap 80.7 points
- occupation_type recall: salaried vs student gap 83.3 points
- occupation_type fpr: business vs gig gap 25.7 points
- occupation_type fpr: business vs salaried gap 21.7 points
- occupation_type fpr: business vs student gap 54.8 points
- occupation_type fpr: gig vs salaried gap 47.4 points
- occupation_type fpr: gig vs student gap 29.1 points
- occupation_type fpr: salaried vs student gap 76.5 points
- tenure_group recall: cold_start vs established gap 37.8 points
- tenure_group fpr: cold_start vs established gap 18.1 points
- rent_band recall: 10k_to_20k vs 20k_plus gap 18.0 points
- rent_band recall: 10k_to_20k vs under_10k gap 17.7 points
- rent_band recall: 20k_plus vs under_10k gap 35.7 points
- rent_band fpr: 10k_to_20k vs 20k_plus gap 12.4 points
- preferred_language_audit_only recall: hi vs hinglish gap 12.3 points

## Simulation

Label: assumption-based, not measured. These are assumption-based projections with a swept nudge effect, not measured outcomes. Proving that nudges change behaviour needs a real A/B test.

| Follow-ups | 5% | 10% | 15% | 25% |
|---|---|---|---|---|
| top 5 | 0.55 | 1.10 | 1.65 | 2.74 |
| top 10 | 1.07 | 2.14 | 3.20 | 5.34 |
| top 15 | 1.45 | 2.91 | 4.36 | 7.27 |
| top 20 | 1.80 | 3.60 | 5.40 | 8.99 |
| top 30 | 2.49 | 4.98 | 7.47 | 12.45 |

## Guardrails

90 drafts, provider: none (template path), fallback rate 0.000.

| Guardrail | Pass rate | Passed | Failed |
|---|---|---|---|
| contains_amount | 1.000 | 90 | 0 |
| contains_due_date | 1.000 | 90 | 0 |
| pay_link_once | 1.000 | 90 | 0 |
| length | 1.000 | 90 | 0 |
| banned_terms | 1.000 | 90 | 0 |
| script | 0.978 | 88 | 2 |
| digits | 1.000 | 90 | 0 |

## Limitations and failure modes

- Synthetic data with planted effects; do not read these as production accuracy.
- Small test set, so slice gaps and confidence intervals are noisy.
- Isotonic calibration trades ranking (PR-AUC) for probability quality (Brier, ECE).
- The simulation is assumption-based; it does not measure behaviour change.
- Reminder messages are drafts; a human approves every one before it is sent.

## Figures

- ![01_cumulative_late_rate](figures/01_cumulative_late_rate.png)
- ![02_pr_curves](figures/02_pr_curves.png)
- ![03_calibration](figures/03_calibration.png)
- ![04_topk_capture](figures/04_topk_capture.png)
- ![05_shap_summary](figures/05_shap_summary.png)
- ![06_slices_recall_fpr](figures/06_slices_recall_fpr.png)
- ![07_sensitivity_heatmap](figures/07_sensitivity_heatmap.png)
- ![08_guardrail_pass_rates](figures/08_guardrail_pass_rates.png)
