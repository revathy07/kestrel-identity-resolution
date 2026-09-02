from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.business.estimate_customers import (
    automation_signals,
    latest_dense_window,
    parse_timestamp,
    score_bin_index,
    simulate_counts,
    unresolved_link_lower_sensitivity,
)


class BusinessEstimationTests(unittest.TestCase):
    def test_mixed_timestamp_formats_resolve_to_same_utc_instant(self) -> None:
        expected = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
        values = [
            "03-04-2026 12:00:00",
            "2026/04/03 12:00:00",
            "04-03-26 12:00",
            "2026-04-03T12:00:00Z",
            "1775217600000",
            "2026-04-03 17:30:00",
        ]
        self.assertEqual([parse_timestamp(value) for value in values], [expected] * len(values))

    def test_dense_window_uses_latest_qualifying_burst_not_largest_old_burst(self) -> None:
        origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
        old = [origin + timedelta(seconds=index) for index in range(20)]
        recent_origin = origin + timedelta(days=10)
        recent = [recent_origin + timedelta(seconds=index) for index in range(10)]
        start, end, count = latest_dense_window(
            [*old, *recent], window_seconds=60, minimum_count=10
        )
        self.assertGreaterEqual(start, recent_origin - timedelta(seconds=60))
        self.assertEqual(end, recent[-1])
        self.assertEqual(count, 10)

    def test_automation_requires_window_and_every_corroborating_condition(self) -> None:
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rule = {
            "required_missing_fields": ["phone", "dob"],
            "maximum_engagement": 6,
        }
        raw = {"phone": "", "dob": "null", "engagement_count": 3}
        signals = automation_signals(raw, rule, moment, (moment - timedelta(minutes=1), moment))
        self.assertIn("dense_timestamp_window", signals)
        self.assertIn("low_engagement", signals)
        self.assertEqual(automation_signals({**raw, "phone": "123"}, rule, moment, (moment, moment)), ())
        self.assertEqual(automation_signals(raw, rule, moment - timedelta(days=1), (moment, moment)), ())

    def test_score_bin_boundary_is_left_inclusive(self) -> None:
        boundaries = [0.0, 0.62, 0.7, 0.88]
        self.assertEqual(score_bin_index(0.0, boundaries), 0)
        self.assertEqual(score_bin_index(0.62, boundaries), 1)
        self.assertEqual(score_bin_index(0.7, boundaries), 2)

    def test_simulation_counts_transitive_overlap_once(self) -> None:
        calibration = [
            {"bin_index": 0, "posterior_alpha": 1_000_000.0, "posterior_beta": 0.5}
        ]
        edges = [
            {"left_cluster": "A", "right_cluster": "B", "bin_index": 0, "decision": "human_review"},
            {"left_cluster": "B", "right_cluster": "C", "bin_index": 0, "decision": "human_review"},
        ]
        rows = simulate_counts(
            edges, {"A": 1, "B": 1, "C": 1}, calibration,
            base_count=3, simulations=1, seed=7, maximum_records=12, scenario="review_only",
        )
        self.assertEqual(rows[0]["accepted_identity_reduction"], 2)
        self.assertEqual(rows[0]["estimated_identity_count"], 1)

    def test_simulation_gives_no_partial_reduction_to_oversized_component(self) -> None:
        calibration = [
            {"bin_index": 0, "posterior_alpha": 1_000_000.0, "posterior_beta": 0.5}
        ]
        edges = [
            {"left_cluster": "A", "right_cluster": "B", "bin_index": 0, "decision": "human_review"},
            {"left_cluster": "B", "right_cluster": "C", "bin_index": 0, "decision": "human_review"},
        ]
        rows = simulate_counts(
            edges, {"A": 6, "B": 6, "C": 1}, calibration,
            base_count=3, simulations=1, seed=7, maximum_records=12, scenario="review_only",
        )
        self.assertEqual(rows[0]["accepted_identity_reduction"], 0)
        self.assertEqual(rows[0]["oversized_sampled_components"], 1)
        self.assertEqual(rows[0]["estimated_identity_count"], 3)

    def test_lower_sensitivity_covers_every_unresolved_canonical_link_once(self) -> None:
        self.assertEqual(unresolved_link_lower_sensitivity(333_000, 23_656, 10_105), 299_239)
        with self.assertRaises(ValueError):
            unresolved_link_lower_sensitivity(100, -1, 2)


if __name__ == "__main__":
    unittest.main()
