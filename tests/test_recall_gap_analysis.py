from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.evaluation.analyze_recall_gaps import (
    REQUIRED_COLUMNS,
    RecallGapAnalysisError,
    _read_partition,
    _score_band,
    analyze_recall_gaps,
    recall_metrics,
)


class RecallGapAnalysisTests(unittest.TestCase):
    def _write_labels(
        self, path: Path, partition: str, rows: list[dict[str, str]]
    ) -> None:
        headers = sorted(REQUIRED_COLUMNS | {"left_source_record_id", "right_source_record_id"})
        with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for index, values in enumerate(rows):
                row = {
                    "left_source": "app_users",
                    "right_source": "ticketing",
                    "left_source_record_id": f"LEFT-SECRET-{index}",
                    "right_source_record_id": f"RIGHT-SECRET-{index}",
                    "blocking_rules": "name_city",
                    "positive_evidence": "name_city",
                    "conflicts": "email_conflict",
                    "mct_score": "0.85",
                    "decision": "human_review",
                    "truth_label": "match",
                    "partition": partition,
                }
                row.update(values)
                writer.writerow(row)

    def test_metrics_separate_automatic_assisted_and_residual_recall(self) -> None:
        rows = [
            {"truth_label": "match", "decision": "auto_merge"},
            {"truth_label": "match", "decision": "human_review"},
            {"truth_label": "match", "decision": "leave_separate"},
            {"truth_label": "non_match", "decision": "leave_separate"},
        ]
        result = recall_metrics(rows)
        self.assertEqual(result["true_match_pairs"], 3)
        self.assertAlmostEqual(result["auto_recall"], 1 / 3)
        self.assertAlmostEqual(result["assisted_recall"], 2 / 3)
        self.assertAlmostEqual(result["review_recall_gain"], 1 / 3)
        self.assertAlmostEqual(result["residual_recall_gap"], 1 / 3)
        self.assertNotIn("accuracy", result)

    def test_analysis_reads_only_development_and_validation_and_emits_aggregates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labelled = root / "labels"
            output = root / "analysis"
            labelled.mkdir()
            self._write_labels(
                labelled / "labelled_development_set.csv.gz",
                "development",
                [
                    {"decision": "auto_merge", "mct_score": "0.95"},
                    {"decision": "human_review", "mct_score": "0.85"},
                    {"decision": "leave_separate", "mct_score": "0.58"},
                    {
                        "truth_label": "non_match",
                        "decision": "human_review",
                        "mct_score": "0.70",
                    },
                ],
            )
            self._write_labels(
                labelled / "labelled_validation_set.csv.gz",
                "validation",
                [{"decision": "auto_merge", "mct_score": "0.97"}],
            )
            # A deliberately invalid test artifact proves the analyzer never attempts to read it.
            (labelled / "labelled_test_set.csv.gz").write_text(
                "FROZEN-TEST-SECRET", encoding="utf-8"
            )
            config = root / "mct.json"
            config.write_text(
                json.dumps(
                    {
                        "thresholds": {
                            "auto_merge_minimum": 0.88,
                            "human_review_minimum": 0.62,
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = analyze_recall_gaps(labelled, output, config)

            self.assertEqual(result["partitions_read"], ["development", "validation"])
            self.assertFalse(result["frozen_test_read"])
            self.assertEqual(result["metrics"]["combined"]["true_match_pairs"], 4)
            self.assertAlmostEqual(result["metrics"]["combined"]["auto_recall"], 0.5)
            emitted = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.iterdir()
                if path.suffix in {".json", ".csv", ".md"}
            )
            self.assertNotIn("LEFT-SECRET", emitted)
            self.assertNotIn("RIGHT-SECRET", emitted)
            self.assertNotIn("FROZEN-TEST-SECRET", emitted)

    def test_partition_reader_rejects_a_test_or_mislabeled_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "labels.csv.gz"
            self._write_labels(path, "test", [{}])
            with self.assertRaisesRegex(RecallGapAnalysisError, "permits only"):
                _read_partition(path, "test")
            with self.assertRaisesRegex(RecallGapAnalysisError, "not 'development'"):
                _read_partition(path, "development")

    def test_diagnostic_score_bands_match_mandatory_boundaries(self) -> None:
        self.assertEqual(_score_band(0.619999), "0.55-0.62 (near review)")
        self.assertEqual(_score_band(0.62), "0.62-0.80 (review)")
        self.assertEqual(_score_band(0.879999), "0.84-0.88 (near auto)")
        self.assertEqual(_score_band(0.88), "0.88-1.00 (auto)")
        self.assertEqual(_score_band(1.0), "0.88-1.00 (auto)")


if __name__ == "__main__":
    unittest.main()
