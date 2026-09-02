from __future__ import annotations

import unittest

from src.evaluation.compare_mct_models import select_from_validation


class ModelComparisonTests(unittest.TestCase):
    def test_selection_uses_validation_not_better_frozen_test(self) -> None:
        models = {
            "safe_validation_winner": {
                "validation": {
                    "auto_merge_false_positives": 0,
                    "auto_merge_recall_within_candidates": 0.70,
                    "assisted_recall_within_candidates": 0.80,
                    "human_review_pairs": 20,
                },
                "frozen_test": {"auto_merge_recall_within_candidates": 0.10},
            },
            "test_winner_but_validation_loser": {
                "validation": {
                    "auto_merge_false_positives": 0,
                    "auto_merge_recall_within_candidates": 0.60,
                    "assisted_recall_within_candidates": 0.75,
                    "human_review_pairs": 10,
                },
                "frozen_test": {"auto_merge_recall_within_candidates": 0.99},
            },
            "unsafe": {
                "validation": {
                    "auto_merge_false_positives": 1,
                    "auto_merge_recall_within_candidates": 0.95,
                    "assisted_recall_within_candidates": 0.99,
                    "human_review_pairs": 1,
                },
                "frozen_test": {"auto_merge_recall_within_candidates": 1.0},
            },
        }
        self.assertEqual(select_from_validation(models), "safe_validation_winner")


if __name__ == "__main__":
    unittest.main()
