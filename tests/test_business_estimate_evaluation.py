import unittest

from src.evaluation.evaluate_business_estimate import (
    BusinessEstimateEvaluationError,
    evaluate_classifications,
)


class BusinessEstimateEvaluationTests(unittest.TestCase):
    def test_automation_precision_recall_and_conservative_cluster_action(self):
        truth = {
            ("s", "1"): ("B1", "bot"),
            ("s", "2"): ("B1", "bot"),
            ("s", "3"): ("H1", "human"),
            ("s", "4"): ("H2", "human"),
        }
        rows = [
            {"source": "s", "source_record_id": "1", "final_cluster_id": "c1", "observable_policy": "automation"},
            {"source": "s", "source_record_id": "2", "final_cluster_id": "c1", "observable_policy": "automation"},
            {"source": "s", "source_record_id": "3", "final_cluster_id": "c2", "observable_policy": "automation"},
            {"source": "s", "source_record_id": "4", "final_cluster_id": "c2", "observable_policy": "none"},
        ]
        result = evaluate_classifications(truth, rows)
        metrics = result["automation_record_metrics"]
        self.assertEqual(metrics["precision"], 2 / 3)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(result["automation_cluster_metrics"]["excluded_clusters"], 1)
        self.assertEqual(result["mixed_policy_clusters_retained"], 1)

    def test_qa_is_reported_as_policy_not_an_independent_truth_class(self):
        truth = {("s", "1"): ("H1", "human")}
        rows = [
            {"source": "s", "source_record_id": "1", "final_cluster_id": "c1", "observable_policy": "internal_qa"}
        ]
        result = evaluate_classifications(truth, rows)
        audit = result["internal_qa_policy_audit"]
        self.assertEqual(audit["distinct_human_entities_excluded"], 1)
        self.assertIn("no independent QA label", audit["note"])

    def test_missing_truth_row_is_rejected(self):
        with self.assertRaises(BusinessEstimateEvaluationError):
            evaluate_classifications(
                {},
                [{"source": "s", "source_record_id": "1", "final_cluster_id": "c", "observable_policy": "none"}],
            )


if __name__ == "__main__":
    unittest.main()
