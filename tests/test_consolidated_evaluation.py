from __future__ import annotations

import unittest
from collections import Counter

from src.evaluation.consolidate_evaluation import (
    _empty_counter,
    _update,
    metrics,
    probability_metrics,
)


class ConsolidatedEvaluationTests(unittest.TestCase):
    def test_metrics_report_precision_and_recall_but_not_accuracy(self) -> None:
        counter = Counter(
            {
                "pairs": 10,
                "matches": 4,
                "nonmatches": 6,
                "auto_merge": 3,
                "auto_merge_match": 2,
                "auto_merge_nonmatch": 1,
                "human_review": 2,
                "human_review_match": 1,
                "human_review_nonmatch": 1,
                "leave_separate": 5,
                "leave_separate_match": 1,
                "leave_separate_nonmatch": 4,
            }
        )
        result = metrics(counter)
        self.assertAlmostEqual(result["auto_merge_precision"], 2 / 3)
        self.assertAlmostEqual(result["auto_merge_recall"], 1 / 2)
        self.assertAlmostEqual(result["assisted_recall"], 3 / 4)
        self.assertNotIn("accuracy", result)

    def test_counter_distinguishes_reviewed_and_separate_true_matches(self) -> None:
        counter = _empty_counter()
        _update(counter, {"truth_label": "match", "decision": "human_review"})
        _update(counter, {"truth_label": "match", "decision": "leave_separate"})
        _update(counter, {"truth_label": "non_match", "decision": "leave_separate"})
        result = metrics(counter)
        self.assertEqual(result["true_match_pairs"], 2)
        self.assertEqual(result["human_review_true_matches"], 1)
        self.assertEqual(result["leave_separate_true_matches"], 1)
        self.assertAlmostEqual(result["assisted_recall"], 0.5)

    def test_empty_auto_merge_denominator_is_explicitly_unavailable(self) -> None:
        result = metrics(_empty_counter())
        self.assertIsNone(result["auto_merge_precision"])
        self.assertIsNone(result["auto_merge_recall"])
        self.assertIsNone(result["assisted_recall"])

    def test_probability_metrics_are_measured_without_changing_scores(self) -> None:
        rows = [
            {"mct_score": "0.9", "truth_label": "match"},
            {"mct_score": "0.2", "truth_label": "non_match"},
        ]
        result = probability_metrics(rows)
        self.assertAlmostEqual(result["brier_score"], 0.025)
        self.assertGreater(result["log_loss"], 0.0)
        self.assertGreaterEqual(result["expected_calibration_error_10_bins"], 0.0)
        self.assertEqual(rows[0]["mct_score"], "0.9")


if __name__ == "__main__":
    unittest.main()
