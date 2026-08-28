from __future__ import annotations

import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.normalization.normalize_identifiers import normalize_identifiers
from src.normalization.rules import DEFAULT_RULES, load_normalization_rules, normalize_value
from tests.test_profiling import make_fixture


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NormalizationRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_normalization_rules(DEFAULT_RULES)

    def test_email_preserves_dots_and_plus_suffix(self) -> None:
        result = normalize_value("email", " A.B+tag@Example.COM ", self.rules)
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.normalized_value, "a.b+tag@example.com")

    def test_email_is_extracted_from_one_export_artifact(self) -> None:
        result = normalize_value(
            "email", 'contact: <Alice@example.test> "quoted note"', self.rules
        )
        self.assertEqual(result.normalized_value, "alice@example.test")
        self.assertIn("email_extracted_from_export_text", result.quality_flags)
        ambiguous = normalize_value(
            "email", "a@example.test and b@example.test", self.rules
        )
        self.assertEqual(ambiguous.status, "invalid")
        self.assertIsNone(ambiguous.normalized_value)

    def test_phone_removes_formatting_but_does_not_infer_country(self) -> None:
        explicit = normalize_value("phone", " +999 (123) 456-789 ", self.rules)
        local = normalize_value("phone", "0123 456 789", self.rules)
        self.assertEqual(explicit.normalized_value, "+999123456789")
        self.assertEqual(local.normalized_value, "0123456789")
        self.assertIn("country_code_not_explicit", local.quality_flags)

    def test_names_use_no_fuzzy_or_token_rewrite(self) -> None:
        result = normalize_value("first_name", '  Élodie   Smith "note"\nignored', self.rules)
        self.assertEqual(result.normalized_value, "élodie smith")
        self.assertIn("trailing_multiline_annotation_removed", result.quality_flags)
        self.assertIn("trailing_quoted_annotation_removed", result.quality_flags)

    def test_dates_parse_and_flag_but_are_not_repaired(self) -> None:
        parsed = normalize_value("date_of_birth", "31-12-2000", self.rules)
        old = normalize_value("date_of_birth", "1900-01-01", self.rules)
        invalid = normalize_value("date_of_birth", "31/31/2000", self.rules)
        self.assertEqual(parsed.normalized_value, "2000-12-31")
        self.assertEqual(old.normalized_value, "1900-01-01")
        self.assertIn("age_above_plausible_limit", old.quality_flags)
        self.assertEqual(invalid.status, "invalid")

    def test_country_city_postcode_and_identifier_rules(self) -> None:
        self.assertEqual(normalize_value("country", "U.S.", self.rules).normalized_value, "US")
        self.assertEqual(normalize_value("city", "Metro-City", self.rules).normalized_value, "metro city")
        self.assertEqual(normalize_value("postcode", "SW1A 1AA", self.rules).normalized_value, "SW1A1AA")
        identifier = normalize_value("device_id", " Device-AbC ", self.rules)
        self.assertEqual(identifier.normalized_value, "Device-AbC")

    def test_hash_shape_and_missing_semantics(self) -> None:
        valid_hash = "a" * 64
        self.assertEqual(
            normalize_value("hashed_email", valid_hash.upper(), self.rules).normalized_value,
            valid_hash,
        )
        self.assertEqual(normalize_value("hashed_email", "abc", self.rules).status, "invalid")
        for value in (None, "", "   ", '""', "NULL", "None"):
            self.assertEqual(normalize_value("email", value, self.rules).status, "missing")


class NormalizationPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.data_dir = cls.root / "data"
        cls.output_dir = cls.root / "output"
        cls.second_output_dir = cls.root / "output-second"
        make_fixture(cls.data_dir)
        cls.source_files = sorted(cls.data_dir.iterdir())
        cls.before = {path.name: file_hash(path) for path in cls.source_files}
        cls.manifest = normalize_identifiers(
            cls.data_dir, cls.output_dir, show_progress=False
        )
        cls.after = {path.name: file_hash(path) for path in cls.source_files}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_all_sources_and_expected_observation_count(self) -> None:
        self.assertEqual(self.manifest["total_source_records"], 44)
        self.assertEqual(
            self.manifest["source_counts"],
            {
                "app_users": 20,
                "store_customers": 21,
                "ticketing": 1,
                "subscriptions": 1,
                "social_logins": 1,
            },
        )
        self.assertEqual(self.manifest["identifier_observations"], 491)

    def test_raw_sources_are_byte_identical(self) -> None:
        self.assertEqual(self.before, self.after)
        self.assertTrue(self.manifest["source_files_unchanged"])

    def test_long_form_output_preserves_raw_and_nested_values(self) -> None:
        with gzip.open(
            self.output_dir / "normalized_identifiers.csv.gz",
            "rt",
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 491)
        multiline = next(
            row
            for row in rows
            if row["source"] == "app_users"
            and row["source_record_id"] == "A000"
            and row["raw_field"] == "first_name"
        )
        self.assertEqual(multiline["raw_value"], "Ada\nLovelace")
        self.assertEqual(multiline["normalized_value"], "ada")
        social = next(
            row
            for row in rows
            if row["raw_field"] == "identity_payload.verified_email"
        )
        self.assertEqual(social["raw_value"], "unique@social.example")
        self.assertEqual(social["evidence_role"], "verified_identifier")

    def test_every_concept_and_source_record_id_is_represented(self) -> None:
        with (self.output_dir / "normalization_summary.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        concepts = {row["canonical_concept"] for row in rows}
        self.assertEqual(len(concepts), 17)
        source_id_sources = {
            row["source"] for row in rows if row["canonical_concept"] == "source_record_id"
        }
        self.assertEqual(
            source_id_sources,
            {"app_users", "store_customers", "ticketing", "subscriptions", "social_logins"},
        )

    def test_outputs_are_complete_and_phase_boundary_is_explicit(self) -> None:
        self.assertEqual(
            {path.name for path in self.output_dir.iterdir()},
            {
                "normalized_identifiers.csv.gz",
                "normalization_summary.csv",
                "normalization_issues.csv",
                "normalization_manifest.json",
                "normalization_report.md",
            },
        )
        self.assertTrue(
            all(value is False for value in self.manifest["phase_boundaries"].values())
        )

    def test_output_is_deterministic(self) -> None:
        second = normalize_identifiers(
            self.data_dir, self.second_output_dir, show_progress=False
        )
        self.assertEqual(
            self.manifest["normalized_output"]["sha256"],
            second["normalized_output"]["sha256"],
        )

    def test_normalization_has_no_truth_dependency(self) -> None:
        production_files = [
            Path("src/normalization/rules.py"),
            Path("src/normalization/normalize_identifiers.py"),
        ]
        forbidden = [
            "person_map.csv",
            "hard_negatives.json",
            "canonical_duplicate_links.jsonl",
            "person_id",
            "evidence_mode",
        ]
        text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in production_files)
        for name in forbidden:
            self.assertNotIn(name.casefold(), text)


if __name__ == "__main__":
    unittest.main()
