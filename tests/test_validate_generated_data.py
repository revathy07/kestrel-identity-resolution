import importlib.util
import json
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "src" / "validate_generated_data.py"
SPEC = importlib.util.spec_from_file_location("validate_generated_data", MODULE)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)

GENERATOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_synthetic_dataset.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location("generate_synthetic_dataset_corrected", GENERATOR_PATH)
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
assert GENERATOR_SPEC.loader is not None
sys.modules[GENERATOR_SPEC.name] = GENERATOR
GENERATOR_SPEC.loader.exec_module(GENERATOR)


class ValidatorCalculationTests(unittest.TestCase):
    def test_missing_sentinels_are_consistent(self):
        for value in (None, "", "  ", '""', "'  '", "null", "NULL", "None"):
            self.assertTrue(VALIDATOR.is_missing(value))
            self.assertTrue(GENERATOR.is_missing_identifier(value))
        self.assertFalse(VALIDATOR.is_missing("0"))

    def test_blank_and_quoted_empty_email_never_create_edges(self):
        for value in (None, "", "  ", '""', ' "quoted, comma"', "null", "None"):
            row = GENERATOR.Row({"email": value}, "hidden")
            self.assertFalse(any(token.startswith("email:") for token in GENERATOR.naive_identity_tokens(row)))

    def test_timestamp_detection_and_parse(self):
        values = {"03-04-2026 12:30:00":"DD-MM-YYYY","2026/04/03 12:30:00":"YYYY/MM/DD","04-03-26 12:30":"MM-DD-YY","2026-04-03T12:30:00+00:00":"ISO_OFFSET","1775219400000":"EPOCH_MS","2026-04-03 12:30:00":"LOCAL_TEXT"}
        for value, expected in values.items():
            self.assertEqual(VALIDATOR.timestamp_format(value), expected)
            self.assertIsNotNone(VALIDATOR.parse_timestamp(value))
        self.assertEqual(
            VALIDATOR.parse_timestamp("2026-04-03 12:00:00").hour, 6
        )

    def test_email_and_phone_evidence_normalization(self):
        self.assertEqual(VALIDATOR.norm_email("A.B+tag@brand-example.test"), "ab@brand-example.test")
        self.assertEqual(VALIDATOR.norm_phone("+999 123 456 7890"), "1234567890")
        self.assertEqual(VALIDATOR.norm_phone("01234567890"), "1234567890")

    def test_poison_is_excluded_from_usable_tokens(self):
        row={"email":"qa+001@staff.test","phone":"0000000000","device_id":"KIOSK-DEVICE-1","dob":"1970-01-01"}
        self.assertTrue(VALIDATOR.poison_types(row))
        self.assertFalse(VALIDATOR.record_tokens(row, include_poison=False))

    def test_union_find_transitivity(self):
        uf=VALIDATOR.UnionFind(4); uf.union(0,1); uf.union(1,2)
        self.assertEqual(uf.find(0),uf.find(2)); self.assertNotEqual(uf.find(0),uf.find(3))

    def test_social_payload_and_bot_behaviour_contract(self):
        person = GENERATOR.Person("P000001", "Zexmab", "Korrai", "zexmab.korrai.p000001@brand-example.test", "+999000000001", "1990-01-01", "1 Ridge Road", "", "Metrocity", "12345", "IN", "DEV-abc", "mobile")
        rng = random.Random(17)
        rows = [GENERATOR.make_social_row(person, f"twitter_{i:09d}", False, rng).data for i in range(1, 300)]
        minimal = [row for row in rows if row["provider"] == "twitter"]
        self.assertTrue(minimal)
        self.assertTrue(all(set(row["identity_payload"]) == {"provider_id", "display_name"} for row in minimal))
        banned = re.compile(r"automation\.internal|\b(?:monitor|crawler|scraper|healthcheck|lb-probe|bot)\b|dev-bot|\bheadless\b|\bautomation\b", re.I)
        bot_rows = [GENERATOR.make_bot_row(system, i, rng).data for system in GENERATOR.FINAL_ROW_WEIGHTS for i in range(1, 80)]
        self.assertFalse(any(banned.search(json.dumps(row)) for row in bot_rows))
        app_bots = [GENERATOR.make_bot_row("app_users", i, rng).data for i in range(1, 200)]
        instants = [VALIDATOR.parse_timestamp(row["signup_ts"]) for row in app_bots]
        self.assertLessEqual((max(instants)-min(instants)).total_seconds(), 300)
        self.assertLessEqual(sorted(row["engagement_count"] for row in app_bots)[len(app_bots)//2], 3)

    def test_small_generation_reconciles_hidden_metadata_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            report = GENERATOR.generate(0.01, target, 42)
            parsed_total = sum(sum(1 for _ in VALIDATOR.source_factory(target, system)()) for system in VALIDATOR.FILES)
            self.assertEqual(report["total_row_count"], parsed_total)
            social = json.loads((target / "social_logins.json").read_text(encoding="utf-8"))
            self.assertTrue(any(row["provider"] == "twitter" and set(row["identity_payload"]) == {"provider_id", "display_name"} for row in social))
            canonical = list(VALIDATOR.iter_jsonl(target / "hidden" / "canonical_duplicate_links.jsonl"))
            self.assertEqual(len(canonical), report["measured_problem_rates"]["canonical_duplicate_links"])
            required = {"exact_verified_email", "email_case_variation", "email_dotted_local_part", "email_plus_suffix", "phone_country_code", "phone_spaced", "phone_leading_zero", "name_city_only", "device_only", "no_usable_evidence"}
            observed = {mode for link in canonical for mode in link["evidence_modes"]}
            self.assertTrue(required <= observed)
            metrics = report["measured_problem_rates"]
            self.assertGreaterEqual(metrics["explicit_hard_negative_rate_rule2"], 0.05)
            self.assertLessEqual(metrics["unique_unordered_naive_candidate_pairs"], metrics["candidate_pair_incidences_before_deduplication"])
            audit, _summary = VALIDATOR.audit_dataset(target, target / "audit", GENERATOR_PATH)
            statuses = {check.id: check.status for check in audit.checks}
            for check_id in ("FORMAT-014", "BOT-003", "REPORT-001", "REPORT-002", "UNREC-002", "REPORT-005", "HARDNEG-002"):
                self.assertEqual(statuses[check_id], "PASS", check_id)


if __name__ == "__main__": unittest.main()
