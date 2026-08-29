from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from src.blocking.generate_candidates import generate_candidates
from src.evaluation.evaluate_scoring import evaluate_scoring
from src.normalization.normalize_identifiers import normalize_identifiers
from src.scoring.rules import DEFAULT_RULES, ScoringRecord, load_scoring_rules, score_pair
from src.scoring.score_candidates import SCORE_COLUMNS, score_candidates
from tests.test_profiling import make_fixture


def record(
    source: str,
    ordinal: int,
    record_id: str,
    values: dict[str, set[str]],
    *,
    verified_emails: set[str] | None = None,
) -> ScoringRecord:
    roles: dict[tuple[str, str], set[str]] = defaultdict(set)
    for email in verified_emails or set():
        roles[("email", email)].add("verified_identifier")
    return ScoringRecord(source, ordinal, record_id, values, roles)


class MCTRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_scoring_rules(DEFAULT_RULES)

    def test_assessment_thresholds_are_exact(self) -> None:
        self.assertEqual(self.rules["thresholds"]["auto_merge_minimum"], 0.88)
        self.assertEqual(self.rules["thresholds"]["human_review_minimum"], 0.62)

    def test_verified_email_can_auto_merge_but_ordinary_email_is_review(self) -> None:
        email = "ada@example.test"
        left = record("app", 1, "1", {"email": {email}})
        right = record("social", 1, "2", {"email": {email}}, verified_emails={email})
        verified = score_pair(left, right, set(), self.rules)
        ordinary = score_pair(left, record("store", 1, "3", {"email": {email}}), set(), self.rules)
        self.assertEqual(verified.mct_score, 0.90)
        self.assertEqual(verified.decision, "auto_merge")
        self.assertEqual(ordinary.mct_score, 0.82)
        self.assertEqual(ordinary.decision, "human_review")

    def test_rule2_value_contributes_zero_positive_or_negative_weight(self) -> None:
        email = "shared@example.test"
        left = record("a", 1, "1", {"email": {email}})
        right = record("b", 1, "2", {"email": {email}})
        result = score_pair(left, right, {("email", email)}, self.rules)
        self.assertEqual(result.mct_score, 0.0)
        self.assertEqual(result.evidence, ())
        self.assertEqual(result.conflicts, ())
        self.assertEqual(result.decision, "leave_separate")

    def test_correlated_email_features_are_not_double_counted(self) -> None:
        email = "a.b+tag@example.test"
        left = record("a", 1, "1", {"email": {email}})
        right = record("b", 1, "2", {"email": {email}})
        result = score_pair(left, right, set(), self.rules)
        self.assertEqual(result.evidence, ("exact_email",))
        self.assertEqual(result.family_strengths, (("email", 0.82),))

    def test_household_email_and_payment_with_name_conflict_stays_review(self) -> None:
        shared = "household@example.test"
        left = record(
            "subscriptions", 1, "1",
            {"email": {shared}, "payment_token": {"token"}, "full_name": {"Ada One"}},
        )
        right = record(
            "subscriptions", 2, "2",
            {"email": {shared}, "payment_token": {"token"}, "full_name": {"Bob Two"}},
        )
        result = score_pair(left, right, set(), self.rules)
        self.assertIn("name_conflict", result.conflicts)
        self.assertEqual(result.decision, "human_review")
        self.assertLess(result.mct_score, 0.88)

    def test_household_email_and_payment_without_third_family_is_capped_for_review(self) -> None:
        shared = "household@example.test"
        left = record("subscriptions", 1, "1", {"email": {shared}, "payment_token": {"token"}})
        right = record("subscriptions", 2, "2", {"email": {shared}, "payment_token": {"token"}})
        result = score_pair(left, right, set(), self.rules)
        self.assertIn("shared_email_payment_household_risk", result.conflicts)
        self.assertEqual(result.mct_score, 0.87)
        self.assertEqual(result.decision, "human_review")

    def test_multiple_identity_conflicts_force_separation(self) -> None:
        left = record(
            "a", 1, "1",
            {"email": {"shared@example.test"}, "phone": {"111111111"}, "date_of_birth": {"1980-01-01"}},
        )
        right = record(
            "b", 1, "2",
            {"email": {"shared@example.test"}, "phone": {"222222222"}, "date_of_birth": {"1990-01-01"}},
        )
        result = score_pair(left, right, set(), self.rules)
        self.assertEqual(result.decision, "human_review")
        self.assertEqual(result.mct_score, 0.62)

    def test_verified_email_conflict_disqualifies_review_floor(self) -> None:
        left = record(
            "social", 1, "1", {"email": {"shared@example.test", "left@example.test"}},
            verified_emails={"left@example.test"},
        )
        right = record(
            "social", 2, "2", {"email": {"shared@example.test", "right@example.test"}},
            verified_emails={"right@example.test"},
        )
        result = score_pair(left, right, set(), self.rules)
        self.assertIn("verified_email_conflict", result.conflicts)
        self.assertEqual(result.decision, "leave_separate")
        self.assertLess(result.mct_score, 0.62)


class MCTPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.data_dir = cls.root / "data"
        cls.normalization_dir = cls.root / "normalization"
        cls.blocking_dir = cls.root / "blocking"
        cls.scoring_dir = cls.root / "scoring"
        make_fixture(cls.data_dir)
        normalize_identifiers(cls.data_dir, cls.normalization_dir, show_progress=False)
        cls.blocking_manifest = generate_candidates(
            cls.normalization_dir / "normalized_identifiers.csv.gz",
            cls.blocking_dir,
            show_progress=False,
        )
        cls.manifest = score_candidates(
            cls.normalization_dir / "normalized_identifiers.csv.gz",
            cls.blocking_dir / "candidate_pairs.csv.gz",
            cls.blocking_dir / "normalized_rule2_registry.json",
            cls.scoring_dir,
            show_progress=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_every_candidate_is_scored_and_phase_boundary_is_explicit(self) -> None:
        self.assertEqual(
            self.manifest["candidate_pairs_scored"],
            self.blocking_manifest["unique_candidate_pairs"],
        )
        self.assertEqual(sum(self.manifest["decision_counts"].values()), self.manifest["candidate_pairs_scored"])
        self.assertTrue(self.manifest["phase_boundaries"]["mct_decision_bands_assigned"])
        self.assertFalse(self.manifest["phase_boundaries"]["evaluation_labels_read"])
        self.assertFalse(self.manifest["phase_boundaries"]["clusters_formed"])

    def test_scored_rows_have_required_explanations(self) -> None:
        with gzip.open(
            self.scoring_dir / "scored_candidate_pairs.csv.gz",
            "rt",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), self.manifest["candidate_pairs_scored"])
        self.assertEqual(set(rows[0]), set(SCORE_COLUMNS))
        self.assertTrue(all(0 <= float(row["mct_score"]) <= 1 for row in rows))
        self.assertTrue(all(row["decision"] in {"auto_merge", "human_review", "leave_separate"} for row in rows))

    def test_production_scorer_has_no_label_dependency(self) -> None:
        source = Path("src/scoring/score_candidates.py").read_text(encoding="utf-8")
        for forbidden in (
            "person_map.csv",
            "canonical_duplicate_links.jsonl",
            "hard_negatives.json",
            "person_id",
            "truth_key",
            "scenario_type",
            "evidence_mode",
        ):
            self.assertNotIn(forbidden, source)

    def test_scored_output_is_deterministic(self) -> None:
        second_output = self.root / "scoring-second"
        second = score_candidates(
            self.normalization_dir / "normalized_identifiers.csv.gz",
            self.blocking_dir / "candidate_pairs.csv.gz",
            self.blocking_dir / "normalized_rule2_registry.json",
            second_output,
            show_progress=False,
        )
        self.assertEqual(
            self.manifest["scored_output"]["sha256"],
            second["scored_output"]["sha256"],
        )
        self.assertEqual(
            (self.scoring_dir / "scored_candidate_pairs.csv.gz").read_bytes(),
            (second_output / "scored_candidate_pairs.csv.gz").read_bytes(),
        )


