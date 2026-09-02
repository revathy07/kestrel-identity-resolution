# Phase 13 business-estimation outputs

Run the truth-isolated estimator from the repository root:

```powershell
python -m src.business.estimate_customers
```

Tracked compact outputs:

- `business_estimate.json` and `business_estimate.md`: count bridge, recommended estimate,
  uncertainty ranges, workload scenarios and risk statement;
- `count_simulations.csv`: deterministic Monte Carlo count distribution;
- `observable_traffic_summary.csv`: observable automation and QA exclusions by source;
- `score_bin_match_rates.csv`: frozen-test match-rate calibration by predeclared score bin;
- `business_estimate_evaluation.json` and `.md`: separate hidden-truth evaluation, generated
  only after the estimator and its inputs have been frozen.

`observable_traffic_records.csv.gz` is a large reproducible row-level diagnostic and remains
ignored. Its SHA-256 hash is recorded in the estimate manifest.
