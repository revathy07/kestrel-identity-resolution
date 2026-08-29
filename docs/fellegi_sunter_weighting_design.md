# Fellegi-Sunter Weighting Challenger Design

**Status:** Pre-implementation design and exploratory measurement

**Date:** 30 August 2026

## Purpose

The existing MCT configuration is a manually positioned, explainable baseline. Its decimal
weights were chosen relative to the assessment's mandatory 0.88 and 0.62 decision bands;
they were not estimated from empirical agreement probabilities.

This challenger will test a second MCT score based on Fellegi-Sunter-style likelihood
ratios. It will not silently replace the heuristic baseline. The two methods will be
evaluated on the same person-disjoint partitions, and a later logistic-regression challenger
will be a separate experiment.

## Research basis

Fellegi and Sunter formulate record linkage as a comparison between the match hypothesis
`M` and non-match hypothesis `U`. For an observed evidence event `e`:

`m(e) = P(e | M)`

`u(e) = P(e | U)`

`weight(e) = log2(m(e) / u(e))`

Primary references:

- Fellegi, I. P. and Sunter, A. B. (1969), *A Theory for Record Linkage*:
  https://doi.org/10.1080/01621459.1969.10501049
- Winkler, W. E. (2000), *Using the EM Algorithm for Weight Computation in the
  Fellegi-Sunter Model of Record Linkage*:
  https://www.census.gov/content/dam/Census/library/working-papers/2000/adrm/rr2000-05.pdf

## Frozen experimental contract

1. Estimate parameters from `labelled_development_set.csv.gz` only.
2. Reject any training row not marked `development`.
3. Use only `positive_evidence` and `conflicts` as empirical events.
4. Never use the heuristic `mct_score`, heuristic `decision`, record IDs, blocking rule,
   hard-negative scenario or hidden person identity as a predictor.
5. Estimate event probabilities with Jeffreys smoothing (`alpha = 0.5`) so zero observed
   counts cannot produce infinite weights.
6. Treat event absence as neutral because absence can mean missing or unavailable data, not
   a verified disagreement. Explicit conflicts provide negative evidence.
7. Start from the observed development candidate match prior and add present-event log
   likelihood ratios.
8. Convert posterior odds to a score from 0 to 1 and apply the unchanged 0.88 and 0.62 MCT
   thresholds.
9. Use validation for comparison and diagnostic decisions. Do not train from validation or
   frozen-test labels.
10. Retain the challenger result even if it performs worse.

This is a sparse Fellegi-Sunter-style challenger rather than a claim that all comparison
events are conditionally independent. The existing feature-family selection prevents
multiple email agreements from being counted independently, but residual dependencies will
remain a documented limitation and a reason to test logistic regression afterward.

## Pre-implementation development measurement

The person-disjoint development set contains 67,163 matching and 36,600 non-matching
candidate pairs. The initial event scan found:

| Event | Matches with event | Non-matches with event | Smoothed m | Smoothed u | Present log2 LR |
|---|---:|---:|---:|---:|---:|
| Exact device ID | 47,494 | 25,553 | 0.707142 | 0.698164 | +0.018 |
| Exact email | 16,946 | 1,959 | 0.252315 | 0.053537 | +2.237 |
| Exact payment token | 1,024 | 1,959 | 0.015254 | 0.053537 | -1.811 |
| Name and city | 42,574 | 8,752 | 0.633889 | 0.239133 | +1.406 |
| Account-reference conflict | 463 | 6,596 | 0.006901 | 0.180227 | -4.707 |
| Name conflict | 15,839 | 26,662 | 0.235833 | 0.728464 | -1.627 |
| Household email/payment risk | 0 | 1,959 | 0.000007 | 0.053537 | -12.812 |

These measurements show that the heuristic ordering is not automatically supported by the
candidate population. In particular, device agreement is almost non-discriminative and
shared payment is associated with non-matches in this synthetic fixture. They justify an
empirical challenger but do not yet establish frozen-test performance.

## Required outputs

- Learned event probabilities and log-likelihood weights with training counts and hashes.
- Truth-isolated application scores for every candidate pair.
- Development and validation comparison against the heuristic MCT baseline.
- Frozen-test comparison only after the model artifact and validation decision are frozen.
- Hard-negative, review-volume and source-pair error analysis.
