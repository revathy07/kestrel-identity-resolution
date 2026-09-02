# Heuristic versus logistic clustering comparison

**Promotion decision:** promote_logistic_clusters

| Metric | Heuristic baseline | Logistic challenger | Change |
|---|---:|---:|---:|
| Auto-merge edges | 81,041 | 99,272 | +18,231 |
| Final resolved identities | 355,762 | 342,900 | -12,862 |
| Accepted merged components | 48,814 | 57,403 | +8,589 |
| Accepted singleton components | 306,948 | 285,497 | -21,451 |
| Implied merged record pairs | 81,863 | 99,372 | +17,509 |
| False merged record pairs | 0 | 0 | +0 |
| Cluster precision | 100.0000% | 100.0000% | +0.0000 pp |
| Human pairwise recall | 51.5085% | 65.3699% | +13.8614 pp |
| Mixed-person components | 0 | 0 | +0 |
| Hard negatives co-clustered | 0 | 0 | +0 |
| Rule 1 quarantined components | 0 | 0 | +0 |
| Largest accepted component | 6 | 6 | +0 |

## Promotion gates

- PASS: `same_physical_record_population`
- PASS: `cluster_precision_not_lower`
- PASS: `zero_false_merged_pairs`
- PASS: `zero_mixed_person_components`
- PASS: `zero_hard_negatives_co_clustered`
- PASS: `rule1_applied_without_partial_merges`
- PASS: `accepted_components_respect_size_cap`
- PASS: `human_pairwise_recall_not_lower`

The operational identity count includes automated traffic. It is not presented as the final number of human customers; bot/test handling and review-queue uncertainty remain separate business-analysis steps.
