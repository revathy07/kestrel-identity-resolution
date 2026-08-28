from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import openpyxl

from src.ingestion.read_sources import iter_source_records, load_schema_mapping
from src.profiling.profile_identifiers import DEFAULT_MAPPING, profile_identifiers
from src.profiling.rule2_registry import (
    deterministic_value_hash,
    is_missing,
    make_profiling_key,
    potential_pairs,
)


APP_FIELDS = [
    "account_id",
    "email",
    "phone",
    "first_name",
    "last_name",
    "dob",
    "device_id",
    "device_type",
    "signup_ts",
    "country",
    "city",
    "channel",
    "engagement_count",
]
STORE_FIELDS = [
    "customer_id",
    "app_account_ref",
    "customer_email_address",
    "contact_no",
    "first",
    "last",
    "dob",
    "device",
    "device_type",
    "line1",
    "line2",
    "city",
    "postcode",
    "country",
    "updated_ts",
    "channel",
]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_fixture(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    app_rows = []
    for index in range(20):
        app_rows.append(
            {
                "account_id": f"A{index:03d}",
                "email": " Shared@Example.Test " if index == 0 else "shared@example.test",
                "phone": "+999 (111) 222-3333" if index < 19 else "",
                "first_name": "Ada\nLovelace" if index == 0 else "",
                "last_name": "",
                "dob": "",
                "device_id": "",
                "device_type": "web",
                "signup_ts": "2026-01-01T00:00:00+00:00",
                "country": "",
                "city": "",
                "channel": "app",
                "engagement_count": 1,
            }
        )
    write_csv(data_dir / "app_users.csv", APP_FIELDS, app_rows)

    store_rows = []
    for index in range(21):
        store_rows.append(
            {
                "customer_id": f"C{index:03d}",
                "app_account_ref": "",
                "customer_email_address": "shared@example.test",
                "contact_no": "+9991112223333",
                "first": "",
                "last": "",
                "dob": "",
                "device": "",
                "device_type": "web",
                "line1": "",
                "line2": "",
                "city": "",
                "postcode": "",
                "country": "",
                "updated_ts": "2026-01-01T00:00:00+00:00",
                "channel": "store",
            }
        )
    write_csv(data_dir / "store_customers.csv", STORE_FIELDS, store_rows)

    ticket = {
        "booking_id": "B001",
        "account_id": "",
        "full_name": "None",
        "email": "",
        "phone": "",
        "device_id": "",
        "city": "",
        "event_ts": "2026-01-01T00:00:00+00:00",
        "created_ts": "2026-01-01T00:00:00+00:00",
        "channel": "event",
    }
    (data_dir / "ticketing.jl").write_text(json.dumps(ticket) + "\n", encoding="utf-8")

    workbook = openpyxl.Workbook()
    notes = workbook.active
    notes.title = "notes"
    notes.append(["note", "not a data sheet"])
    sheet = workbook.create_sheet("subscriptions")
    sheet.append(["Synthetic subscription export", None, None, None, None, None, None, None])
    sheet.append(
        [
            "subscription_id",
            "email",
            "subscriber_name",
            "billing_name",
            "payment_token",
            "start_date",
            "country",
            "channel",
        ]
    )
    sheet.append(["S001", "", "", "", "", "2026-01-01", "", "web"])
    workbook.save(data_dir / "subscriptions.xlsx")
    workbook.close()

    social = [
        {
            "provider": "google",
            "login_ts": "2026-01-01T00:00:00+00:00",
            "channel": "social",
            "engagement_count": 1,
            "identity_payload": {
                "provider_id": "provider-001",
                "verified_email": "unique@social.example",
            },
        }
    ]
    (data_dir / "social_logins.json").write_text(
        json.dumps(social), encoding="utf-8"
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProfilingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.data_dir = cls.root / "data"
        cls.output_dir = cls.root / "outputs"
        make_fixture(cls.data_dir)
        cls.normal_files = [
            cls.data_dir / "app_users.csv",
            cls.data_dir / "store_customers.csv",
            cls.data_dir / "ticketing.jl",
            cls.data_dir / "subscriptions.xlsx",
            cls.data_dir / "social_logins.json",
        ]
        cls.before_hashes = {path.name: digest(path) for path in cls.normal_files}
        cls.summary = profile_identifiers(
            cls.data_dir, cls.output_dir, DEFAULT_MAPPING, show_progress=False
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_all_five_source_formats_and_record_ids(self) -> None:
        mapping = load_schema_mapping(DEFAULT_MAPPING)
        counts = {}
        first_records = {}
        for source, spec in mapping["sources"].items():
            records = list(iter_source_records(self.data_dir, source, spec))
            counts[source] = len(records)
            first_records[source] = records[0]
        self.assertEqual(
            counts,
            {
                "app_users": 20,
                "store_customers": 21,
                "ticketing": 1,
                "subscriptions": 1,
                "social_logins": 1,
            },
        )
        self.assertEqual(first_records["app_users"].source_record_id, "A000")
        self.assertEqual(first_records["ticketing"].source_record_id, "B001")
        self.assertEqual(first_records["subscriptions"].source_record_id, "S001")

    def test_excel_title_row_detection_and_non_data_sheet(self) -> None:
        mapping = load_schema_mapping(DEFAULT_MAPPING)
        record = next(
            iter_source_records(
                self.data_dir, "subscriptions", mapping["sources"]["subscriptions"]
            )
        )
        self.assertEqual(record.raw["subscription_id"], "S001")
        self.assertNotIn("Synthetic subscription export", record.raw)

    def test_social_identity_payload_remains_nested(self) -> None:
        mapping = load_schema_mapping(DEFAULT_MAPPING)
        record = next(
            iter_source_records(
                self.data_dir, "social_logins", mapping["sources"]["social_logins"]
            )
        )
        self.assertEqual(record.source_record_id, "provider-001")
        self.assertIn("identity_payload", record.raw)
        self.assertNotIn("verified_email", record.raw)
        self.assertEqual(record.raw["identity_payload"]["verified_email"], "unique@social.example")

    def test_multiline_quoted_csv_field_is_preserved(self) -> None:
        mapping = load_schema_mapping(DEFAULT_MAPPING)
        record = next(
            iter_source_records(self.data_dir, "app_users", mapping["sources"]["app_users"])
        )
        self.assertEqual(record.raw["first_name"], "Ada\nLovelace")

    def test_global_frequency_and_strict_rule2_boundary(self) -> None:
        registry = json.loads(
            (self.output_dir / "rule2_registry.json").read_text(encoding="utf-8")
        )["values"]
        shared_email = [
            row
            for row in registry
            if row["attribute_concept"] == "email"
            and row["profiling_key"] == "shared@example.test"
        ]
        self.assertEqual(len(shared_email), 1)
        self.assertEqual(shared_email[0]["global_frequency"], 41)
        self.assertEqual(
            shared_email[0]["frequency_by_source"],
            {"app_users": 20, "store_customers": 21},
        )
        self.assertFalse(
            any(
                row["attribute_concept"] == "phone"
                and row["profiling_key"] == "+9991112223333"
                for row in registry
            ),
            "A value occurring exactly 40 times must remain outside the Rule 2 registry",
        )

    def test_truth_files_are_not_required_or_referenced(self) -> None:
        self.assertEqual(self.summary["total_records_profiled"], 44)
        production_files = [
            Path("src/ingestion/read_sources.py"),
            Path("src/profiling/profile_identifiers.py"),
            Path("src/profiling/rule2_registry.py"),
        ]
        forbidden_names = [
            "person_map.csv",
            "hard_negatives.json",
            "canonical_duplicate_links.jsonl",
            "person_id",
            "evidence_mode",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8").casefold() for path in production_files)
        for name in forbidden_names:
            self.assertNotIn(name.casefold(), combined)

    def test_source_files_are_byte_identical_after_profiling(self) -> None:
        after = {path.name: digest(path) for path in self.normal_files}
        self.assertEqual(self.before_hashes, after)

    def test_all_required_outputs_are_created(self) -> None:
        expected = {
            "source_summary.csv",
            "column_profile.csv",
            "identifier_frequency.csv",
            "worthless_values.csv",
            "rule2_registry.json",
            "data_quality_summary.json",
            "profiling_report.md",
        }
        self.assertEqual(expected, {path.name for path in self.output_dir.iterdir()})
        stakeholder_csv = (self.output_dir / "worthless_values.csv").read_text(encoding="utf-8")
        self.assertNotIn("shared@example.test", stakeholder_csv)
        self.assertNotIn("profiling_key", stakeholder_csv.splitlines()[0])

    def test_source_record_ids_are_profiled_for_every_source(self) -> None:
        with (self.output_dir / "column_profile.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        profiled_sources = {
            row["source"]
            for row in rows
            if row["canonical_concept"] == "source_record_id"
        }
        self.assertEqual(
            profiled_sources,
            {"app_users", "store_customers", "ticketing", "subscriptions", "social_logins"},
        )


class ProfilingHelperTests(unittest.TestCase):
    def test_missing_value_semantics(self) -> None:
        for value in (None, "", "   ", '""', "''", "NULL", "None"):
            self.assertTrue(is_missing(value), repr(value))
        self.assertFalse(is_missing("N/A"))
        self.assertFalse(is_missing("0"))

    def test_conservative_email_and_phone_keys(self) -> None:
        email, email_transform = make_profiling_key("email", " A.B+tag@Example.COM ")
        phone, phone_transform = make_profiling_key("phone", " +999 (111) 222-3333 ")
        self.assertEqual(email, "a.b+tag@example.com")
        self.assertIn("case-fold", email_transform)
        self.assertEqual(phone, "+9991112223333")
        self.assertIn("punctuation", phone_transform)

    def test_deterministic_hash_is_concept_scoped(self) -> None:
        first = deterministic_value_hash("email", "shared@example.test")
        second = deterministic_value_hash("email", "shared@example.test")
        other_concept = deterministic_value_hash("provider_id", "shared@example.test")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, other_concept)

    def test_candidate_explosion_arithmetic(self) -> None:
        self.assertEqual(potential_pairs(0), 0)
        self.assertEqual(potential_pairs(1), 0)
        self.assertEqual(potential_pairs(40), 780)
        self.assertEqual(potential_pairs(41), 820)


if __name__ == "__main__":
    unittest.main()
