# Phase 5 candidate-blocking outputs

Regenerate the production-style artifacts from the repository root:

```bash
python -m src.blocking.generate_candidates --normalized-path outputs/normalization/normalized_identifiers.csv.gz --output-dir outputs/blocking
```

Then run the isolated synthetic-label audit:

```bash
python -m src.evaluation.evaluate_blocking --candidate-path outputs/blocking/candidate_pairs.csv.gz --canonical-links data/generated/hidden/canonical_duplicate_links.jsonl --hard-negatives data/generated/hard_negatives.json --output-dir outputs/blocking
```

| Artifact | Purpose | Git policy |
|---|---|---|
| `candidate_pairs.csv.gz` | Physical record pairs plus the rules that discovered them | Generated locally |
| `normalized_rule2_registry.json` | Internal normalized values occurring on more than 40 records | Generated locally; contains unmasked values |
| `normalized_rule2_values.csv` | Masked Rule 2 audit summary | Committed |
| `blocking_rule_summary.csv` | Eligible blocks and pair incidence by rule | Committed |
| `candidate_manifest.json` | Counts, hashes, reduction and phase boundaries | Committed |
| `blocking_report.md` | Production blocking methodology and result | Committed |
| `blocking_evaluation.json` | Aggregate synthetic-label recall and hard-negative coverage | Committed |
| `blocking_evaluation.md` | Stakeholder-readable evaluation | Committed |

Candidate generation reads only the Phase 4 normalized table and configuration. The
evaluation command runs afterward and cannot change the candidate output. Phase 5 makes no
match decisions, calculates no MCT score, and forms no clusters.
