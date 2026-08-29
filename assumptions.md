# Assumptions and failure conditions

This file records the assumptions behind the identity-resolution work and what would break
if they are wrong.

## Data and identifier assumptions

1. **A source plus physical row ordinal uniquely identifies an ingested record.** Source
   record IDs may repeat because exact and near duplicate rows are deliberate. If source
   export ordering is unstable between ingestion and evaluation, ordinal-based joins to the
   synthetic truth map would be invalid; production scoring itself would still run, but the
   reported evaluation would not be trustworthy.

2. **The optional social-login phone, device and city fields represent provider-returned
   identity data.** If they are operational metadata rather than user identifiers, they
   must be removed from the schema map and Phase 4–6 outputs regenerated.

3. **The supplied hashed-email representation is SHA-256 of the normalized email.** If a
   provider uses a salt, pepper, different canonicalization or another algorithm, the
   email-hash bridge will produce false non-matches and must be disabled or replaced by a
   provider-approved comparison service.

4. **A plus suffix and dots in an email local part are discovery signals, not universally
   equivalent mailbox semantics.** Providers differ in their treatment. These variants are
   never allowed to overwrite the stored email and do not auto-merge alone. If the business
   treats these transformations as universally exact, precision could fall.

5. **A nine-digit phone suffix is useful for candidate discovery and review.** It does not
   infer a country code. If markets have shorter national numbers or recycled/shared phone
   use is high, its evidence weight and review-floor eligibility require revalidation.

6. **Verified email means the provider verified control of that exact mailbox.** If
   “verified” has a weaker source-specific meaning, its 0.90 evidence weight is too strong
   and verified-email-only pairs should move from auto-merge to review.

## Frequency and scoring assumptions

7. **Rule 2 frequency is calculated across all current physical records after
   normalization.** Incremental or partial runs can undercount common values and mistakenly
   give them weight. A production deployment must refresh or conservatively maintain the
   global registry before scoring new data.

8. **The strongest feature in a correlated family is sufficient.** Exact email, email
   skeleton and email hash are not independent confirmations. If this grouping is removed,
   correlated transformations would inflate scores and cause unsafe merges.

9. **Independent evidence families can be combined with noisy-OR.** The weights are
   documented business-risk choices, not probabilities learned from real customers. If
   real prevalence, error rates or source semantics differ, the numerical score is not
   calibrated and must be reviewed against newly labelled data.

10. **Ordinary shared email plus payment token is a household risk.** That combination is
    capped below auto-merge unless a third independent family or stronger verified evidence
    exists. If payment tokens are actually person-specific rather than household-specific,
    this is conservative and increases review volume rather than privacy risk.

11. **Human review capacity can absorb roughly 22,263 pair decisions for this run.** If that
    queue is operationally unaffordable, records must not be silently auto-merged. The safe
    alternatives are improved independent evidence, prioritised review, or leaving more
    pairs separate.

## Evaluation and deployment assumptions

12. **Synthetic hidden IDs accurately represent the generated identities.** The reported
    100% frozen-test merge precision validates this fixture, not future customer data. Real
    deployment requires independently labelled examples and ongoing false-merge monitoring.

13. **The deterministic SHA-256 partition is frozen before test release.** Changing pair
    identity, partition logic, scoring weights or thresholds after examining the test result
    invalidates it as a holdout and requires a new untouched test set.

14. **False merges are materially more costly than missed matches.** This justifies 100%
    observed merge precision with lower auto-merge recall. If the cost asymmetry changes,
    the evidence weights can be reconsidered, but the assessment's 0.88 and 0.62 thresholds
    remain fixed.

15. **Phase 6 pair decisions are not clusters.** Transitive union can amplify one bad edge.
    Auto-merge edges must not be deployed until Phase 7 applies Rule 1 exactly: every
    connected component with more than 12 source records is rejected in full and
    quarantined, never partially merged.
