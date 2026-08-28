"""Profile identifiers globally and discover Rule 2 worthless values.

This phase deliberately stops before matching. It creates conservative profiling keys,
frequency tables, safety diagnostics, and a registry for values observed on more than 40
physical records. It never imports evaluation modules or reads labelled truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.ingestion.read_sources import (
    SourceReadError,
    get_raw_value,
    iter_source_records,
    load_schema_mapping,
)
from src.profiling.rule2_registry import (
    MISSING_TEXT_TOKENS,
    RULE2_THRESHOLD,
    make_profiling_key,
    make_registry_entry,
    potential_pairs,
)


DEFAULT_MAPPING = Path(__file__).resolve().parents[2] / "config" / "schema_mapping.yaml"
BATCH_SIZE = 5_000


class ProfilingError(RuntimeError):
    """Raised when profiling cannot safely produce a complete result."""


@dataclass
class ColumnState:
    total_count: int = 0
    missing_count: int = 0


class FrequencyStore:
    """Disk-backed exact counters for raw fields and record-level concept values."""

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.executescript(
            """
            CREATE TABLE column_values (
                source TEXT NOT NULL,
                raw_field TEXT NOT NULL,
                concept TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                profiling_key TEXT NOT NULL,
                transformation TEXT NOT NULL,
                frequency INTEGER NOT NULL,
                PRIMARY KEY (source, raw_field, raw_value, profiling_key)
            ) WITHOUT ROWID;

            CREATE TABLE record_values (
                source TEXT NOT NULL,
                record_ordinal INTEGER NOT NULL,
                source_record_id TEXT NOT NULL,
                concept TEXT NOT NULL,
                profiling_key TEXT NOT NULL,
                transformation TEXT NOT NULL,
                display_raw TEXT NOT NULL,
                PRIMARY KEY (source, record_ordinal, concept, profiling_key)
            ) WITHOUT ROWID;
            """
        )

    def add_batch(
        self,
        column_rows: list[tuple[str, str, str, str, str, str]],
        record_rows: list[tuple[str, int, str, str, str, str, str]],
    ) -> None:
        if column_rows:
            self.connection.executemany(
                """
                INSERT INTO column_values
                    (source, raw_field, concept, raw_value, profiling_key,
                     transformation, frequency)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT (source, raw_field, raw_value, profiling_key)
                DO UPDATE SET frequency = frequency + 1
                """,
                column_rows,
            )
        if record_rows:
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO record_values
                    (source, record_ordinal, source_record_id, concept, profiling_key,
                     transformation, display_raw)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                record_rows,
            )
        self.connection.commit()

    def finalize(self) -> None:
        self.connection.executescript(
            """
            CREATE INDEX record_values_concept_key
                ON record_values (concept, profiling_key);
            CREATE INDEX record_values_source_concept_key
                ON record_values (source, concept, profiling_key);

            CREATE TABLE source_frequency AS
            SELECT
                source,
                concept,
                profiling_key,
                MIN(transformation) AS transformation,
                MIN(display_raw) AS representative_raw_value,
                COUNT(*) AS source_frequency
            FROM record_values
            GROUP BY source, concept, profiling_key;

            CREATE UNIQUE INDEX source_frequency_key
                ON source_frequency (source, concept, profiling_key);
            CREATE INDEX source_frequency_concept_key
                ON source_frequency (concept, profiling_key);

            CREATE TABLE global_frequency AS
            SELECT
                concept,
                profiling_key,
                MIN(transformation) AS transformation,
                MIN(representative_raw_value) AS representative_raw_value,
                SUM(source_frequency) AS global_frequency,
                COUNT(*) AS source_count
            FROM source_frequency
            GROUP BY concept, profiling_key;

            CREATE UNIQUE INDEX global_frequency_key
                ON global_frequency (concept, profiling_key);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def _validate_mapping(mapping: Mapping[str, Any]) -> None:
    canonical = set(mapping["canonical_concepts"])
    if "source_record_id" not in canonical:
        raise ProfilingError("Canonical mapping must include source_record_id")
    for source, spec in mapping["sources"].items():
        identifiers = spec.get("identifiers")
        unavailable = spec.get("unavailable")
        if not isinstance(identifiers, dict) or not isinstance(unavailable, list):
            raise ProfilingError(f"{source} must declare identifiers and unavailable concepts")
        mapped = set(identifiers.values()) | {"source_record_id"}
        unavailable_set = set(unavailable)
        overlap = mapped & unavailable_set
        if overlap:
            raise ProfilingError(f"{source} maps and marks unavailable: {sorted(overlap)}")
        missing = canonical - mapped - unavailable_set
        extras = (mapped | unavailable_set) - canonical
        if missing or extras:
            raise ProfilingError(
                f"{source} concept coverage invalid; unaccounted={sorted(missing)}, "
                f"unknown={sorted(extras)}"
            )


