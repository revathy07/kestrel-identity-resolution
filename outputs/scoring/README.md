# Phase 6 MCT scoring outputs

Generate production scores from the repository root:

```bash
python -m src.scoring.score_candidates --normalized-path outputs/normalization/normalized_identifiers.csv.gz --candidate-path outputs/blocking/candidate_pairs.csv.gz --rule2-registry outputs/blocking/normalized_rule2_registry.json --output-dir outputs/scoring
```

Evaluate development labels without releasing the frozen holdout:

```bash
python -m src.evaluation.evaluate_scoring --output-dir outputs/scoring --scope development
```

After freezing the configuration, release validation and the frozen-test partition:

```bash
python -m src.evaluation.evaluate_scoring --output-dir outputs/scoring --scope final
```

| Artifact | Purpose | Git policy |
|---|---|---|
| `scored_candidate_pairs.csv.gz` | Row-level MCT scores, evidence, conflicts and decisions | Generated locally |
| `labelled_development_set.csv.gz` | Person-disjoint 50% development labels without person IDs | Generated locally |
| `labelled_validation_set.csv.gz` | Person-disjoint 20% validation labels without person IDs | Generated locally |
| `labelled_test_set.csv.gz` | Person-disjoint frozen 30% test labels without person IDs | Generated locally |
| `mct_manifest.json` | Input hashes, thresholds, counts and phase boundaries | Committed |
| `mct_decision_summary.csv` | Counts in the three required MCT bands | Committed |
| `mct_feature_summary.csv` | Aggregate selected evidence features | Committed |
| `mct_conflict_summary.csv` | Aggregate conflict and safety flags | Committed |
| `mct_scoring_report.md` | Production scoring method and result | Committed |
| `mct_development_evaluation.*` | Development-only calibration result | Committed |
| `mct_evaluation.*` | Person-isolation proof plus validation, frozen-test and full safety results | Committed |

The scorer never reads labels. The evaluator runs after scoring and cannot alter an MCT
score. Hidden people connected by any candidate or explicit hard negative are assigned as
complete relationship components to development, validation or frozen test. This retains
every candidate while guaranteeing zero person overlap. Person IDs are never written to a
labelled pair file. Phase 6 assigns pair decision bands but does not perform transitive
merging or apply the 12-record cluster cap.
