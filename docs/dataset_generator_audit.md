# Dataset generator audit

This audit treats `Dataset Prompt - Assessment No.6.pdf` as the data-generation
specification. The separate assessment PDF describes the downstream identity-resolution
solution (MCT scoring, the 12-record cluster cap, the 40-record worthless-evidence rule,
evaluation, memo, and presentation); those are not generator requirements.

## Current verdict

The corrected generator satisfies every audited dataset-brief check at full scale. The
deterministic seed-42 run generated exactly 300,000 invented people and 420,000 source
rows; the independent validator reported **90 PASS, 0 FAIL, 0 WARN, 0 NOT VERIFIABLE**.

## Resolved findings

1. **Controlled scale and identities.** The default plan produces 300,000 represented
   people and 420,000 rows. Exactly 25% of people have multiple source records, with a
   deliberately small six-plus group. `--scale` preserves these proportions for testing.

2. **Measured zero-evidence ceiling.** Evidence modes are explicitly assigned at pair
   level and measured from emitted rows. The 1% run measured 104 of 1,262 true pairs
   (8.24%) with no shared usable evidence. The latest full run measured 10,845 of
   126,315 true pairs (8.5857%).

3. **Source-backed hard negatives.** Father/son, university lab-device, common-name/city,
   and couple shared-email/payment-token cases exist in source rows. Only manifest-labelled,
   different-truth pairs count as explicit hard negatives. The full audit measured 17,330
   explicit candidates among 301,504 unique unordered post-Rule-2 pairs (5.7479%). Token
   incidences and poison-induced candidate pairs are reported separately.

4. **Real join-key problems.** App integer IDs are emitted as zero-padded store references.
   Ticketing has an account reference; the latest full run measured 931 of 21,386
   nonblank event IDs (4.35%) as unmatched.

5. **Format-aware duplicate generation.** Rows are duplicated as structured records, so
   quoted commas and multiline CSV fields remain valid. Exact and near duplicates retain
   ground truth; near duplicates shift their timestamp by seconds. Full-scale measured
   rates were exactly 2.00% and 1.00%.

6. **Enforced poison counts.** Placeholder phones, default DOBs, corporate booking email,
   kiosk device, and staff-test emails are assigned deterministically at scaled targets and
   counted from output. The kiosk value occurs on 40,000 full-scale rows; union-find over
   the documented naive evidence graph measures the resulting transitive poisoned cluster
   at 104,136 rows and 78,448 distinct hidden entities. The validator independently
   reconstructs exactly the same component and poison causes.

7. **Non-random missingness.** Missingness varies by source, country, and device type. At
   least three columns measure between 4% and 9%.

8. **Category and temporal messiness.** Channel, city, country, and device categories have
   multiple spellings. Six timestamp encodings share columns; local text is rendered at
   UTC+05:30 with the offset deliberately omitted. More than 3% of events arrive over nine
   days late, and every source is shuffled.

9. **Measured reporting.** Row counts, an explicit total, distinct people, pairwise and
   canonical unrecoverable rates, unique candidate pairs, explicit hard-negative rate,
   poison-only pairs, poison sizes, and largest-cluster record/person counts are computed
   and independently reconciled.

10. **Addressable ground truth.** Every physical row has a map entry. Subscriptions expose
    `subscription_id`, social mapping uses `provider_id`, and `entity_type` distinguishes
    invented humans from automated traffic.

11. **Synthetic safety.** People are created from synthetic syllables and synthetic
   domains. Phone numbers use unassigned country code `+999`, so they cannot route to a
   real subscriber.

12. **Hidden canonical metadata.** `hidden/canonical_duplicate_links.jsonl` contains 99,000
    evaluation-only star links with non-reversible truth keys, intended recoverability and
    evidence modes. All 99,000 links and labels reconcile with observable source evidence.

13. **Subtle automated traffic.** The 5% hidden-labelled bot population uses neutral normal
    identities. Behaviour differs through low engagement, a 360-second activity window and
    zero-median ticket recording delay; no obvious bot marker occurs in normal outputs.

## Validation commands

Fast proportional validation:

```bash
python scripts/generate_synthetic_dataset.py --scale 0.01 --output-dir data/generated-small
python src/validate_generated_data.py --data-dir data/generated-small --output-dir outputs-small
python -m unittest discover -s tests -v
```

Full validation (completed successfully):

```bash
python scripts/generate_synthetic_dataset.py --output-dir data/generated
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

The validator is read-only and exits with status 1 if any mandatory requirement fails.