def _expected_row_counts(data_dir: Path) -> dict[str, int] | None:
    report_path = data_dir / "generation_report.json"
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfilingError(f"Cannot read operational generation report: {exc}") from exc
    row_counts = report.get("row_counts")
    if not isinstance(row_counts, dict):
        raise ProfilingError("generation_report.json has no row_counts object")
    try:
        return {str(source): int(count) for source, count in row_counts.items()}
    except (TypeError, ValueError) as exc:
        raise ProfilingError("generation_report.json contains an invalid row count") from exc


def _write_csv(path: Path, headers: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _column_profiles(
    connection: sqlite3.Connection,
    states: Mapping[tuple[str, str, str], ColumnState],
) -> list[dict[str, Any]]:
    frequency_rows = connection.execute(
        """
        SELECT
            source,
            raw_field,
            concept,
            COUNT(*) AS distinct_values,
            SUM(CASE WHEN key_frequency > 1 THEN 1 ELSE 0 END) AS duplicate_values,
            MAX(key_frequency) AS maximum_frequency,
            SUM(CASE WHEN key_frequency = 1 THEN 1 ELSE 0 END) AS frequency_once,
            SUM(CASE WHEN key_frequency BETWEEN 2 AND 5 THEN 1 ELSE 0 END) AS frequency_2_5,
            SUM(CASE WHEN key_frequency BETWEEN 6 AND 20 THEN 1 ELSE 0 END) AS frequency_6_20,
            SUM(CASE WHEN key_frequency BETWEEN 21 AND 40 THEN 1 ELSE 0 END) AS frequency_21_40,
            SUM(CASE WHEN key_frequency > 40 THEN 1 ELSE 0 END) AS frequency_over_40
        FROM (
            SELECT source, raw_field, concept, profiling_key, SUM(frequency) AS key_frequency
            FROM column_values
            GROUP BY source, raw_field, concept, profiling_key
        )
        GROUP BY source, raw_field, concept
        """
    )
    by_column = {(row[0], row[1], row[2]): row[3:] for row in frequency_rows}
    profiles: list[dict[str, Any]] = []
    for (source, raw_field, concept), state in sorted(states.items()):
        values = by_column.get((source, raw_field, concept), (0,) * 8)
        non_null = state.total_count - state.missing_count
        distinct = int(values[0] or 0)
        profiles.append(
            {
                "source": source,
                "raw_field": raw_field,
                "canonical_concept": concept,
                "parsed_row_count": state.total_count,
                "non_null_count": non_null,
                "missing_count": state.missing_count,
                "missing_percentage": round(100 * state.missing_count / state.total_count, 6)
                if state.total_count
                else 0.0,
                "distinct_non_missing_values": distinct,
                "uniqueness_ratio": round(distinct / non_null, 8) if non_null else 0.0,
                "duplicate_value_count": int(values[1] or 0),
                "maximum_frequency": int(values[2] or 0),
                "values_appearing_once": int(values[3] or 0),
                "values_appearing_2_5_times": int(values[4] or 0),
                "values_appearing_6_20_times": int(values[5] or 0),
                "values_appearing_21_40_times": int(values[6] or 0),
                "values_appearing_over_40_times": int(values[7] or 0),
            }
        )
    return profiles


def _build_registry(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            gf.concept,
            gf.profiling_key,
            gf.representative_raw_value,
            gf.global_frequency,
            gf.transformation,
            sf.source,
            sf.source_frequency
        FROM global_frequency gf
        JOIN source_frequency sf
          ON sf.concept = gf.concept AND sf.profiling_key = gf.profiling_key
        WHERE gf.global_frequency > ?
        ORDER BY gf.global_frequency DESC, gf.concept, gf.profiling_key, sf.source
        """,
        (RULE2_THRESHOLD,),
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for concept, key, raw, global_frequency, transformation, source, source_frequency in rows:
        group = grouped.setdefault(
            (concept, key),
            {
                "concept": concept,
                "key": key,
                "raw": raw,
                "global_frequency": int(global_frequency),
                "transformation": transformation,
                "frequencies": {},
            },
        )
        group["frequencies"][source] = int(source_frequency)
    registry = [
        make_registry_entry(
            concept=group["concept"],
            profiling_key=group["key"],
            representative_raw_value=group["raw"],
            global_frequency=group["global_frequency"],
            frequency_by_source=group["frequencies"],
            transformation=group["transformation"],
        )
        for group in grouped.values()
    ]
    return sorted(
        registry,
        key=lambda entry: (
            -entry["global_frequency"],
            entry["attribute_concept"],
            entry["value_hash"],
        ),
    )


def _pair_diagnostics(connection: sqlite3.Connection) -> dict[str, int]:
    frequencies = [
        int(row[0])
        for row in connection.execute(
            "SELECT global_frequency FROM global_frequency WHERE global_frequency >= 2"
        )
    ]
    before = sum(potential_pairs(value) for value in frequencies)
    removed = sum(
        potential_pairs(value) for value in frequencies if value > RULE2_THRESHOLD
    )
    affected = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT rv.source, rv.record_ordinal
                FROM record_values rv
                JOIN global_frequency gf
                  ON gf.concept = rv.concept AND gf.profiling_key = rv.profiling_key
                WHERE gf.global_frequency > ?
                GROUP BY rv.source, rv.record_ordinal
            )
            """,
            (RULE2_THRESHOLD,),
        ).fetchone()[0]
    )
    return {
        "potential_pair_incidences_before_rule2": before,
        "potential_pair_incidences_removed_by_rule2": removed,
        "potential_pair_incidences_remaining_after_rule2": before - removed,
        "records_affected_by_at_least_one_rule2_value": affected,
    }


