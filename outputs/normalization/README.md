# Phase 4 normalization outputs

Regenerate these artifacts from the repository root:

```bash
python -m src.normalization.normalize_identifiers --data-dir data/generated --output-dir outputs/normalization
```

| Artifact | Purpose | Git policy |
|---|---|---|
| `normalized_identifiers.csv.gz` | Long-form raw, profiling and normalized identifier observations | Generated locally |
| `normalization_summary.csv` | Missing, valid, invalid, changed and flagged counts by field | Committed |
| `normalization_issues.csv` | Aggregated quality flags without direct identifier examples | Committed |
| `normalization_manifest.json` | Counts, configuration/output hashes, source fingerprints and phase boundaries | Committed |
| `normalization_report.md` | Concise stakeholder-readable methodology and results | Committed |

The compressed normalized table contains 3,820,000 rows and is approximately 47.2 MiB.
It is intentionally excluded from Git as a reproducible intermediate to avoid growing the
repository history with derived row-level data. Its deterministic SHA-256 is recorded in
the committed manifest.

The table preserves `raw_value` alongside `profiling_key`, `normalized_value`, status,
transformation, quality flags and evidence role. It contains no candidate pairs, similarity
features, MCT scores, match decisions, clusters or evaluation labels.
