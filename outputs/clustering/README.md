# Phase 7 capped-clustering outputs

Generate production components from the repository root:

```bash
python -m src.clustering.cluster_records --normalized-path outputs/normalization/normalized_identifiers.csv.gz --scored-path outputs/logistic/logistic_scored_candidate_pairs.csv.gz --output-dir outputs/clustering
```

Then run the isolated truth-based evaluator:

```bash
python -m src.evaluation.evaluate_clusters --assignments outputs/clustering/cluster_assignments.csv.gz --clustering-manifest outputs/clustering/clustering_manifest.json --truth-map data/generated/person_map.csv --canonical-links data/generated/hidden/canonical_duplicate_links.jsonl --hard-negatives data/generated/hard_negatives.json --output-dir outputs/clustering
```

| Artifact | Purpose | Git policy |
|---|---|---|
| `cluster_assignments.csv.gz` | Row-level proposed component, final cluster and Rule 1 status | Generated locally |
| `cluster_size_distribution.csv` | Component counts and records by size/status | Committed |
| `quarantined_components.csv` | Aggregate evidence and source content for cap hits | Committed |
| `clustering_manifest.json` | Counts, hashes, largest component and phase boundaries | Committed |
| `clustering_report.md` | Production clustering and Rule 1 report | Committed |
| `cluster_evaluation.json` | Aggregate truth-based precision, recall, purity and safety | Committed |
| `cluster_evaluation.md` | Stakeholder-readable cluster evaluation | Committed |

The production clusterer reads no hidden labels. The assignment table is excluded from Git
because it is a reproducible row-level intermediate. Components above 12 records receive no
final cluster ID and are never partially merged.

The standard artifacts use the logistic MCT selected on validation. The preceding heuristic
baseline and the explicit promotion checks remain documented under
`outputs/logistic-clustering/` and in Git history.
