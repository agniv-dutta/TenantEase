# Evaluation report

> All numbers come from synthetic data with planted effects. Not a forecast of production accuracy.

Test rows: 528. Test base rate (>5 days late): 0.167. Operating threshold: 0.200.

## Model comparison (test set)

| Model | PR-AUC | ROC-AUC | Brier | ECE |
|---|---|---|---|---|
| B0 rule baseline | 0.275 | 0.653 | 0.191 | 0.188 |
| B1 logistic | 0.403 | 0.701 | 0.124 | 0.057 |
| M LightGBM (raw) | 0.353 | 0.680 | 0.128 | 0.043 |
| M LightGBM (isotonic) | 0.318 | 0.688 | 0.131 | 0.060 |
| M LightGBM (sigmoid/Platt) | 0.353 | 0.680 | 0.128 | 0.040 |
| M LightGBM (smoothed isotonic) | 0.353 | 0.680 | 0.128 | 0.038 |
| M shipped (isotonic) | 0.318 | 0.688 | 0.131 | 0.060 |

Ranking in product uses raw model scores; displayed probabilities are calibrated.
Shipped calibration: isotonic. Selected on validation set by lowest Brier score, with ECE as tie-breaker; PR-AUC is reported for ranking transparency.

## Ablation (occupation removed)

PR-AUC 0.319, ROC-AUC 0.685.

## Follow-up capacity (top share of leases per cycle)

| Share | 5% | 10% | 15% | 20% |
|---|---|---|---|---|
| Precision | 0.464 | 0.442 | 0.388 | 0.346 |
| Recall | 0.146 | 0.266 | 0.354 | 0.406 |

## Slices

### occupation type

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| business | 120 | 0.158 | 0.895 | 0.713 |
| gig | 76 | 0.355 | 0.889 | 0.816 |
| salaried | 272 | 0.110 | 0.133 | 0.050 |
| student | 60 | 0.200 | 0.833 | 0.688 |

### tenure group

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| cold_start | 8 | 0.125 | 1.000 | 0.571 |
| established | 520 | 0.167 | 0.621 | 0.353 |

### rent band

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| 10k_to_20k | 308 | 0.172 | 0.566 | 0.361 |
| 20k_plus | 140 | 0.171 | 0.750 | 0.353 |
| under_10k | 80 | 0.138 | 0.636 | 0.348 |

### preferred language audit only

| Bucket | n | Late rate | Recall | False positive rate |
|---|---|---|---|---|
| en | 204 | 0.176 | 0.528 | 0.292 |
| hi | 112 | 0.170 | 0.474 | 0.280 |
| hinglish | 212 | 0.156 | 0.818 | 0.458 |

Gap flags (differences above the threshold are called out):

- occupation_type recall: business vs salaried gap 76.1 points
- occupation_type recall: gig vs salaried gap 75.6 points
- occupation_type recall: salaried vs student gap 70.0 points
- occupation_type fpr: business vs gig gap 10.3 points
- occupation_type fpr: business vs salaried gap 66.3 points
- occupation_type fpr: gig vs salaried gap 76.7 points
- occupation_type fpr: gig vs student gap 12.9 points
- occupation_type fpr: salaried vs student gap 63.8 points
- tenure_group recall: cold_start vs established gap 37.9 points
- tenure_group fpr: cold_start vs established gap 21.8 points
- rent_band recall: 10k_to_20k vs 20k_plus gap 18.4 points
- rent_band recall: 20k_plus vs under_10k gap 11.4 points
- preferred_language_audit_only recall: en vs hinglish gap 29.0 points
- preferred_language_audit_only recall: hi vs hinglish gap 34.5 points
- preferred_language_audit_only fpr: en vs hinglish gap 16.6 points
- preferred_language_audit_only fpr: hi vs hinglish gap 17.8 points

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

## Maintenance triage

60 labelled complaints. Category accuracy 1.000, urgency accuracy 1.000.

Emergency recall 1.000 over 12 emergencies; emergency precision 1.000. Gas smell, sparks, fire, flooding and structural cracks are always forced to emergency, so recall does not depend on the model.

## Payment capture from pasted messages

60 labelled messages, layer: regex (LLM_PROVIDER=none). Match top-3 accuracy 1.000, top-1 0.889 (0.878 on the 41 messages a person could resolve from a unique first name).

| Field | Accuracy |
|---|---|
| amount | 1.000 |
| method | 1.000 |
| reference | 1.000 |
| payer name guess | 0.960 |
| language | 1.000 |

| Flag | Precision | Recall |
|---|---|---|
| amount mismatch | 1.000 | 1.000 |
| injected instruction | 1.000 | 1.000 |
| no payment found | 1.000 | 1.000 |

False auto-confirmation rate 0.000 (a parse never posts a payment). Injection pass rate 1.000 over 3 messages; the ledger was unchanged in 1.000 of them.

## Limitations and failure modes

- Synthetic data with planted effects; do not read these as production accuracy.
- Small test set, so slice gaps and confidence intervals are noisy.
- Ranking uses raw scores while display and simulation use calibrated probabilities.
- The simulation is assumption-based; it does not measure behaviour change.
- Reminder messages are drafts; a human approves every one before it is sent.
- Maintenance triage is keyword/LLM assisted; an emergency is always escalated but a human still dispatches the trade.

## Figures

- ![01_cumulative_late_rate](figures/01_cumulative_late_rate.png)
- ![02_pr_curves](figures/02_pr_curves.png)
- ![03_calibration](figures/03_calibration.png)
- ![04_topk_capture](figures/04_topk_capture.png)
- ![05_shap_summary](figures/05_shap_summary.png)
- ![06_slices_recall_fpr](figures/06_slices_recall_fpr.png)
- ![07_sensitivity_heatmap](figures/07_sensitivity_heatmap.png)
- ![08_guardrail_pass_rates](figures/08_guardrail_pass_rates.png)
- ![09_triage_scores](figures/09_triage_scores.png)
- ![10_payment_parsing](figures/10_payment_parsing.png)
