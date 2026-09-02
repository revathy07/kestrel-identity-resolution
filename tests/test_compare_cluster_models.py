from __future__ import annotations

import unittest

from src.evaluation.compare_cluster_models import promotion_checks


def manifest(*, records: int = 100, largest: int = 6, partial: int = 0) -> dict:
    return {
        "total_source_records": records,
        "rule1_maximum_source_records": 12,
        "partial_merges_from_quarantined_components": partial,
        "largest_accepted_component_size": largest,
    }


def evaluation(*, precision: float = 1.0, false_pairs: int = 0, recall: float = 0.6,
               mixed: int = 0, hard: int = 0) -> dict:
    return {
        "pairwise_cluster_metrics": {
            "precision": precision,
            "false_positive_merged_pairs": false_pairs,
            "recall_humans": recall,
        },
        "accepted_cluster_purity": {"mixed_person_components": mixed},
        "hard_negative_metrics": {"co_clustered_after_transitivity": hard},
    }


class ClusterComparisonTests(unittest.TestCase):
    def test_safe_higher_recall_challenger_passes_every_gate(self) -> None:
        checks = promotion_checks(
            manifest(), evaluation(recall=0.5), manifest(), evaluation(recall=0.7)
        )
        self.assertTrue(all(checks.values()))

    def test_one_transitive_false_merge_blocks_promotion(self) -> None:
        checks = promotion_checks(
            manifest(), evaluation(), manifest(), evaluation(precision=0.99, false_pairs=1, mixed=1)
        )
        self.assertFalse(checks["cluster_precision_not_lower"])
        self.assertFalse(checks["zero_false_merged_pairs"])
        self.assertFalse(checks["zero_mixed_person_components"])

    def test_rule1_partial_merge_or_oversized_acceptance_blocks_promotion(self) -> None:
        checks = promotion_checks(
            manifest(), evaluation(), manifest(largest=13, partial=1), evaluation(recall=0.7)
        )
        self.assertFalse(checks["rule1_applied_without_partial_merges"])
        self.assertFalse(checks["accepted_components_respect_size_cap"])


if __name__ == "__main__":
    unittest.main()
