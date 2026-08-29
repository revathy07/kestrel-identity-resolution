from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.modeling.fellegi_sunter import (
    FS_SCORE_COLUMNS,
    FellegiSunterError,
    apply_fs_model,
    estimate_fs_model,
)


LABEL_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
    "mct_score",
    "decision",
    "truth_label",
    "hard_negative_type",
    "partition",
]


def write_training(path: Path, *, invalid_partition: bool = False) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        for index in range(5):
            writer.writerow(
                {
                    "left_source": "a",
                    "left_record_ordinal": index + 1,
                    "left_source_record_id": f"A{index}",
                    "right_source": "b",
                    "right_record_ordinal": index + 1,
                    "right_source_record_id": f"B{index}",
                    "blocking_rules": "exact_email",
                    "positive_evidence": "exact_device_id;exact_email",
                    "conflicts": "",
                    "mct_score": "0.999999",
                    "decision": "auto_merge",
                    "truth_label": "match",
                    "hard_negative_type": "",
                    "partition": "validation" if invalid_partition and index == 0 else "development",
                }
            )
        for index in range(5, 10):
            writer.writerow(
                {
                    "left_source": "a",
                    "left_record_ordinal": index + 1,
                    "left_source_record_id": f"A{index}",
                    "right_source": "b",
                    "right_record_ordinal": index + 1,
                    "right_source_record_id": f"B{index}",
                    "blocking_rules": "exact_device_id",
                    "positive_evidence": "exact_device_id",
                    "conflicts": "name_conflict",
                    "mct_score": "0.000001",
                    "decision": "leave_separate",
                    "truth_label": "non_match",
                    "hard_negative_type": "common_name",
                    "partition": "development",
                }
            )


def write_features(path: Path) -> None:
    headers = [
        "left_source", "left_record_ordinal", "left_source_record_id",
        "right_source", "right_record_ordinal", "right_source_record_id",
        "blocking_rules", "positive_evidence", "conflicts", "mct_score", "decision",
    ]
    rows = [
        ("exact_device_id;exact_email", ""),
        ("exact_device_id", "name_conflict"),
        ("exact_device_id", ""),
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for index, (evidence, conflicts) in enumerate(rows, start=1):
            writer.writerow(
                {
                    "left_source": "a", "left_record_ordinal": index,
                    "left_source_record_id": f"A{index}",
                    "right_source": "b", "right_record_ordinal": index,
                    "right_source_record_id": f"B{index}",
                    "blocking_rules": "fixture",
                    "positive_evidence": evidence,
                    "conflicts": conflicts,
                    "mct_score": "0.123456",
                    "decision": "human_review",
                }
            )


class FellegiSunterTests(unittest.TestCase):
    def test_estimation_uses_development_events_not_heuristic_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            training = root / "development.csv.gz"
            write_training(training)
            model = estimate_fs_model(training, root / "model", show_progress=False)
            self.assertEqual(model["training_partition"], "development")
            self.assertEqual(model["training_match_rows"], 5)
            self.assertEqual(model["training_nonmatch_rows"], 5)
            self.assertGreater(
                model["events"]["evidence:exact_email"]["present_log2_likelihood_ratio"],
                0,
            )
            self.assertAlmostEqual(
                model["events"]["evidence:exact_device_id"]["present_log2_likelihood_ratio"],
                0.0,
            )
            self.assertLess(
                model["events"]["conflict:name_conflict"]["present_log2_likelihood_ratio"],
                0,
            )
            self.assertFalse(model["feature_contract"]["heuristic_mct_score_used"])
            self.assertFalse(model["feature_contract"]["heuristic_decision_used"])

    def test_training_rejects_non_development_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            training = root / "mixed.csv.gz"
            write_training(training, invalid_partition=True)
            with self.assertRaises(FellegiSunterError):
                estimate_fs_model(training, root / "model", show_progress=False)

    def test_frozen_model_scores_every_pair_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            training = root / "development.csv.gz"
            features = root / "features.csv.gz"
            write_training(training)
            write_features(features)
            model_dir = root / "model"
            estimate_fs_model(training, model_dir, show_progress=False)
            first_dir, second_dir = root / "first", root / "second"
            first = apply_fs_model(features, model_dir / "fs_model.json", first_dir, show_progress=False)
            second = apply_fs_model(features, model_dir / "fs_model.json", second_dir, show_progress=False)
            self.assertEqual(first["candidate_pairs_scored"], 3)
            self.assertEqual(first["decision_counts"]["auto_merge"], 1)
            self.assertEqual(first["decision_counts"]["leave_separate"], 2)
            self.assertFalse(first["phase_boundaries"]["evaluation_labels_read"])
            self.assertEqual(first["scored_output"]["sha256"], second["scored_output"]["sha256"])
            self.assertEqual(
                (first_dir / "fs_scored_candidate_pairs.csv.gz").read_bytes(),
                (second_dir / "fs_scored_candidate_pairs.csv.gz").read_bytes(),
            )
            with gzip.open(
                first_dir / "fs_scored_candidate_pairs.csv.gz",
                "rt",
                encoding="utf-8",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(set(rows[0]), set(FS_SCORE_COLUMNS))
            self.assertEqual([row["decision"] for row in rows], ["auto_merge", "leave_separate", "leave_separate"])
            self.assertNotEqual(rows[0]["mct_score"], "0.123456")
            json.loads((first_dir / "fs_manifest.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
