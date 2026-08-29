"""Generate deterministic candidate pairs from the Phase 4 normalized table.

This production-style module reads no evaluation artefact. It recalculates Rule 2 on
normalized values, creates bounded candidate blocks, and stops before scoring or matching.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sqlite3
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterator, Mapping

from src.blocking.rules import DEFAULT_RULES, BlockingError, derive_candidate_keys, load_blocking_rules
from src.profiling.rule2_registry import deterministic_value_hash, mask_display_value


BLOCKER_VERSION = 1
CANDIDATE_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "blocking_rule_count",
]


@dataclass
class NormalizedRecord:
    source: str
    ordinal: int
    source_record_id: str
    values: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configuration_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_normalized_records(path: Path) -> Iterator[NormalizedRecord]:
    """Group the long-form normalized file into physical source records."""

    required = {
        "source",
        "record_ordinal",
        "source_record_id",
        "canonical_concept",
        "normalized_value",
        "normalization_status",
    }
    current: NormalizedRecord | None = None
    seen_groups: set[tuple[str, int]] = set()
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise BlockingError(
                    f"Normalized input is missing required columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row in reader:
                try:
                    key = (row["source"], int(row["record_ordinal"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise BlockingError(f"Invalid record identity in normalized input: {row}") from exc
                if current is None or key != (current.source, current.ordinal):
                    if current is not None:
                        yield current
                    if key in seen_groups:
                        raise BlockingError(f"Normalized rows for physical record {key} are not contiguous")
                    seen_groups.add(key)
                    current = NormalizedRecord(key[0], key[1], row["source_record_id"])
                elif row["source_record_id"] != current.source_record_id:
                    raise BlockingError(f"Conflicting record IDs for physical record {key}")
                if row["normalization_status"] == "valid" and row["normalized_value"]:
                    current.values[row["canonical_concept"]].add(row["normalized_value"])
            if current is not None:
                yield current
    except OSError as exc:
        raise BlockingError(f"Unable to read normalized input {path}: {exc}") from exc


def _open_deterministic_gzip_csv(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=CANDIDATE_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend(
        "| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _build_report(manifest: Mapping[str, Any], rule_rows: list[dict[str, Any]]) -> str:
    phase = manifest["phase_boundaries"]
    return "\n".join(
        [
            "# Phase 5 candidate-blocking report",
            "",
            "## Outcome",
            "",
            f"- Physical source records: **{manifest['total_source_records']:,}**",
            f"- Unique candidate pairs: **{manifest['unique_candidate_pairs']:,}**",
            f"- Candidate reduction from all unordered pairs: **{manifest['candidate_reduction_percentage']:.6f}%**",
            f"- Normalized Rule 2 values (> {manifest['rule2_threshold']} records): **{manifest['normalized_rule2_value_count']:,}**",
            f"- Records with at least one eligible block: **{manifest['records_with_eligible_blocks']:,}**",
            "",
            "A candidate pair means only that two records deserve comparison. It is not a match decision.",
            "",
            "## Blocking rules",
            "",
            _markdown_table(
                ["Rule", "Eligible keys", "Pair-rule incidences", "Pairs unique to rule"],
                [
                    [row["blocking_rule"], f"{row['eligible_block_keys']:,}", f"{row['pair_rule_incidences']:,}", f"{row['pairs_unique_to_rule']:,}"]
                    for row in rule_rows
                ],
            ),
            "",
            "Exact normalized values are eligible only when their normalized global frequency is 2–40.",
            "Derived keys are discovery-only and are independently discarded when their block contains more than 40 records.",
            "Email skeletons preserve the Phase 4 normalized value and remove dots/plus suffixes only in a temporary block key.",
            "Phone suffixes do not infer a country code. Name composites are candidate keys, not fuzzy scores.",
            "",
            "## Rule 2 and safety",
            "",
            f"Rule 2 was recalculated after normalization. **{manifest['normalized_rule2_value_count']:,}** single concept/value keys occur on more than 40 physical records and cannot form exact blocks.",
            f"A further **{manifest['oversized_derived_block_count']:,}** derived keys were suppressed by the same 40-record safety cap.",
            "The public CSV masks high-frequency values; the machine registry is an internal reproducibility artifact.",
            "",
            "## Phase boundary",
            "",
            f"- Candidate pairs created: `{str(phase['candidate_pairs_created']).lower()}`",
            f"- Match scores calculated: `{str(phase['match_scores_calculated']).lower()}`",
            f"- Match decisions made: `{str(phase['match_decisions_made']).lower()}`",
            f"- Clusters formed: `{str(phase['clusters_formed']).lower()}`",
            f"- Evaluation labels read: `{str(phase['evaluation_labels_read']).lower()}`",
            "",
            "Blocking recall and discarded true links are measured separately by the evaluation-only command.",
            "",
        ]
    )


def generate_candidates(
    normalized_path: Path,
    output_dir: Path,
    *,
    rules_path: Path = DEFAULT_RULES,
    show_progress: bool = True,
) -> dict[str, Any]:
    normalized_path = Path(normalized_path)
    output_dir = Path(output_dir)
    rules_path = Path(rules_path)
    rules = load_blocking_rules(rules_path)
    if not normalized_path.exists():
        raise BlockingError(f"Normalized input not found: {normalized_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    if show_progress:
        print("[blocking] Pass 1/3: recalculating normalized global frequencies...")
    frequencies: Counter[tuple[str, str]] = Counter()
    source_counts: Counter[str] = Counter()
    for record in iter_normalized_records(normalized_path):
        source_counts[record.source] += 1
        for concept, values in record.values.items():
            frequencies.update((concept, value) for value in values)
    total_records = sum(source_counts.values())
    threshold = int(rules["rule2_threshold"])
    minimum = int(rules["minimum_block_size"])
    maximum = int(rules["maximum_block_size"])
    high_values = {key for key, frequency in frequencies.items() if frequency > threshold}

    if show_progress:
        print("[blocking] Pass 2/3: sizing candidate blocks and normalized Rule 2 values...")
    block_counts: Counter[tuple[str, str]] = Counter()
    high_by_source: Counter[tuple[str, str, str]] = Counter()
    for record in iter_normalized_records(normalized_path):
        for concept, values in record.values.items():
            for value in values:
                if (concept, value) in high_values:
                    high_by_source[(concept, value, record.source)] += 1
        block_counts.update(derive_candidate_keys(record.values, frequencies, rules))
    eligible_keys = {key for key, count in block_counts.items() if minimum <= count <= maximum}

    if show_progress:
        print("[blocking] Pass 3/3: materializing and deduplicating candidate pairs...")
    members: dict[tuple[str, str], list[int]] = defaultdict(list)
    records: list[tuple[str, int, str]] = []
    records_with_blocks = 0
    for record_index, record in enumerate(iter_normalized_records(normalized_path)):
        records.append((record.source, record.ordinal, record.source_record_id))
        keys = derive_candidate_keys(record.values, frequencies, rules) & eligible_keys
        if keys:
            records_with_blocks += 1
        for key in keys:
            members[key].append(record_index)

    temp_directory = Path(tempfile.mkdtemp(prefix="kestrel-blocking-"))
    database_path = temp_directory / "candidate_pairs.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(
            "CREATE TABLE records (record_index INTEGER PRIMARY KEY, source TEXT, ordinal INTEGER, source_record_id TEXT)"
        )
        connection.executemany(
            "INSERT INTO records VALUES (?, ?, ?, ?)",
            ((index, *record) for index, record in enumerate(records)),
        )
        connection.execute(
            "CREATE TABLE pair_rules (left_index INTEGER, right_index INTEGER, rule TEXT, PRIMARY KEY(left_index, right_index, rule)) WITHOUT ROWID"
        )
        incidence_by_rule: Counter[str] = Counter()
        eligible_by_rule: Counter[str] = Counter()
        for (rule_name, block_key), block_members in sorted(members.items()):
            del block_key
            eligible_by_rule[rule_name] += 1
            pair_rows = [(left, right, rule_name) for left, right in combinations(sorted(block_members), 2)]
            incidence_by_rule[rule_name] += len(pair_rows)
            connection.executemany("INSERT OR IGNORE INTO pair_rules VALUES (?, ?, ?)", pair_rows)
        connection.commit()
        connection.execute("CREATE INDEX pair_order ON pair_rules(left_index, right_index, rule)")

        unique_candidates = int(
            connection.execute(
                "SELECT COUNT(*) FROM (SELECT left_index, right_index FROM pair_rules GROUP BY left_index, right_index)"
            ).fetchone()[0]
        )
        unique_only = Counter(
            {
                str(rule): int(count)
                for rule, count in connection.execute(
                    "SELECT MIN(rule), COUNT(*) FROM (SELECT left_index, right_index, MIN(rule) AS rule, COUNT(*) AS n FROM pair_rules GROUP BY left_index, right_index) WHERE n = 1 GROUP BY rule"
                )
            }
        )

        candidate_path = output_dir / "candidate_pairs.csv.gz"
        binary, text_handle, writer = _open_deterministic_gzip_csv(candidate_path)
        try:
            query = """
                SELECT left_record.source, left_record.ordinal, left_record.source_record_id,
                       right_record.source, right_record.ordinal, right_record.source_record_id,
                       GROUP_CONCAT(grouped.rule, ';'), COUNT(grouped.rule)
                FROM (
                    SELECT left_index, right_index, rule
                    FROM pair_rules ORDER BY left_index, right_index, rule
                ) AS grouped
                JOIN records AS left_record ON left_record.record_index = grouped.left_index
                JOIN records AS right_record ON right_record.record_index = grouped.right_index
                GROUP BY grouped.left_index, grouped.right_index
                ORDER BY grouped.left_index, grouped.right_index
            """
            for row in connection.execute(query):
                writer.writerow(dict(zip(CANDIDATE_COLUMNS, row)))
        finally:
            text_handle.close()
            binary.close()
    finally:
        connection.close()
        try:
            database_path.unlink(missing_ok=True)
            temp_directory.rmdir()
        except OSError:
            pass

    all_possible = math.comb(total_records, 2) if total_records > 1 else 0
    rule_names = sorted({rule for rule, _ in eligible_keys})
    rule_rows = [
        {
            "blocking_rule": rule,
            "eligible_block_keys": eligible_by_rule[rule],
            "eligible_record_memberships": sum(
                count for (item_rule, _), count in block_counts.items() if item_rule == rule and minimum <= count <= maximum
            ),
            "pair_rule_incidences": incidence_by_rule[rule],
            "pairs_unique_to_rule": unique_only[rule],
        }
        for rule in rule_names
    ]
    _write_csv(
        output_dir / "blocking_rule_summary.csv",
        rule_rows,
        ["blocking_rule", "eligible_block_keys", "eligible_record_memberships", "pair_rule_incidences", "pairs_unique_to_rule"],
    )

    registry: list[dict[str, Any]] = []
    for concept, value in sorted(high_values):
        by_source = {
            source: high_by_source[(concept, value, source)]
            for source in sorted(source_counts)
            if high_by_source[(concept, value, source)]
        }
        registry.append(
            {
                "attribute_concept": concept,
                "masked_display_value": mask_display_value(concept, value),
                "value_hash": deterministic_value_hash(concept, value),
                "normalized_value": value,
                "global_frequency": frequencies[(concept, value)],
                "frequency_by_source": by_source,
                "rule2_status": "worthless",
                "reason": f"Observed on {frequencies[(concept, value)]:,} physical records after normalization; strict threshold is greater than {threshold}.",
            }
        )
    (output_dir / "normalized_rule2_registry.json").write_text(
        json.dumps({"version": 1, "threshold": threshold, "values": registry}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    public_registry_rows = [
        {key: item[key] for key in ("attribute_concept", "masked_display_value", "value_hash", "global_frequency", "rule2_status")}
        for item in registry
    ]
    _write_csv(
        output_dir / "normalized_rule2_values.csv",
        public_registry_rows,
        ["attribute_concept", "masked_display_value", "value_hash", "global_frequency", "rule2_status"],
    )

    oversized_derived = sum(
        1 for (rule, _), count in block_counts.items() if not rule.startswith("exact_") and count > maximum
    )
    pair_incidences = sum(incidence_by_rule.values())
    candidate_path = output_dir / "candidate_pairs.csv.gz"
    manifest: dict[str, Any] = {
        "phase": "candidate_blocking",
        "blocker_version": BLOCKER_VERSION,
        "total_source_records": total_records,
        "source_counts": dict(source_counts),
        "rule2_threshold": threshold,
        "normalized_distinct_concept_values": len(frequencies),
        "normalized_rule2_value_count": len(registry),
        "eligible_block_key_count": len(eligible_keys),
        "oversized_derived_block_count": oversized_derived,
        "records_with_eligible_blocks": records_with_blocks,
        "candidate_pair_incidences_before_pair_deduplication": pair_incidences,
        "unique_candidate_pairs": unique_candidates,
        "all_possible_unordered_record_pairs": all_possible,
        "candidate_percentage_of_all_pairs": 100 * unique_candidates / all_possible if all_possible else 0.0,
        "candidate_reduction_percentage": 100 * (1 - unique_candidates / all_possible) if all_possible else 100.0,
        "input": {"path": _portable_path(normalized_path), "sha256": _sha256(normalized_path)},
        "configuration": {"path": _portable_path(rules_path), "sha256": _configuration_hash(rules_path)},
        "candidate_output": {
            "path": candidate_path.name,
            "compression": "gzip",
            "rows": unique_candidates,
            "size_bytes": candidate_path.stat().st_size,
            "sha256": _sha256(candidate_path),
        },
        "phase_boundaries": {
            "candidate_pairs_created": True,
            "match_scores_calculated": False,
            "match_decisions_made": False,
            "clusters_formed": False,
            "evaluation_labels_read": False,
        },
    }
    (output_dir / "candidate_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "blocking_report.md").write_text(_build_report(manifest, rule_rows), encoding="utf-8")
    if show_progress:
        print(f"[blocking] Complete: {unique_candidates:,} candidates from {total_records:,} records")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--normalized-path",
        type=Path,
        default=Path("outputs/normalization/normalized_identifiers.csv.gz"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/blocking"))
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    try:
        generate_candidates(args.normalized_path, args.output_dir, rules_path=args.rules)
    except BlockingError as exc:
        print(f"[blocking] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
