# Phase 12 consolidated evaluation outputs

Regenerate the post-selection evaluation from the repository root:

```bash
python -m src.evaluation.consolidate_evaluation
```

| Artifact | Purpose |
|---|---|
| `evaluation_report.md` | Consolidated interpretation, error analysis and limitations |
| `evaluation_summary.json` | Machine-readable metrics, hashes and isolation assertions |
| `source_pair_performance.csv` | Frozen-test performance by source-system pair |
| `evidence_event_performance.csv` | Frozen-test performance for each evidence/conflict event |
| `identifier_availability_performance.csv` | Performance by valid endpoint-identifier availability |
| `score_band_performance.csv` | Validation/test calibration and decision-band behaviour |
| `unresolved_match_patterns.csv` | Aggregate review/separate true-match error patterns |
| `hard_negative_performance.csv` | Outcomes for each explicit hard-negative scenario |
| `pipeline_loss_attribution.csv` | Canonical links retained or unresolved by pipeline stage |

All subgroup conclusions use the person-disjoint frozen test. Outputs contain no record or
person identifiers, do not report overall accuracy, and do not modify the selected model,
thresholds, candidates or clusters.
