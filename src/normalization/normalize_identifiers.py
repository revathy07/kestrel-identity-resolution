"""Create derived normalized identifiers while preserving every raw source value.

This module implements only normalization. It does not create candidate pairs, compare two
records, calculate MCT, make match decisions, or form clusters.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.ingestion.read_sources import (
    SourceReadError,
    get_raw_value,
    iter_source_records,
    load_schema_mapping,
)
from src.normalization.rules import (
    DEFAULT_RULES,
    NormalizationError,
    load_normalization_rules,
    normalize_value,
)
from src.profiling.profile_identifiers import DEFAULT_MAPPING
from src.profiling.rule2_registry import make_profiling_key


NORMALIZER_VERSION = 1
OUTPUT_COLUMNS = [
    "source",
    "record_ordinal",
    "source_record_id",
    "raw_field",
    "canonical_concept",
    "raw_value",
    "profiling_key",
    "normalized_value",
    "normalization_status",
    "normalization_changed",
    "transformation",
    "quality_flags",
    "evidence_role",
    "normalizer_version",
]


@dataclass
class FieldStats:
    total_count: int = 0
    missing_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    changed_count: int = 0
    quality_flagged_count: int = 0
    transformations: Counter[str] = field(default_factory=Counter)
    quality_flags: Counter[str] = field(default_factory=Counter)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprints(data_dir: Path, mapping: Mapping[str, Any]) -> dict[str, Any]:
    fingerprints: dict[str, Any] = {}
    for source, spec in mapping["sources"].items():
        path = data_dir / spec["path"]
        if not path.exists():
            raise SourceReadError(f"Required source file not found: {path}")
        fingerprints[source] = {
            "relative_path": spec["path"],
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    return fingerprints


def _configuration_hash(mapping_path: Path, rules_path: Path) -> str:
    digest = hashlib.sha256()
    for path in (mapping_path, rules_path):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _expected_row_counts(data_dir: Path) -> dict[str, int] | None:
    report_path = data_dir / "generation_report.json"
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        counts = report["row_counts"]
        return {str(source): int(count) for source, count in counts.items()}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise NormalizationError(f"Invalid operational row counts in {report_path}: {exc}") from exc


def _open_deterministic_gzip_csv(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def _field_rows(
    source: str, spec: Mapping[str, Any]
) -> list[tuple[str, str, str]]:
    rows = [(str(spec["record_id"]), "source_record_id", "source_record_key")]
    for raw_field, concept in spec["identifiers"].items():
        role = (
            "verified_identifier"
            if source == "social_logins" and raw_field.endswith(".verified_email")
            else "observed_identifier"
        )
        rows.append((str(raw_field), str(concept), role))
    return rows


def _summary_rows(
    stats: Mapping[tuple[str, str, str], FieldStats]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (source, raw_field, concept), item in sorted(stats.items()):
        rows.append(
            {
                "source": source,
                "raw_field": raw_field,
                "canonical_concept": concept,
                "total_count": item.total_count,
                "missing_count": item.missing_count,
                "missing_percentage": round(100 * item.missing_count / item.total_count, 6)
                if item.total_count
                else 0.0,
                "valid_count": item.valid_count,
                "valid_percentage": round(100 * item.valid_count / item.total_count, 6)
                if item.total_count
                else 0.0,
                "invalid_count": item.invalid_count,
                "invalid_percentage": round(100 * item.invalid_count / item.total_count, 6)
                if item.total_count
                else 0.0,
                "changed_count": item.changed_count,
                "changed_percentage_of_valid": round(100 * item.changed_count / item.valid_count, 6)
                if item.valid_count
                else 0.0,
                "quality_flagged_count": item.quality_flagged_count,
                "transformations": json.dumps(dict(sorted(item.transformations.items())), sort_keys=True),
            }
        )
    return rows


def _issue_rows(
    stats: Mapping[tuple[str, str, str], FieldStats]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (source, raw_field, concept), item in sorted(stats.items()):
        for quality_flag, count in item.quality_flags.most_common():
            rows.append(
                {
                    "source": source,
                    "raw_field": raw_field,
                    "canonical_concept": concept,
                    "quality_flag": quality_flag,
                    "affected_observations": count,
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fallback_headers: list[str]) -> None:
    headers = list(rows[0]) if rows else fallback_headers
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
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
    manifest: Mapping[str, Any],
    summary_rows: list[dict[str, Any]],
    issue_rows: list[dict[str, Any]],
    rules: Mapping[str, Any],
) -> None:
    highest_missing = sorted(
        summary_rows,
        key=lambda row: (-row["missing_percentage"], row["source"], row["raw_field"]),
    )[:10]
    highest_invalid = sorted(
        (row for row in summary_rows if row["invalid_count"]),
        key=lambda row: (-row["invalid_count"], row["source"], row["raw_field"]),
    )[:10]
    top_issues = sorted(
        issue_rows,
        key=lambda row: (-row["affected_observations"], row["quality_flag"]),
    )[:15]
    status = manifest["status_counts"]
    report = [
        "# Derived identifier-normalization report",
        "",
        "## Executive summary",
        "",
        f"- **Source records processed:** {manifest['total_source_records']:,}",
        f"- **Identifier observations emitted:** {manifest['identifier_observations']:,}",
        f"- **Valid observations:** {status.get('valid', 0):,}",
        f"- **Missing observations:** {status.get('missing', 0):,}",
        f"- **Invalid observations:** {status.get('invalid', 0):,}",
        f"- **Valid values changed by normalization:** {manifest['changed_observations']:,}",
        f"- **Observations carrying at least one quality flag:** {manifest['quality_flagged_observations']:,}",
        "- **Raw source files modified:** no; before/after SHA-256 fingerprints match",
        "",
        "The output is a derived, long-form identifier table. It contains no candidate pairs,",
        "pair similarities, MCT scores, match decisions, clusters, or evaluation labels.",
        "",
        "## Normalization principles",
        "",
        *[f"- {principle}" for principle in rules["principles"]],
        "",
        "## Concept strategies",
        "",
        _markdown_table(
            ["Canonical concept", "Strategy"],
            [[concept, strategy] for concept, strategy in sorted(rules["concept_strategies"].items())],
        ),
        "",
        "Email dots and plus suffixes remain intact. Phones lose only safe display punctuation;",
        "a missing country code is never inferred. Names and addresses use Unicode, case and",
        "whitespace handling only—no fuzzy comparison is performed. Country aliases map to ISO",
        "two-letter codes. DOB parsing emits ISO dates and flags implausible ages without repairing them.",
        "",
        "## Highest missingness",
        "",
        _markdown_table(
            ["Source", "Field", "Concept", "Missing", "Missing %"],
            [
                [
                    row["source"],
                    row["raw_field"],
                    row["canonical_concept"],
                    f"{row['missing_count']:,}",
                    f"{row['missing_percentage']:.2f}%",
                ]
                for row in highest_missing
            ],
        ),
        "",
        "## Invalid-value summary",
        "",
        (
            _markdown_table(
                ["Source", "Field", "Concept", "Invalid", "Invalid %"],
                [
                    [
                        row["source"],
                        row["raw_field"],
                        row["canonical_concept"],
                        f"{row['invalid_count']:,}",
                        f"{row['invalid_percentage']:.2f}%",
                    ]
                    for row in highest_invalid
                ],
            )
            if highest_invalid
            else "No non-missing values failed the declared structural validation rules."
        ),
        "",
        "## Quality flags",
        "",
        (
            _markdown_table(
                ["Source", "Field", "Concept", "Flag", "Observations"],
                [
                    [
                        row["source"],
                        row["raw_field"],
                        row["canonical_concept"],
                        row["quality_flag"],
                        f"{row['affected_observations']:,}",
                    ]
                    for row in top_issues
                ],
            )
            if top_issues
            else "No quality flags were emitted."
        ),
        "",
        "Quality flags preserve uncertainty. A structurally valid value may still be marked as",
        "having an unknown phone country code, an export annotation, a symbol, or an implausible DOB.",
        "The value is not silently repaired beyond the documented transformation.",
        "",
        "## Data lineage and reproducibility",
        "",
        f"- Normalizer version: `{manifest['normalizer_version']}`",
        f"- Configuration SHA-256: `{manifest['configuration_sha256']}`",
        f"- Normalized table SHA-256: `{manifest['normalized_output']['sha256']}`",
        f"- Compressed table size: {manifest['normalized_output']['size_bytes']:,} bytes",
        "- Source fingerprints: recorded in `normalization_manifest.json`",
        "",
        "## Boundary for the next phase",
        "",
        "The normalized table is suitable input for candidate blocking. Before a normalized value",
        "is allowed to create candidates or contribute evidence, the later phase must apply Rule 2",
        "using global frequencies. This phase itself performs no matching or scoring.",
        "",
    ]
    path.write_text("\n".join(report), encoding="utf-8")


def normalize_identifiers(
    data_dir: Path,
    output_dir: Path,
    schema_mapping_path: Path = DEFAULT_MAPPING,
    rules_path: Path = DEFAULT_RULES,
    *,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Normalize every mapped identifier and write deterministic Phase 4 outputs."""

    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    schema_mapping_path = Path(schema_mapping_path)
    rules_path = Path(rules_path)
    mapping = load_schema_mapping(schema_mapping_path)
    rules = load_normalization_rules(rules_path)
    concepts = set(mapping["canonical_concepts"])
    configured = set(rules["concept_strategies"])
    if concepts != configured:
        raise NormalizationError(
            "Normalization strategy coverage differs from schema concepts: "
            f"missing={sorted(concepts - configured)}, unknown={sorted(configured - concepts)}"
        )
    expected_counts = _expected_row_counts(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    before_fingerprints = _source_fingerprints(data_dir, mapping)

    normalized_path = output_dir / "normalized_identifiers.csv.gz"
    binary_handle, text_handle, writer = _open_deterministic_gzip_csv(normalized_path)
    stats: dict[tuple[str, str, str], FieldStats] = defaultdict(FieldStats)
    source_counts: dict[str, int] = {}
    status_counts: Counter[str] = Counter()
    identifier_observations = 0
    changed_observations = 0
    quality_flagged_observations = 0
    try:
        for source, spec in mapping["sources"].items():
            if show_progress:
                print(f"[normalize] Reading {source} ({spec['path']})...")
            row_count = 0
            fields = _field_rows(source, spec)
            for row_count, record in enumerate(
                iter_source_records(data_dir, source, spec), start=1
            ):
                for raw_field, concept, role in fields:
                    raw_value = get_raw_value(record.raw, raw_field)
                    result = normalize_value(concept, raw_value, rules)
                    profiling_key, _ = make_profiling_key(concept, raw_value)
                    raw_text = "" if raw_value is None else str(raw_value)
                    changed = (
                        result.status == "valid"
                        and result.normalized_value is not None
                        and result.normalized_value != raw_text
                    )
                    writer.writerow(
                        {
                            "source": source,
                            "record_ordinal": row_count,
                            "source_record_id": record.source_record_id,
                            "raw_field": raw_field,
                            "canonical_concept": concept,
                            "raw_value": raw_text,
                            "profiling_key": profiling_key or "",
                            "normalized_value": result.normalized_value or "",
                            "normalization_status": result.status,
                            "normalization_changed": "true" if changed else "false",
                            "transformation": result.transformation,
                            "quality_flags": ";".join(result.quality_flags),
                            "evidence_role": role,
                            "normalizer_version": NORMALIZER_VERSION,
                        }
                    )
                    item = stats[(source, raw_field, concept)]
                    item.total_count += 1
                    item.transformations[result.transformation] += 1
                    status_counts[result.status] += 1
                    if result.status == "missing":
                        item.missing_count += 1
                    elif result.status == "valid":
                        item.valid_count += 1
                    else:
                        item.invalid_count += 1
                    if changed:
                        item.changed_count += 1
                        changed_observations += 1
                    if result.quality_flags:
                        item.quality_flagged_count += 1
                        quality_flagged_observations += 1
                    for quality_flag in result.quality_flags:
                        item.quality_flags[quality_flag] += 1
                    identifier_observations += 1
            expected = expected_counts.get(source) if expected_counts is not None else None
            if expected is not None and row_count != expected:
                raise NormalizationError(
                    f"Operational row-count mismatch for {source}: parsed {row_count:,}, "
                    f"expected {expected:,}"
                )
            source_counts[source] = row_count
            if show_progress:
                print(f"[normalize] {source}: {row_count:,} records")
    finally:
        text_handle.close()
        binary_handle.close()

    after_fingerprints = _source_fingerprints(data_dir, mapping)
    if before_fingerprints != after_fingerprints:
        raise NormalizationError("At least one raw source fingerprint changed during normalization")

    summary_rows = _summary_rows(stats)
    issue_rows = _issue_rows(stats)
    _write_csv(
        output_dir / "normalization_summary.csv",
        summary_rows,
        [
            "source",
            "raw_field",
            "canonical_concept",
            "total_count",
            "missing_count",
            "missing_percentage",
            "valid_count",
            "valid_percentage",
            "invalid_count",
            "invalid_percentage",
            "changed_count",
            "changed_percentage_of_valid",
            "quality_flagged_count",
            "transformations",
        ],
    )
    _write_csv(
        output_dir / "normalization_issues.csv",
        issue_rows,
        ["source", "raw_field", "canonical_concept", "quality_flag", "affected_observations"],
    )
    manifest: dict[str, Any] = {
        "phase": "derived_identifier_normalization",
        "normalizer_version": NORMALIZER_VERSION,
        "total_source_records": sum(source_counts.values()),
        "source_counts": source_counts,
        "identifier_observations": identifier_observations,
        "status_counts": dict(sorted(status_counts.items())),
        "changed_observations": changed_observations,
        "quality_flagged_observations": quality_flagged_observations,
        "configuration_sha256": _configuration_hash(schema_mapping_path, rules_path),
        "source_fingerprints_before_and_after": before_fingerprints,
        "source_files_unchanged": True,
        "normalized_output": {
            "path": normalized_path.name,
            "compression": "gzip",
            "rows": identifier_observations,
            "size_bytes": normalized_path.stat().st_size,
            "sha256": _sha256(normalized_path),
        },
        "phase_boundaries": {
            "candidate_pairs_created": False,
            "fuzzy_similarity_calculated": False,
            "mct_scores_calculated": False,
            "match_decisions_created": False,
            "clusters_created": False,
        },
    }
    with (output_dir / "normalization_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    _write_report(
        output_dir / "normalization_report.md",
        manifest=manifest,
        summary_rows=summary_rows,
        issue_rows=issue_rows,
        rules=rules,
    )
    if show_progress:
        print(
            f"[normalize] Complete: {manifest['total_source_records']:,} records, "
            f"{identifier_observations:,} identifier observations, "
            f"{status_counts.get('invalid', 0):,} invalid"
        )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create derived normalized identifiers without matching records."
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--schema-mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--normalization-rules", type=Path, default=DEFAULT_RULES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        normalize_identifiers(
            args.data_dir,
            args.output_dir,
            args.schema_mapping,
            args.normalization_rules,
        )
    except (SourceReadError, NormalizationError, OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
