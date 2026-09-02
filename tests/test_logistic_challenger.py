from __future__ import annotations

import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.modeling.logistic_challenger import (
    LogisticChallengerError,
    _binary_metrics,
    apply_model,
    encode_rows,
    feature_names,
    load_config,
    select_on_validation,
    train_candidates,
)


LABEL_COLUMNS = [
    "left_source", "left_record_ordinal", "left_source_record_id",
    "right_source", "right_record_ordinal", "right_source_record_id",
    "blocking_rules", "positive_evidence", "conflicts", "mct_score", "decision",
    "truth_label", "hard_negative_type", "partition",
]
PAIR_COLUMNS = LABEL_COLUMNS[:9] + ["mct_score", "decision"]
CONFIG_PATH = Path("config/logistic_challenger.yaml")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_labels(path: Path, partition: str, *, mixed_partition: bool = False) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        for index in range(12):
            is_match = index < 6
            writer.writerow(
                {
                    "left_source": "a",
                    "left_record_ordinal": index + 1,
                    "left_source_record_id": f"A{index}",
                    "right_source": "b",
                    "right_record_ordinal": index + 1,
                    "right_source_record_id": f"B{index}",
                    "blocking_rules": "fixture",
                    "positive_evidence": "exact_email;exact_phone" if is_match else "exact_device_id",
                    "conflicts": "" if is_match else "name_conflict",
                    "mct_score": "0.95" if is_match else "0.10",
                    "decision": "auto_merge" if is_match else "leave_separate",
                    "truth_label": "match" if is_match else "non_match",
                    "hard_negative_type": "" if is_match else "fixture_negative",
                    "partition": "validation" if mixed_partition and index == 0 else partition,
                }
            )


def write_pair_features(path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_COLUMNS)
        writer.writeheader()
        for index, (evidence, conflicts) in enumerate(
            [("exact_email;exact_phone", ""), ("exact_device_id", "name_conflict")],
            start=1,
        ):
            writer.writerow(
                {
                    "left_source": "a", "left_record_ordinal": index,
                    "left_source_record_id": f"A{index}",
                    "right_source": "b", "right_record_ordinal": index,
                    "right_source_record_id": f"B{index}",
                    "blocking_rules": "fixture", "positive_evidence": evidence,
                    "conflicts": conflicts, "mct_score": "0.50", "decision": "human_review",
                }
            )


class LogisticChallengerTests(unittest.TestCase):
    def test_evaluation_uses_the_same_six_decimal_boundary_as_scoring(self) -> None:
        metrics = _binary_metrics(
            np.asarray([1.0, 1.0]),
            np.asarray([0.8799996, 0.6199996]),
        )
        self.assertEqual(metrics["auto_merge_pairs"], 1)
        self.assertEqual(metrics["human_review_pairs"], 1)

    def test_encoding_contains_every_declared_pairwise_interaction(self) -> None:
        config = load_config(CONFIG_PATH)
        rows = [{"positive_evidence": "exact_email;exact_phone", "conflicts": "name_conflict"}]
        matrix = encode_rows(rows, config)
        names = feature_names(config)
        self.assertEqual(matrix.shape, (1, 190))
        self.assertEqual(len(names), 190)
        self.assertEqual(matrix[0, names.index("evidence:exact_email")], 1.0)
        interaction = "conflict:name_conflict & evidence:exact_email"
        self.assertEqual(matrix[0, names.index(interaction)], 1.0)
        absent = "conflict:email_conflict & evidence:exact_email"
        self.assertEqual(matrix[0, names.index(absent)], 0.0)

    def test_training_rejects_any_non_development_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = root / "mixed.csv.gz"
            write_labels(labels, "development", mixed_partition=True)
            with self.assertRaises(LogisticChallengerError):
                train_candidates(labels, root / "output", show_progress=False)

    def test_training_is_deterministic_and_excludes_forbidden_features(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = root / "development.csv.gz"
            write_labels(labels, "development")
            first = train_candidates(labels, root / "first", show_progress=False)
            second = train_candidates(labels, root / "second", show_progress=False)
            self.assertEqual(first["candidates"], second["candidates"])
            self.assertEqual(first["feature_count"], 190)
            self.assertFalse(first["feature_contract"]["heuristic_mct_score_used"])
            self.assertFalse(first["feature_contract"]["record_identity_used"])

    def test_validation_selects_only_zero_false_auto_merge_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            validation = root / "validation.csv.gz"
            candidates_path = root / "candidates.json"
            write_labels(validation, "validation")
            config = load_config(CONFIG_PATH)
            names = feature_names(config)
            safe = {name: 0.0 for name in names}
            safe["evidence:exact_email"] = 6.0
            safe["conflict:name_conflict"] = -6.0
            unsafe = dict(safe)
            unsafe["evidence:exact_device_id"] = 12.0
            candidates_path.write_text(
                json.dumps(
                    {
                        "training_partition": "development",
                        "feature_names": names,
                        "configuration": {"sha256": sha256(CONFIG_PATH)},
                        "input": {"sha256": "fixture-development"},
                        "feature_contract": {"validation_or_test_labels_used": False},
                        "candidates": [
                            {"candidate_id": "safe", "l2_strength": 0.1, "intercept": -3.0, "coefficients": safe},
                            {"candidate_id": "unsafe", "l2_strength": 0.0001, "intercept": -3.0, "coefficients": unsafe},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = select_on_validation(
                validation, candidates_path, root / "output", show_progress=False
            )
            self.assertEqual(result["selected_candidate"]["candidate_id"], "safe")
            by_id = {item["candidate_id"]: item for item in result["candidate_validation_metrics"]}
            self.assertTrue(by_id["safe"]["passes_zero_false_auto_merge_gate"])
            self.assertFalse(by_id["unsafe"]["passes_zero_false_auto_merge_gate"])
            self.assertEqual(result["frozen_test_status"], "not opened by logistic challenger")

    def test_frozen_model_scores_truth_free_pairs_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            features = root / "features.csv.gz"
            model_path = root / "model.json"
            write_pair_features(features)
            config = load_config(CONFIG_PATH)
            names = feature_names(config)
            coefficients = {name: 0.0 for name in names}
            coefficients["evidence:exact_email"] = 6.0
            coefficients["conflict:name_conflict"] = -6.0
            model_path.write_text(
                json.dumps(
                    {
                        "feature_names": names,
                        "coefficients": coefficients,
                        "intercept": -3.0,
                        "configuration_sha256": sha256(CONFIG_PATH),
                        "frozen_test_labels_used": False,
                    }
                ),
                encoding="utf-8",
            )
            first = apply_model(features, model_path, root / "first", show_progress=False)
            second = apply_model(features, model_path, root / "second", show_progress=False)
            self.assertEqual(first["candidate_pairs_scored"], 2)
            self.assertEqual(first["decision_counts"]["auto_merge"], 1)
            self.assertEqual(first["decision_counts"]["leave_separate"], 1)
            self.assertFalse(first["phase_boundaries"]["evaluation_labels_read"])
            self.assertEqual(first["scored_output"]["sha256"], second["scored_output"]["sha256"])
            with gzip.open(
                root / "first" / "logistic_scored_candidate_pairs.csv.gz",
                "rt", encoding="utf-8", newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertNotEqual(rows[0]["mct_score"], "0.50")
            self.assertEqual([row["decision"] for row in rows], ["auto_merge", "leave_separate"])


if __name__ == "__main__":
    unittest.main()
