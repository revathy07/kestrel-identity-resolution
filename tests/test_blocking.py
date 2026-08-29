from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.blocking.generate_candidates import CANDIDATE_COLUMNS, generate_candidates
from src.blocking.rules import DEFAULT_RULES, derive_candidate_keys, load_blocking_rules
from src.evaluation.evaluate_blocking import evaluate_blocking
from src.normalization.normalize_identifiers import normalize_identifiers
from tests.test_profiling import make_fixture


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class BlockingRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_blocking_rules(DEFAULT_RULES)

    def test_rule2_boundary_is_strictly_greater_than_40(self) -> None:
        values = {"email": {"same@example.test"}}
        at_40 = derive_candidate_keys(values, {("email", "same@example.test"): 40}, self.rules)
        at_41 = derive_candidate_keys(values, {("email", "same@example.test"): 41}, self.rules)
        self.assertIn(("exact_email", "same@example.test"), at_40)
        self.assertNotIn(("exact_email", "same@example.test"), at_41)

    def test_discovery_bridges_do_not_change_normalized_values(self) -> None:
        values = {
            "email": {"a.b+tag@example.test"},
            "phone": {"+999123456789"},
            "account_reference": {"000123"},
            "first_name": {"Ada"},
            "last_name": {"Lovelace"},
            "city": {"Metro City"},
        }
        frequencies = {(concept, value): 2 for concept, items in values.items() for value in items}
        keys = derive_candidate_keys(values, frequencies, self.rules)
        self.assertIn(("email_skeleton", "ab@example.test"), keys)
        self.assertIn(("phone_suffix_9", "123456789"), keys)
        self.assertIn(("numeric_account_reference", "123"), keys)
        self.assertIn(("name_city", "adalovelace\x1fmetrocity"), keys)
        self.assertEqual(values["email"], {"a.b+tag@example.test"})


class BlockingPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.data_dir = cls.root / "data"
        cls.normalization_dir = cls.root / "normalization"
        cls.output_dir = cls.root / "blocking"
        make_fixture(cls.data_dir)
        normalize_identifiers(cls.data_dir, cls.normalization_dir, show_progress=False)
        cls.manifest = generate_candidates(
            cls.normalization_dir / "normalized_identifiers.csv.gz",
            cls.output_dir,
            show_progress=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_candidate_generation_is_truth_independent_and_stops_before_scoring(self) -> None:
        self.assertEqual(self.manifest["total_source_records"], 44)
        self.assertGreater(self.manifest["unique_candidate_pairs"], 0)
        self.assertEqual(
            self.manifest["phase_boundaries"],
            {
                "candidate_pairs_created": True,
                "match_scores_calculated": False,
                "match_decisions_made": False,
                "clusters_formed": False,
                "evaluation_labels_read": False,
            },
        )
        production_source = (Path("src/blocking/generate_candidates.py")).read_text(encoding="utf-8")
        for forbidden in ("person_map.csv", "canonical_duplicate_links.jsonl", "hard_negatives.json"):
            self.assertNotIn(forbidden, production_source)

    def test_candidate_rows_are_unique_ordered_and_traceable(self) -> None:
        rows = read_gzip_csv(self.output_dir / "candidate_pairs.csv.gz")
        self.assertEqual(len(rows), self.manifest["unique_candidate_pairs"])
        self.assertEqual(set(rows[0]), set(CANDIDATE_COLUMNS))
        identities = [
            (
                row["left_source"],
                int(row["left_record_ordinal"]),
                row["right_source"],
                int(row["right_record_ordinal"]),
            )
            for row in rows
        ]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(int(row["blocking_rule_count"]) >= 1 for row in rows))

    def test_compact_outputs_and_internal_registry_exist(self) -> None:
        expected = {
            "candidate_pairs.csv.gz",
            "blocking_rule_summary.csv",
            "normalized_rule2_registry.json",
            "normalized_rule2_values.csv",
            "candidate_manifest.json",
            "blocking_report.md",
        }
        self.assertTrue(expected.issubset({path.name for path in self.output_dir.iterdir()}))
        public_text = (self.output_dir / "normalized_rule2_values.csv").read_text(encoding="utf-8")
        self.assertNotIn("normalized_value", public_text.splitlines()[0])

    def test_candidate_output_is_deterministic(self) -> None:
        second_output = self.root / "blocking-second"
        second_manifest = generate_candidates(
            self.normalization_dir / "normalized_identifiers.csv.gz",
            second_output,
            show_progress=False,
        )
        self.assertEqual(
            self.manifest["candidate_output"]["sha256"],
            second_manifest["candidate_output"]["sha256"],
        )
        self.assertEqual(
            (self.output_dir / "candidate_pairs.csv.gz").read_bytes(),
            (second_output / "candidate_pairs.csv.gz").read_bytes(),
        )


class BlockingEvaluationTests(unittest.TestCase):
    def test_recall_is_measured_after_generation_without_affecting_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates.csv.gz"
            with gzip.open(candidates, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=CANDIDATE_COLUMNS)
                writer.writeheader()
                writer.writerow(
                    {
                        "left_source": "a",
                        "left_record_ordinal": 1,
                        "left_source_record_id": "A1",
                        "right_source": "b",
                        "right_record_ordinal": 1,
                        "right_source_record_id": "B1",
                        "blocking_rules": "exact_email",
                        "blocking_rule_count": 1,
                    }
                )
            canonical = root / "canonical.jsonl"
            canonical.write_text(
                "\n".join(
                    json.dumps(item)
                    for item in (
                        {
                            "source_system_a": "a", "source_record_id_a": "A1",
                            "source_system_b": "b", "source_record_id_b": "B1",
                            "evidence_modes": ["exact_email"], "intended_recoverability": True,
                        },
                        {
                            "source_system_a": "a", "source_record_id_a": "A2",
                            "source_system_b": "b", "source_record_id_b": "B2",
                            "evidence_modes": ["no_usable_evidence"], "intended_recoverability": False,
                        },
                    )
                ) + "\n",
                encoding="utf-8",
            )
            hard = root / "hard.json"
            hard.write_text(
                json.dumps([
                    {"type": "shared_email", "source_records": [
                        {"system": "a", "record_id": "A1"},
                        {"system": "b", "record_id": "B1"},
                    ]}
                ]),
                encoding="utf-8",
            )
            result = evaluate_blocking(candidates, canonical, hard, root / "evaluation")
            summary = result["canonical_link_evaluation"]
            self.assertEqual(summary["canonical_true_links"], 2)
            self.assertEqual(summary["retained_true_links"], 1)
            self.assertEqual(summary["discarded_true_links_before_scoring"], 1)
            self.assertEqual(summary["recoverable_blocking_recall"], 1.0)
            self.assertFalse(result["isolation"]["labels_used_as_blocking_features"])


if __name__ == "__main__":
    unittest.main()