class MCTEvaluationTests(unittest.TestCase):
    def test_person_disjoint_development_validation_and_test_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scored = root / "scored.csv.gz"
            base = {
                "blocking_rules": "exact_email",
                "positive_evidence": "exact_verified_email",
                "evidence_family_count": "1",
                "conflicts": "",
                "positive_score": "0.900000",
                "conflict_penalty": "0.000000",
                "mct_score": "0.900000",
                "decision": "auto_merge",
            }
            with gzip.open(scored, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=SCORE_COLUMNS)
                writer.writeheader()
                writer.writerow(
                    {
                        **base,
                        "left_source": "a", "left_record_ordinal": 1, "left_source_record_id": "A1",
                        "right_source": "b", "right_record_ordinal": 1, "right_source_record_id": "B1",
                    }
                )
                writer.writerow(
                    {
                        **base,
                        "left_source": "a", "left_record_ordinal": 2, "left_source_record_id": "A2",
                        "right_source": "b", "right_record_ordinal": 2, "right_source_record_id": "B2",
                    }
                )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "phase_boundaries": {"evaluation_labels_read": False},
                        "inputs": {"configuration": {"sha256": "frozen-config"}},
                    }
                ),
                encoding="utf-8",
            )
            truth = root / "person_map.csv"
            truth.write_text(
                "system,record_id,person_id,entity_type\n"
                "a,A1,P1,human\n"
                "a,A2,P2,human\n"
                "a,A3,P4,human\n"
                "b,B1,P1,human\n"
                "b,B2,P3,human\n"
                "b,B3,P5,human\n",
                encoding="utf-8",
            )
            canonical = root / "canonical.jsonl"
            canonical.write_text(
                json.dumps(
                    {
                        "source_system_a": "a", "source_record_id_a": "A1",
                        "source_system_b": "b", "source_record_id_b": "B1",
                        "intended_recoverability": True,
                    }
                ) + "\n",
                encoding="utf-8",
            )
            hard = root / "hard.json"
            hard.write_text(
                json.dumps(
                    [
                        {
                            "type": "shared_email",
                            "source_records": [
                                {"system": "a", "record_id": "A2"},
                                {"system": "b", "record_id": "B2"},
                            ],
                        },
                        {
                            "type": "blocked_family_case",
                            "source_records": [
                                {"system": "a", "record_id": "A3"},
                                {"system": "b", "record_id": "B3"},
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            development_dir = root / "development"
            development = evaluate_scoring(
                scored, manifest, truth, canonical, hard, development_dir, scope="development"
            )
            self.assertEqual(set(development["pair_metrics_by_partition"]), {"development"})
            self.assertTrue((development_dir / "labelled_development_set.csv.gz").exists())
            self.assertFalse((development_dir / "labelled_validation_set.csv.gz").exists())
            self.assertFalse((development_dir / "labelled_test_set.csv.gz").exists())

            validation_dir = root / "validation"
            validation = evaluate_scoring(
                scored, manifest, truth, canonical, hard, validation_dir, scope="validation"
            )
            self.assertEqual(
                set(validation["pair_metrics_by_partition"]),
                {"development", "validation"},
            )
            self.assertTrue((validation_dir / "labelled_validation_set.csv.gz").exists())
            self.assertFalse((validation_dir / "labelled_test_set.csv.gz").exists())

            final_dir = root / "final"
            final = evaluate_scoring(scored, manifest, truth, canonical, hard, final_dir, scope="final")
            self.assertEqual(
                set(final["pair_metrics_by_partition"]),
                {"development", "validation", "test"},
            )
            metrics = list(final["pair_metrics_by_partition"].values())
            self.assertEqual(sum(item["candidate_pairs"] for item in metrics), 2)
            self.assertEqual(sum(item["auto_merge_true_positives"] for item in metrics), 1)
            self.assertEqual(sum(item["auto_merge_false_positives"] for item in metrics), 1)
            self.assertEqual(final["canonical_link_metrics"]["auto_merge"], 1)
            self.assertEqual(final["hard_negative_metrics"]["overall"]["pairs"], 2)
            self.assertEqual(final["hard_negative_metrics"]["overall"]["auto_merge"], 1)
            self.assertEqual(final["hard_negative_metrics"]["overall"]["blocked"], 1)
            self.assertTrue(final["partition_policy"]["person_disjoint"])
            self.assertEqual(
                final["partition_isolation"]["person_overlap_across_model_partitions"], 0
            )
            self.assertTrue(
                final["partition_isolation"]["all_scored_candidate_pairs_retained"]
            )
            self.assertEqual(
                sum(final["partition_isolation"]["candidate_pairs_by_partition"].values()),
                2,
            )

            person_by_record = {
                "A1": "P1", "B1": "P1", "A2": "P2", "B2": "P3",
                "A3": "P4", "B3": "P5",
            }
            people_by_partition: dict[str, set[str]] = {}
            for partition in ("development", "validation", "test"):
                path = final_dir / f"labelled_{partition}_set.csv.gz"
                with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    self.assertNotIn("person_id", reader.fieldnames or [])
                    people_by_partition[partition] = {
                        person_by_record[record_id]
                        for row in reader
                        for record_id in (
                            row["left_source_record_id"],
                            row["right_source_record_id"],
                        )
                    }
            for index, left in enumerate(("development", "validation", "test")):
                for right in ("development", "validation", "test")[index + 1 :]:
                    self.assertFalse(people_by_partition[left] & people_by_partition[right])
            self.assertTrue(final["isolation"]["scores_created_before_labels_opened"])


if __name__ == "__main__":
    unittest.main()
