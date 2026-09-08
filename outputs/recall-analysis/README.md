# Recall-gap analysis outputs

These compact artifacts diagnose selected-model misses using only the person-disjoint
development and validation partitions. The frozen test is not read, and no row/person
identifier is emitted.

- `recall_gap_analysis.json` records summary metrics, input hashes and the isolation contract.
- `recall_gap_analysis.md` explains the measured feature-development priorities.
- `recall_gap_by_source_pair.csv` attributes unresolved true pairs by source combination.
- `unresolved_patterns.csv` groups missed matches by evidence and conflict signature.
- `score_proximity.csv` describes match prevalence around the fixed MCT bands.

Regenerate with:

```bash
python -m src.evaluation.analyze_recall_gaps
```