def _concept_summaries(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            concept,
            COUNT(*) AS distinct_keys,
            SUM(global_frequency) AS record_incidences,
            MAX(global_frequency) AS maximum_frequency,
            SUM(CASE WHEN global_frequency > ? THEN 1 ELSE 0 END) AS rule2_values
        FROM global_frequency
        GROUP BY concept
        ORDER BY concept
        """,
        (RULE2_THRESHOLD,),
    )
    return [
        {
            "concept": row[0],
            "distinct_profiling_keys": int(row[1]),
            "record_incidences": int(row[2]),
            "maximum_global_frequency": int(row[3]),
            "rule2_value_count": int(row[4]),
        }
        for row in rows
    ]


def _write_identifier_frequency(connection: sqlite3.Connection, path: Path) -> int:
    headers = [
        "source",
        "raw_field",
        "canonical_concept",
        "raw_value",
        "profiling_key",
        "raw_value_frequency",
        "source_frequency",
        "global_frequency",
        "profiling_transformation",
    ]
    query = connection.execute(
        """
        SELECT
            cv.source,
            cv.raw_field,
            cv.concept,
            cv.raw_value,
            cv.profiling_key,
            cv.frequency,
            sf.source_frequency,
            gf.global_frequency,
            cv.transformation
        FROM column_values cv
        JOIN source_frequency sf
          ON sf.source = cv.source
         AND sf.concept = cv.concept
         AND sf.profiling_key = cv.profiling_key
        JOIN global_frequency gf
          ON gf.concept = cv.concept
         AND gf.profiling_key = cv.profiling_key
        """
    )
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in query:
            writer.writerow(row)
            count += 1
    return count


def _schema_rows(mapping: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for source, spec in mapping["sources"].items():
        rows.append(
            {
                "source": source,
                "raw_field": spec["record_id"],
                "canonical_concept": "source_record_id",
                "availability": "available (record key)",
            }
        )
        rows.extend(
            {
                "source": source,
                "raw_field": raw_field,
                "canonical_concept": concept,
                "availability": "available",
            }
            for raw_field, concept in spec["identifiers"].items()
        )
        rows.extend(
            {
                "source": source,
                "raw_field": "—",
                "canonical_concept": concept,
                "availability": "unavailable",
            }
            for concept in spec["unavailable"]
        )
    return rows


def _data_quality_summary(
    *,
    total_records: int,
    source_rows: list[dict[str, Any]],
    column_profiles: list[dict[str, Any]],
    concept_summaries: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    pair_diagnostics: Mapping[str, int],
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    missing_ranked = sorted(
        column_profiles,
        key=lambda row: (-row["missing_percentage"], row["source"], row["raw_field"]),
    )
    worst_missing = missing_ranked[0] if missing_ranked else None
    top_value = registry[0] if registry else None
    concept_rule2 = sorted(
        concept_summaries,
        key=lambda row: (-row["rule2_value_count"], row["concept"]),
    )
    availability_counts = {
        source: len(set(spec["identifiers"].values())) + 1
        for source, spec in mapping["sources"].items()
    }

    risks = [
        (
            f"Unfiltered exact values imply {pair_diagnostics['potential_pair_incidences_before_rule2']:,} "
            "potential pair incidences; the same record pair may occur under several concepts."
        ),
        (
            f"Rule 2 marks {len(registry):,} concept/value keys as worthless and removes "
            f"{pair_diagnostics['potential_pair_incidences_removed_by_rule2']:,} potential incidences."
        ),
        (
            f"{pair_diagnostics['records_affected_by_at_least_one_rule2_value']:,} records contain at "
            "least one high-frequency value that must never carry matching weight by itself."
        ),
        (
            f"The largest high-frequency value is {top_value['masked_display_value']} "
            f"({top_value['attribute_concept']}, {top_value['global_frequency']:,} records)."
            if top_value
            else "No value exceeds the Rule 2 threshold."
        ),
        (
            f"The highest missingness is {worst_missing['source']}.{worst_missing['raw_field']} at "
            f"{worst_missing['missing_percentage']:.2f}%."
            if worst_missing
            else "No mapped identifier columns were available."
        ),
    ]
    observations = [
        {
            "category": "missing_identifiers",
            "finding": risks[4],
        },
        {
            "category": "shared_identifiers",
            "finding": risks[2],
        },
        {
            "category": "suspicious_defaults",
            "finding": (
                f"Frequency profiling discovered {len(registry):,} Rule 2 values without a list of "
                "known placeholders or defaults."
            ),
        },
        {
            "category": "cross_source_schema",
            "finding": "Available canonical concepts by source: "
            + ", ".join(f"{source}={count}" for source, count in availability_counts.items())
            + ".",
        },
        {
            "category": "identifier_reliability",
            "finding": (
                f"The concept with the most Rule 2 values is {concept_rule2[0]['concept']} "
                f"({concept_rule2[0]['rule2_value_count']:,} values)."
                if concept_rule2
                else "No identifier concepts were profiled."
            ),
        },
        {
            "category": "never_use_alone",
            "finding": "Every registry entry has zero matching weight under Rule 2 and must not be used alone.",
        },
        {
            "category": "combination_only",
            "finding": (
                "Names, addresses, cities, postcodes, countries, dates of birth, and other shared "
                "fields may become useful only in combination after the later scoring design is justified."
            ),
        },
    ]
    return {
        "phase": "identifier_profiling_and_rule2_detection",
        "total_records_profiled": total_records,
        "source_counts": {row["source"]: row["parsed_row_count"] for row in source_rows},
        "identifier_concept_count": len(concept_summaries),
        "rule2_threshold": RULE2_THRESHOLD,
        "rule2_value_count": len(registry),
        **pair_diagnostics,
        "missing_value_semantics": {
            "actual_null": True,
            "empty_or_whitespace": True,
            "case_insensitive_null_like_tokens": sorted(MISSING_TEXT_TOKENS - {""}),
            "raw_values_modified": False,
        },
        "five_most_important_identifier_risks": risks,
        "observations": observations,
        "limitations": [
            "Potential pair counts are incidences, not unique unordered record pairs.",
            "Profiling keys are intentionally conservative and are not final matching normalization.",
            "No match/non-match decisions, fuzzy comparisons, blocking, scoring, or clustering are performed.",
        ],
    }


def _markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _write_report(
    path: Path,
    *,
    summary: Mapping[str, Any],
    source_rows: list[dict[str, Any]],
    schema_rows: list[dict[str, str]],
    column_profiles: list[dict[str, Any]],
    concept_summaries: list[dict[str, Any]],
    registry: list[dict[str, Any]],
) -> None:
    top_missing = sorted(
        column_profiles,
        key=lambda row: (-row["missing_percentage"], row["source"], row["raw_field"]),
    )[:10]
    top_registry = registry[:15]
    report = [
        "# Identifier profiling and Rule 2 report",
        "",
        "## Executive summary",
        "",
        f"- **Total records profiled:** {summary['total_records_profiled']:,}",
        "- **Source counts:** "
        + ", ".join(f"{name}={count:,}" for name, count in summary["source_counts"].items()),
        f"- **Identifier concepts observed:** {summary['identifier_concept_count']:,}",
        f"- **Rule 2 values (> {RULE2_THRESHOLD} records):** {summary['rule2_value_count']:,}",
        "- **Records affected by Rule 2:** "
        f"{summary['records_affected_by_at_least_one_rule2_value']:,}",
        "- **Potential pair incidences prevented:** "
        f"{summary['potential_pair_incidences_removed_by_rule2']:,}",
        "",
        "Five most important identifier risks:",
        "",
        *[f"{index}. {risk}" for index, risk in enumerate(summary["five_most_important_identifier_risks"], 1)],
        "",
        "## Source overview",
        "",
        _markdown_table(
            ["Source", "Format", "Rows", "Expected", "Reconciled"],
            (
                (
                    row["source"],
                    row["format"],
                    f"{row['parsed_row_count']:,}",
                    row["expected_row_count"] if row["expected_row_count"] != "" else "not supplied",
                    row["row_count_reconciled"],
                )
                for row in source_rows
            ),
        ),
        "",
        "Only the five normal source systems were ingested. The generation report was used only to",
        "reconcile operational row counts.",
        "",
        "## Schema mapping",
        "",
        _markdown_table(
            ["Source", "Raw field", "Canonical concept", "Availability"],
            (
                (row["source"], row["raw_field"], row["canonical_concept"], row["availability"])
                for row in schema_rows
            ),
        ),
        "",
        "Mappings create profiling concepts; they do not overwrite raw source fields. A concept",
        "listed as unavailable is not manufactured from another field.",
        "",
        "## Missingness summary",
        "",
        "For frequency analysis, actual nulls, empty or whitespace-only strings, quoted-empty",
        "strings, and case-insensitive `null`/`None` tokens are missing. Raw values remain unchanged.",
        "`duplicate_value_count` means the number of distinct profiling keys occurring more than once.",
        "",
        _markdown_table(
            ["Source", "Field", "Concept", "Missing", "Missing %", "Distinct", "Max frequency"],
            (
                (
                    row["source"],
                    row["raw_field"],
                    row["canonical_concept"],
                    f"{row['missing_count']:,}",
                    f"{row['missing_percentage']:.2f}%",
                    f"{row['distinct_non_missing_values']:,}",
                    f"{row['maximum_frequency']:,}",
                )
                for row in top_missing
            ),
        ),
        "",
        "Detailed metrics for every mapped field are in `column_profile.csv`.",
        "",
        "## Identifier-frequency summary",
        "",
        _markdown_table(
            ["Concept", "Distinct keys", "Record incidences", "Maximum frequency", "Rule 2 values"],
            (
                (
                    row["concept"],
                    f"{row['distinct_profiling_keys']:,}",
                    f"{row['record_incidences']:,}",
                    f"{row['maximum_global_frequency']:,}",
                    f"{row['rule2_value_count']:,}",
                )
                for row in concept_summaries
            ),
        ),
        "",
        "Email keys use trim and case-fold only; dots and plus suffixes remain. Phone keys remove",
        "safe display punctuation only; country codes are not inferred. Other concepts use trim only.",
        "No fuzzy name or address comparison is performed.",
        "",
        "## Rule 2 registry summary",
        "",
        _markdown_table(
            ["Concept", "Masked value", "Global frequency", "Sources", "Potential pair incidences"],
            (
                (
                    row["attribute_concept"],
                    row["masked_display_value"],
                    f"{row['global_frequency']:,}",
                    row["source_count"],
                    f"{row['potential_pair_incidences']:,}",
                )
                for row in top_registry
            ),
        ),
        "",
        "The complete stakeholder-safe list is in `worthless_values.csv`. The internal",
        "`rule2_registry.json` additionally retains the profiling key required by a later matcher.",
        "Registry membership is discovered only from global frequencies; no known-value list is used.",
        "",
        "## Candidate-explosion analysis",
        "",
        f"- Potential pair incidences before Rule 2: **{summary['potential_pair_incidences_before_rule2']:,}**",
        f"- Potential pair incidences removed: **{summary['potential_pair_incidences_removed_by_rule2']:,}**",
        f"- Potential pair incidences remaining: **{summary['potential_pair_incidences_remaining_after_rule2']:,}**",
        "",
        "Each value contributes `n × (n - 1) / 2`. These totals are potential pair incidences,",
        "not unique pairs: the same two records can share more than one identifier concept. No pair",
        "objects were constructed to calculate these figures.",
        "",
        "## Data-quality observations",
        "",
        *[f"- **{item['category'].replace('_', ' ').title()}:** {item['finding']}" for item in summary["observations"]],
        "",
        "## Recommendations for later blocking and scoring",
        "",
        "- Exclude every registry key from evidence before candidate blocking or scoring.",
        "- Prefer surviving high-specificity identifiers for blocking; measure blocking recall later.",
        "- Do not use names, addresses, locations, dates of birth, or shared devices alone.",
        "- Keep raw values, profiling keys, and any later matching-normalization fields separate.",
        "- Rebuild the registry when source volumes or schemas change; frequency is data-dependent.",
        "",
        "This report makes no true-match decisions and implements no blocking, MCT scoring, fuzzy",
        "matching, clustering, dashboard, or final evaluation.",
        "",
    ]
    path.write_text("\n".join(report), encoding="utf-8")


def profile_identifiers(
    data_dir: Path,
    output_dir: Path,
    mapping_path: Path = DEFAULT_MAPPING,
    *,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Run isolated identifier profiling and write all Phase 1 outputs."""

    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    mapping = load_schema_mapping(Path(mapping_path))
    _validate_mapping(mapping)
    expected_counts = _expected_row_counts(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Keep the large scratch database outside a potentially synced repository (for example,
    # OneDrive). Only final deterministic artifacts belong in the requested output directory.
    temporary = tempfile.NamedTemporaryFile(prefix="kestrel-profiling-", suffix=".sqlite", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()

    store = FrequencyStore(temporary_path)
    states: dict[tuple[str, str, str], ColumnState] = defaultdict(ColumnState)
    source_rows: list[dict[str, Any]] = []
    try:
        for source, spec in mapping["sources"].items():
            if show_progress:
                print(f"[profile] Reading {source} ({spec['path']})...")
            column_buffer: list[tuple[str, str, str, str, str, str]] = []
            record_buffer: list[tuple[str, int, str, str, str, str, str]] = []
            row_count = 0
            for row_count, record in enumerate(
                iter_source_records(data_dir, source, spec), start=1
            ):
                record_concepts: dict[tuple[str, str], tuple[str, str]] = {}
                profiling_fields = [
                    (spec["record_id"], "source_record_id"),
                    *spec["identifiers"].items(),
                ]
                for raw_field, concept in profiling_fields:
                    state = states[(source, raw_field, concept)]
                    state.total_count += 1
                    raw_value = get_raw_value(record.raw, raw_field)
                    key, transformation = make_profiling_key(concept, raw_value)
                    if key is None:
                        state.missing_count += 1
                        continue
                    raw_text = str(raw_value)
                    column_buffer.append(
                        (source, raw_field, concept, raw_text, key, transformation)
                    )
                    record_concepts.setdefault((concept, key), (transformation, raw_text))

                for (concept, key), (transformation, raw_text) in record_concepts.items():
                    record_buffer.append(
                        (
                            source,
                            row_count,
                            record.source_record_id,
                            concept,
                            key,
                            transformation,
                            raw_text,
                        )
                    )
                if row_count % BATCH_SIZE == 0:
                    store.add_batch(column_buffer, record_buffer)
                    column_buffer.clear()
                    record_buffer.clear()
            store.add_batch(column_buffer, record_buffer)

            expected = expected_counts.get(source) if expected_counts is not None else None
            if expected is not None and row_count != expected:
                raise ProfilingError(
                    f"Operational row-count mismatch for {source}: parsed {row_count:,}, "
                    f"generation report says {expected:,}"
                )
            source_rows.append(
                {
                    "source": source,
                    "path": spec["path"],
                    "format": spec["format"],
                    "parsed_row_count": row_count,
                    "expected_row_count": expected if expected is not None else "",
                    "row_count_reconciled": "yes" if expected is not None else "not supplied",
                }
            )
            if show_progress:
                print(f"[profile] {source}: {row_count:,} rows")

        if expected_counts is not None:
            configured = set(mapping["sources"])
            reported = set(expected_counts)
            if configured != reported:
                raise ProfilingError(
                    "Operational source list differs from generation report: "
                    f"configured={sorted(configured)}, reported={sorted(reported)}"
                )

        if show_progress:
            print("[profile] Aggregating global frequencies and applying Rule 2...")
        store.finalize()
        connection = store.connection
        column_profiles = _column_profiles(connection, states)
        concept_summaries = _concept_summaries(connection)
        registry = _build_registry(connection)
        pair_diagnostics = _pair_diagnostics(connection)
        schema_rows = _schema_rows(mapping)
        total_records = sum(int(row["parsed_row_count"]) for row in source_rows)
        summary = _data_quality_summary(
            total_records=total_records,
            source_rows=source_rows,
            column_profiles=column_profiles,
            concept_summaries=concept_summaries,
            registry=registry,
            pair_diagnostics=pair_diagnostics,
            mapping=mapping,
        )

        _write_csv(
            output_dir / "source_summary.csv",
            ["source", "path", "format", "parsed_row_count", "expected_row_count", "row_count_reconciled"],
            source_rows,
        )
        _write_csv(
            output_dir / "column_profile.csv",
            list(column_profiles[0]) if column_profiles else [],
            column_profiles,
        )
        frequency_rows = _write_identifier_frequency(
            connection, output_dir / "identifier_frequency.csv"
        )
        stakeholder_registry = [
            {key: value for key, value in entry.items() if key != "profiling_key"}
            for entry in registry
        ]
        worthless_headers = list(stakeholder_registry[0]) if stakeholder_registry else [
            "attribute_concept",
            "masked_display_value",
            "value_hash",
            "global_frequency",
            "frequency_by_source",
            "source_count",
            "rule2_status",
            "reason",
            "profiling_transformation",
            "affected_records",
            "potential_pair_incidences",
        ]
        flat_registry = []
        for entry in stakeholder_registry:
            row = dict(entry)
            row["frequency_by_source"] = json.dumps(row["frequency_by_source"], sort_keys=True)
            flat_registry.append(row)
        _write_csv(output_dir / "worthless_values.csv", worthless_headers, flat_registry)
        with (output_dir / "rule2_registry.json").open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "rule2_threshold": RULE2_THRESHOLD,
                    "strict_comparison": "global_frequency > 40",
                    "registry_count": len(registry),
                    "values": registry,
                },
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.write("\n")
        summary["identifier_frequency_rows"] = frequency_rows
        with (output_dir / "data_quality_summary.json").open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        _write_report(
            output_dir / "profiling_report.md",
            summary=summary,
            source_rows=source_rows,
            schema_rows=schema_rows,
            column_profiles=column_profiles,
            concept_summaries=concept_summaries,
            registry=registry,
        )
        if show_progress:
            print(
                f"[profile] Complete: {total_records:,} records, {len(registry):,} Rule 2 values, "
                f"{pair_diagnostics['potential_pair_incidences_removed_by_rule2']:,} "
                "potential pair incidences prevented"
            )
        return summary
    finally:
        store.close()
        temporary_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Profile identifiers and discover global Rule 2 worthless values."
    )
    parser.add_argument("--data-dir", type=Path, required=True, help="Directory containing normal sources")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for profiling outputs")
    parser.add_argument(
        "--schema-mapping",
        type=Path,
        default=DEFAULT_MAPPING,
        help="Canonical profiling schema mapping",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile_identifiers(args.data_dir, args.output_dir, args.schema_mapping)
    except (SourceReadError, ProfilingError, OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
