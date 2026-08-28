# Dataset guide

`generated/` contains the deterministic seed-42 full-scale synthetic fixture. All people,
identifiers, events, and labels are invented. The directory is committed so reviewers can
reproduce the published measurements without first running the full generator.

## Source-system files

| File | Format | Rows | Purpose |
|---|---|---:|---|
| `generated/app_users.csv` | CSV | 120,000 | App identities and activity |
| `generated/store_customers.csv` | CSV | 80,000 | Store customer identities |
| `generated/ticketing.jl` | JSON Lines | 80,000 | Ticket bookings and recorded times |
| `generated/subscriptions.xlsx` | Excel | 50,000 | Content subscriptions |
| `generated/social_logins.json` | JSON array | 90,000 | Provider-specific nested login payloads |

These five files are the only source-system inputs intended for the matching pipeline.

## Evaluation and provenance files

| File | Purpose |
|---|---|
| `generated/person_map.csv` | Row-level hidden entity truth |
| `generated/hard_negatives.json` | Explicit different-person labelled pairs |
| `generated/hidden/canonical_duplicate_links.jsonl` | Canonical same-person evaluation links |
| `generated/generation_report.json` | Parameters, measured rates, counts, and definitions |

Evaluation files must not be used to construct matching features, candidate blocks, MCT
scores, or clusters. They exist only to measure the completed pipeline.

## Regeneration

From the repository root:

```bash
python scripts/generate_synthetic_dataset.py --output-dir data/generated
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

For routine development, use `--scale 0.01` and `data/generated-small`; that directory is
ignored by Git.
