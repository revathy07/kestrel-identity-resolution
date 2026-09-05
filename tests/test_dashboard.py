from __future__ import annotations

import unittest

from dashboard.data_loader import (
    ARTIFACTS,
    DashboardDataError,
    PROJECT_ROOT,
    load_dashboard_data,
    score_selected_model,
)


class DashboardDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = load_dashboard_data(PROJECT_ROOT)

    def test_dashboard_uses_only_aggregate_allowlisted_artifacts(self) -> None:
        paths = {path.as_posix() for path in ARTIFACTS.values()}
        self.assertTrue(all(path.startswith("outputs/") for path in paths))
        self.assertFalse(any("person_map" in path for path in paths))
        self.assertFalse(any(path.endswith(".gz") for path in paths))
        self.assertFalse(self.snapshot["meta"]["row_level_data_loaded"])

    def test_executive_counts_and_range_reconcile(self) -> None:
        executive = self.snapshot["executive"]
        self.assertEqual(sum(row["records"] for row in self.snapshot["sources"]), 420_000)
        self.assertEqual(sum(row["pairs"] for row in self.snapshot["decisions"]), 204_547)
        self.assertEqual(executive["operational_identities"], 342_900)
        self.assertEqual(executive["recommended_customers"], 315_177)
        self.assertLessEqual(executive["range_lower"], executive["recommended_customers"])
        self.assertLessEqual(executive["recommended_customers"], executive["range_upper"])

    def test_selected_model_score_is_deterministic_and_uses_fixed_bands(self) -> None:
        model = self.snapshot["selected_model"]
        events = ["evidence:exact_email", "evidence:exact_phone"]
        first = score_selected_model(model, events)
        second = score_selected_model(model, reversed(events))
        self.assertEqual(first, second)
        self.assertEqual(first["score"], 0.927095)
        self.assertEqual(first["decision"], "auto_merge")
        self.assertEqual(model["thresholds"]["auto_merge_minimum"], 0.88)
        self.assertEqual(model["thresholds"]["human_review_minimum"], 0.62)

    def test_decision_lab_rejects_unknown_features(self) -> None:
        with self.assertRaises(DashboardDataError):
            score_selected_model(self.snapshot["selected_model"], ["person_id"])


class DashboardSmokeTests(unittest.TestCase):
    def test_all_dashboard_views_render_without_exceptions(self) -> None:
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError as exc:  # pragma: no cover - installation contract
            self.fail(f"Pinned Streamlit dependency is unavailable: {exc}")
        app = AppTest.from_file(str(PROJECT_ROOT / "dashboard" / "app.py"), default_timeout=30)
        app.run()
        self.assertEqual(list(app.exception), [])
        for view in ["Technical audit", "MCT decision lab", "Methods & limits"]:
            app.sidebar.radio[0].set_value(view)
            app.run()
            self.assertEqual(list(app.exception), [], view)


if __name__ == "__main__":
    unittest.main()
