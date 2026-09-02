"""Estimate human customers from frozen clusters without changing operational merges."""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.ingestion.read_sources import get_raw_value, iter_source_records, load_schema_mapping
from src.profiling.rule2_registry import is_missing


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "business_estimation.yaml"
DEFAULT_MAPPING = Path(__file__).resolve().parents[2] / "config" / "schema_mapping.yaml"
CLASSIFICATION_COLUMNS = [
    "source",
    "record_ordinal",
    "source_record_id",
    "final_cluster_id",
    "observable_policy",
    "signals",
]


class BusinessEstimationError(ValueError):
    """Raised when a business estimate cannot be reproduced safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessEstimationError(f"Unable to load business-estimation config: {exc}") from exc
    scenario = config.get("latent_match_scenario", {})
    boundaries = scenario.get("score_bin_boundaries")
    if not isinstance(boundaries, list) or boundaries != sorted(set(boundaries)):
        raise BusinessEstimationError("Score-bin boundaries must be a sorted unique list")
    if boundaries[0] != 0.0 or boundaries[-1] != 0.88:
        raise BusinessEstimationError("Latent-match bins must cover [0, 0.88)")
    if scenario.get("rule1_maximum_source_records") != 12:
        raise BusinessEstimationError("Rule 1 maximum must remain 12")
    if scenario.get("simulations") != 500 or scenario.get("random_seed") != 20260902:
        raise BusinessEstimationError("Simulation count and seed differ from the frozen design")
    return config


def parse_timestamp(value: Any) -> datetime | None:
    """Parse the documented mixed timestamp formats into UTC."""

    if is_missing(value):
        return None
    text = str(value).strip()
    try:
        if len(text) == 13 and text.isdigit():
            return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
        if "T" in text and (text.endswith("Z") or "+" in text[10:] or "-" in text[10:]):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        if len(text) == 19 and text[4] == "-" and text[7] == "-":
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            return parsed.replace(tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc)
        formats = (
            ("%d-%m-%Y %H:%M:%S", 19),
            ("%Y/%m/%d %H:%M:%S", 19),
            ("%m-%d-%y %H:%M", 14),
        )
        for fmt, length in formats:
            if len(text) == length:
                try:
                    return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
    except (OverflowError, OSError, ValueError):
        return None
    return None


def latest_dense_window(
    timestamps: Sequence[datetime],
    *,
    window_seconds: int,
    minimum_count: int,
) -> tuple[datetime, datetime, int]:
    """Return the latest qualifying rolling window, avoiding a hard-coded anchor."""

    ordered = sorted(timestamps)
    if not ordered or minimum_count <= 0:
        raise BusinessEstimationError("Dense-window detection requires timestamps and a positive count")
    left = 0
    candidates: list[tuple[datetime, int, datetime]] = []
    width = timedelta(seconds=window_seconds)
    for right, value in enumerate(ordered):
        while value - ordered[left] > width:
            left += 1
        count = right - left + 1
        if count >= minimum_count:
            candidates.append((value, count, value - width))
    if not candidates:
        raise BusinessEstimationError(
            f"No timestamp window contains the required {minimum_count:,} records"
        )
    end, count, start = max(candidates, key=lambda item: (item[0], item[1]))
    return start, end, count


def _flatten_scalars(value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_scalars(nested, path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _flatten_scalars(nested, f"{prefix}[{index}]")
    elif value is not None:
        yield prefix.casefold(), str(value).strip()


def qa_signals(raw: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, ...]:
    domains = tuple(str(value).casefold() for value in policy["email_domain_suffixes"])
    name_tokens = tuple(str(value).casefold() for value in policy["name_tokens"])
    signals: set[str] = set()
    for path, value in _flatten_scalars(raw):
        lowered = value.casefold()
        if "email" in path and "@" in lowered and lowered.rsplit("@", 1)[1].endswith(domains):
            signals.add("test_email_domain")
        if any(token in lowered for token in name_tokens) and any(
            token in path for token in ("name", "first", "last", "display")
        ):
            signals.add("test_name_token")
    return tuple(sorted(signals))


def automation_signals(
    raw: Mapping[str, Any],
    rule: Mapping[str, Any],
    timestamp: datetime | None,
    window: tuple[datetime, datetime],
) -> tuple[str, ...]:
    if timestamp is None or not window[0] <= timestamp <= window[1]:
        return ()
    signals = ["dense_timestamp_window"]
    for field in rule.get("required_missing_fields", []):
        if not is_missing(get_raw_value(raw, field)):
            return ()
        signals.append(f"missing:{field}")
    if "maximum_engagement" in rule:
        try:
            engagement = float(get_raw_value(raw, "engagement_count"))
        except (TypeError, ValueError):
            return ()
        if engagement > float(rule["maximum_engagement"]):
            return ()
        signals.append("low_engagement")
    for field, accepted in rule.get("required_values", {}).items():
        value = str(get_raw_value(raw, field) or "").casefold()
        if value not in {str(item).casefold() for item in accepted}:
            return ()
        signals.append(f"value:{field}")
    comparison = rule.get("comparison_timestamp_field")
    if comparison:
        other = parse_timestamp(get_raw_value(raw, str(comparison)))
        if other is None:
            return ()
        delay = abs((timestamp - other).total_seconds())
        if delay > float(rule["maximum_absolute_delay_seconds"]):
            return ()
        signals.append("zero_or_short_event_delay")
    return tuple(sorted(signals))


def _load_assignments(
    path: Path,
) -> tuple[dict[tuple[str, int], tuple[str, str]], dict[str, int], dict[str, Counter[str]]]:
    records: dict[tuple[str, int], tuple[str, str]] = {}
    cluster_sizes: Counter[str] = Counter()
    cluster_sources: dict[str, Counter[str]] = defaultdict(Counter)
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"source", "record_ordinal", "source_record_id", "final_cluster_id"}
            fields = set(reader.fieldnames or [])
            if not required.issubset(fields):
                raise BusinessEstimationError(f"Assignments missing: {sorted(required - fields)}")
            for row in reader:
                cluster = row["final_cluster_id"]
                if not cluster:
                    raise BusinessEstimationError("Business estimate requires accepted final cluster IDs")
                key = (row["source"], int(row["record_ordinal"]))
                if key in records:
                    raise BusinessEstimationError(f"Duplicate assignment key: {key}")
                records[key] = (row["source_record_id"], cluster)
                cluster_sizes[cluster] += 1
                cluster_sources[cluster][row["source"]] += 1
    except OSError as exc:
        raise BusinessEstimationError(f"Unable to load assignments: {exc}") from exc
    return records, dict(cluster_sizes), cluster_sources


def _open_classifications(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=CLASSIFICATION_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def classify_observable_traffic(
    data_dir: Path,
    mapping_path: Path,
    assignments_path: Path,
    output_path: Path,
    config: Mapping[str, Any],
    *,
    show_progress: bool = True,
) -> dict[str, Any]:
    mapping = load_schema_mapping(mapping_path)
    assignments, cluster_sizes, cluster_sources = _load_assignments(assignments_path)
    automation_policy = config["automation_policy"]
    qa_policy = config["internal_qa_policy"]
    policy_by_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    windows: dict[str, dict[str, Any]] = {}
    binary, text_handle, writer = _open_classifications(output_path)
    classified_records = 0
    try:
        for source, spec in mapping["sources"].items():
            records = list(iter_source_records(data_dir, source, spec))
            rule = automation_policy["sources"][source]
            parsed = [parse_timestamp(get_raw_value(record.raw, rule["timestamp_field"])) for record in records]
            valid = [value for value in parsed if value is not None]
            minimum = max(1, math.ceil(len(records) * float(automation_policy["minimum_source_fraction"])))
            start, end, dense_count = latest_dense_window(
                valid,
                window_seconds=int(automation_policy["window_seconds"]),
                minimum_count=minimum,
            )
            windows[source] = {
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "records_in_latest_qualifying_window": dense_count,
                "minimum_qualifying_records": minimum,
                "parseable_timestamps": len(valid),
            }
            tolerance = timedelta(
                seconds=int(automation_policy.get("window_boundary_tolerance_seconds", 0))
            )
            classification_window = (start - tolerance, end + tolerance)
            if show_progress:
                print(
                    f"[business] {source}: latest dense window {start.isoformat()} to "
                    f"{end.isoformat()}"
                )
            for ordinal, (record, timestamp) in enumerate(zip(records, parsed), start=1):
                key = (source, ordinal)
                expected = assignments.get(key)
                if expected is None or expected[0] != record.source_record_id:
                    raise BusinessEstimationError(f"Raw/assignment identity mismatch at {key}")
                qa = qa_signals(record.raw, qa_policy)
                automated = automation_signals(record.raw, rule, timestamp, classification_window)
                if qa:
                    policy, signals = "internal_qa", qa
                elif automated:
                    policy, signals = "automation", automated
                else:
                    policy, signals = "none", ()
                cluster = expected[1]
                policy_by_cluster[cluster][policy] += 1
                source_counts[source][policy] += 1
                writer.writerow(
                    {
                        "source": source,
                        "record_ordinal": ordinal,
                        "source_record_id": record.source_record_id,
                        "final_cluster_id": cluster,
                        "observable_policy": policy,
                        "signals": ";".join(signals),
                    }
                )
                classified_records += 1
    finally:
        text_handle.close()
        binary.close()
    if classified_records != len(assignments):
        raise BusinessEstimationError(
            f"Classified {classified_records:,} records but assignments contain {len(assignments):,}"
        )
    excluded_automation: set[str] = set()
    excluded_qa: set[str] = set()
    mixed_policy: set[str] = set()
    for cluster, counts in policy_by_cluster.items():
        size = cluster_sizes[cluster]
        if counts["automation"] == size:
            excluded_automation.add(cluster)
        elif counts["internal_qa"] == size:
            excluded_qa.add(cluster)
        elif counts["automation"] or counts["internal_qa"]:
            mixed_policy.add(cluster)
    return {
        "records_classified": classified_records,
        "operational_clusters": len(cluster_sizes),
        "cluster_sizes": cluster_sizes,
        "cluster_sources": cluster_sources,
        "excluded_automation_clusters": excluded_automation,
        "excluded_internal_qa_clusters": excluded_qa,
        "mixed_policy_clusters_retained": mixed_policy,
        "source_counts": source_counts,
        "timestamp_windows": windows,
        "classification_sha256": _sha256(output_path),
    }


def score_bin_index(score: float, boundaries: Sequence[float]) -> int:
    if not boundaries[0] <= score < boundaries[-1]:
        raise BusinessEstimationError(f"Unresolved score {score} is outside configured bins")
    return bisect.bisect_right(boundaries, score) - 1


def calibrate_unresolved_bins(
    labelled_test_path: Path,
    boundaries: Sequence[float],
    alpha: float,
    beta: float,
) -> list[dict[str, Any]]:
    counters: dict[int, Counter[str]] = defaultdict(Counter)
    try:
        with gzip.open(labelled_test_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"mct_score", "decision", "truth_label", "partition"}
            fields = set(reader.fieldnames or [])
            if not required.issubset(fields):
                raise BusinessEstimationError(f"Test labels missing: {sorted(required - fields)}")
            for number, row in enumerate(reader, start=1):
                if row["partition"] != "test":
                    raise BusinessEstimationError(f"Calibration row {number} is not frozen test")
                if row["decision"] == "auto_merge":
                    continue
                index = score_bin_index(float(row["mct_score"]), boundaries)
                counters[index]["pairs"] += 1
                counters[index]["matches" if row["truth_label"] == "match" else "nonmatches"] += 1
    except OSError as exc:
        raise BusinessEstimationError(f"Unable to read test labels: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for index in range(len(boundaries) - 1):
        count = counters[index]
        posterior_alpha = count["matches"] + alpha
        posterior_beta = count["nonmatches"] + beta
        rows.append(
            {
                "bin_index": index,
                "lower_inclusive": boundaries[index],
                "upper_exclusive": boundaries[index + 1],
                "test_pairs": count["pairs"],
                "test_matches": count["matches"],
                "test_nonmatches": count["nonmatches"],
                "observed_match_rate": count["matches"] / count["pairs"] if count["pairs"] else None,
                "posterior_alpha": posterior_alpha,
                "posterior_beta": posterior_beta,
                "posterior_mean_match_probability": posterior_alpha / (posterior_alpha + posterior_beta),
            }
        )
    return rows


def load_unresolved_cluster_edges(
    scored_path: Path,
    assignments: Mapping[tuple[str, int], tuple[str, str]],
    excluded_clusters: set[str],
    boundaries: Sequence[float],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    counters: Counter[str] = Counter()
    try:
        with gzip.open(scored_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "left_source", "left_record_ordinal", "right_source", "right_record_ordinal",
                "mct_score", "decision",
            }
            fields = set(reader.fieldnames or [])
            if not required.issubset(fields):
                raise BusinessEstimationError(f"Scored pairs missing: {sorted(required - fields)}")
            if "truth_label" in fields or any("person_id" in field.casefold() for field in fields):
                raise BusinessEstimationError("Business scenario scored input must be truth-free")
            for row in reader:
                if row["decision"] == "auto_merge":
                    continue
                left = assignments[(row["left_source"], int(row["left_record_ordinal"]))][1]
                right = assignments[(row["right_source"], int(row["right_record_ordinal"]))][1]
                counters["physical_unresolved_candidate_pairs"] += 1
                if left == right:
                    counters["already_same_operational_cluster"] += 1
                    continue
                if left in excluded_clusters or right in excluded_clusters:
                    counters["incident_to_excluded_traffic_cluster"] += 1
                    continue
                pair = tuple(sorted((left, right)))
                score = float(row["mct_score"])
                item = {
                    "left_cluster": pair[0],
                    "right_cluster": pair[1],
                    "score": score,
                    "decision": row["decision"],
                    "bin_index": score_bin_index(score, boundaries),
                }
                previous = best.get(pair)
                if previous is None or score > previous["score"]:
                    best[pair] = item
    except OSError as exc:
        raise BusinessEstimationError(f"Unable to read selected scores: {exc}") from exc
    edges = sorted(best.values(), key=lambda row: (row["left_cluster"], row["right_cluster"]))
    counters["unique_unresolved_cluster_pairs"] = len(edges)
    counters["unique_review_cluster_pairs"] = sum(row["decision"] == "human_review" for row in edges)
    counters["unique_separate_cluster_pairs"] = sum(row["decision"] == "leave_separate" for row in edges)
    return edges, counters


class UnionFind:
    def __init__(self, sizes: Sequence[int]) -> None:
        self.parent = list(range(len(sizes)))
        self.nodes = [1] * len(sizes)
        self.records = list(sizes)

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self.nodes[left_root] < self.nodes[right_root] or (
            self.nodes[left_root] == self.nodes[right_root] and left_root > right_root
        ):
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.nodes[left_root] += self.nodes[right_root]
        self.records[left_root] += self.records[right_root]


def simulate_counts(
    edges: Sequence[Mapping[str, Any]],
    cluster_sizes: Mapping[str, int],
    calibration: Sequence[Mapping[str, Any]],
    *,
    base_count: int,
    simulations: int,
    seed: int,
    maximum_records: int,
    scenario: str,
) -> list[dict[str, Any]]:
    selected_edges = [
        edge for edge in edges
        if scenario == "all_unresolved" or edge["decision"] == "human_review"
    ]
    nodes = sorted({str(edge["left_cluster"]) for edge in selected_edges} | {str(edge["right_cluster"]) for edge in selected_edges})
    lookup = {cluster: index for index, cluster in enumerate(nodes)}
    indexed_edges = [
        (lookup[str(edge["left_cluster"])], lookup[str(edge["right_cluster"])], int(edge["bin_index"]))
        for edge in selected_edges
    ]
    sizes = [int(cluster_sizes[cluster]) for cluster in nodes]
    rng = random.Random(seed)
    output: list[dict[str, Any]] = []
    for iteration in range(1, simulations + 1):
        probabilities = {
            int(row["bin_index"]): rng.betavariate(float(row["posterior_alpha"]), float(row["posterior_beta"]))
            for row in calibration
        }
        union_find = UnionFind(sizes)
        sampled_edges = 0
        for left, right, bin_index in indexed_edges:
            if rng.random() < probabilities[bin_index]:
                union_find.union(left, right)
                sampled_edges += 1
        reductions = 0
        oversized = 0
        roots = {union_find.find(index) for index in range(len(nodes))}
        for root in roots:
            if union_find.nodes[root] <= 1:
                continue
            if union_find.records[root] <= maximum_records:
                reductions += union_find.nodes[root] - 1
            else:
                oversized += 1
        output.append(
            {
                "scenario": scenario,
                "simulation": iteration,
                "sampled_edges": sampled_edges,
                "accepted_identity_reduction": reductions,
                "oversized_sampled_components": oversized,
                "estimated_identity_count": base_count - reductions,
            }
        )
    return output


def _percentile(values: Sequence[int], percentile: int) -> int:
    ordered = sorted(values)
    index = round((percentile / 100) * (len(ordered) - 1))
    return int(ordered[index])


def _scenario_summary(rows: Sequence[Mapping[str, Any]], percentiles: Sequence[int]) -> dict[str, Any]:
    counts = [int(row["estimated_identity_count"]) for row in rows]
    reductions = [int(row["accepted_identity_reduction"]) for row in rows]
    return {
        "simulations": len(rows),
        "identity_count_percentiles": {f"p{value:02d}": _percentile(counts, value) for value in percentiles},
        "identity_reduction_percentiles": {f"p{value:02d}": _percentile(reductions, value) for value in percentiles},
        "minimum_identity_count": min(counts),
        "maximum_identity_count": max(counts),
        "simulations_with_oversized_components": sum(int(row["oversized_sampled_components"]) > 0 for row in rows),
        "maximum_oversized_components": max(int(row["oversized_sampled_components"]) for row in rows),
    }


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _report(result: Mapping[str, Any]) -> str:
    counts = result["customer_count_estimate"]
    review = result["review_workload"]
    traffic = result["observable_traffic_exclusions"]
    return "\n".join(
        [
            "# Phase 13 customer-count and risk summary",
            "",
            "## Recommended business statement",
            "",
            f"Kestrel has an estimated **{counts['recommended_candidate_resolvable_count']:,} human customers** under the candidate-resolvable scenario. A defensible range is **{counts['defensible_range_lower']:,} to {counts['defensible_range_upper']:,}**. The lower end includes an explicit zero-evidence sensitivity; the upper end assumes no uncertain candidate link resolves after high-confidence traffic exclusions.",
            "",
            "This is an aggregate estimate, not permission to merge records below MCT 0.88. The operational identity table remains at 342,900 and keeps review/separate records distinct.",
            "",
            "## Count bridge",
            "",
            f"- Source records: **{counts['source_records']:,}**",
            f"- Selected operational identities: **{counts['operational_identities']:,}**",
            f"- Observable automation clusters excluded: **{traffic['automation_clusters']:,}**",
            f"- Observable internal-QA clusters excluded: **{traffic['internal_qa_clusters']:,}**",
            f"- Marketing-safe upper after exclusions: **{counts['marketing_safe_upper']:,}**",
            f"- Review-only median scenario: **{counts['review_only_median']:,}**",
            f"- All-candidate median scenario: **{counts['recommended_candidate_resolvable_count']:,}**",
            f"- Candidate statistical interval: **{counts['candidate_statistical_lower']:,}–{counts['candidate_statistical_upper']:,}**",
            f"- Zero-evidence lower sensitivity: **{counts['defensible_range_lower']:,}**",
            "",
            "## Marketing versus Finance",
            "",
            f"Marketing's 400,000 is closest to an account/record count and is {result['business_reference_comparison']['marketing_minus_recommended']:,} above the recommended estimate. Finance's 300,000 is {abs(result['business_reference_comparison']['finance_minus_recommended']):,} {'below' if result['business_reference_comparison']['finance_minus_recommended'] < 0 else 'above'} it. Marketing is counting duplicated system identities; Finance is directionally closer to people, but the evidence supports a range rather than an exact production total.",
            "",
            "## Review workload",
            "",
            f"The queue contains **{review['physical_review_pairs']:,} physical pairs** representing **{review['unique_review_cluster_pairs']:,} unique operational-cluster pairs**. At two minutes each this is **{review['two_minute_hours']:.1f} analyst hours ({review['two_minute_days']:.1f} eight-hour days)**; at five minutes it is **{review['five_minute_hours']:.1f} hours ({review['five_minute_days']:.1f} days)**. These are staffing scenarios, not measured handling times.",
            "",
            "## False-merge consequence",
            "",
            "A wrong merge can expose another person's orders, tickets, subscription relationship or address and can become a reportable privacy breach. The dataset provides no defensible currency cost, so none is invented. Rule 1 bounds an accepted automatic component at 12 source records, but a two-person merge is still unacceptable; monitoring, reversal tooling, incident investigation time, notification cost and regulatory/legal cost must be supplied before monetary expected loss can be calculated.",
            "",
            "## Method and limitations",
            "",
            "- Automation uses a discovered recent timestamp burst plus source-specific observable behaviour; no bot flag, hidden entity type, generator anchor or ID range is used.",
            "- QA uses explicit test-domain/name policy and excludes only wholly flagged clusters.",
            "- Frozen-test score-bin match rates drive 500 deterministic simulations with Jeffreys uncertainty.",
            "- Candidate edges are collapsed to unique operational-cluster pairs, sampled, unioned transitively and checked against Rule 1.",
            "- Simulations estimate aggregate people; they never rewrite operational clusters or accept below-threshold links.",
            "- The lower zero-evidence sensitivity is deliberately conservative and may overstate the possible reduction because canonical links can overlap.",
            "- Real production behaviour may differ from the synthetic fixture; ongoing labelled review and false-merge monitoring are required.",
            "",
        ]
    )


def estimate_customers(
    data_dir: Path,
    assignments_path: Path,
    scored_path: Path,
    labelled_test_path: Path,
    phase12_summary_path: Path,
    output_dir: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    mapping_path: Path = DEFAULT_MAPPING,
    show_progress: bool = True,
) -> dict[str, Any]:
    config = load_config(config_path)
    paths = (data_dir, assignments_path, scored_path, labelled_test_path, phase12_summary_path, config_path, mapping_path)
    for path in paths:
        if not Path(path).exists():
            raise BusinessEstimationError(f"Required Phase 13 input not found: {path}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    classification_path = output_dir / "observable_traffic_records.csv.gz"
    traffic = classify_observable_traffic(
        Path(data_dir), Path(mapping_path), Path(assignments_path), classification_path, config,
        show_progress=show_progress,
    )
    excluded = set(traffic["excluded_automation_clusters"]) | set(traffic["excluded_internal_qa_clusters"])
    base_count = traffic["operational_clusters"] - len(excluded)
    assignments, cluster_sizes, _cluster_sources = _load_assignments(Path(assignments_path))
    scenario = config["latent_match_scenario"]
    boundaries = [float(value) for value in scenario["score_bin_boundaries"]]
    smoothing = scenario["smoothing"]
    calibration = calibrate_unresolved_bins(
        Path(labelled_test_path), boundaries, float(smoothing["alpha"]), float(smoothing["beta"])
    )
    edges, edge_counts = load_unresolved_cluster_edges(
        Path(scored_path), assignments, excluded, boundaries
    )
    operational_bins: dict[int, Counter[str]] = defaultdict(Counter)
    for edge in edges:
        operational_bins[int(edge["bin_index"])]["cluster_pairs"] += 1
        operational_bins[int(edge["bin_index"])][str(edge["decision"])] += 1
    for row in calibration:
        counts = operational_bins[int(row["bin_index"])]
        row["operational_unique_cluster_pairs"] = counts["cluster_pairs"]
        row["operational_review_cluster_pairs"] = counts["human_review"]
        row["operational_separate_cluster_pairs"] = counts["leave_separate"]
    if show_progress:
        print(
            f"[business] Simulating {len(edges):,} unique unresolved cluster pairs "
            f"across {scenario['simulations']:,} scenarios"
        )
    review_rows = simulate_counts(
        edges, cluster_sizes, calibration,
        base_count=base_count,
        simulations=int(scenario["simulations"]),
        seed=int(scenario["random_seed"]),
        maximum_records=int(scenario["rule1_maximum_source_records"]),
        scenario="review_only",
    )
    all_rows = simulate_counts(
        edges, cluster_sizes, calibration,
        base_count=base_count,
        simulations=int(scenario["simulations"]),
        seed=int(scenario["random_seed"]) + 1,
        maximum_records=int(scenario["rule1_maximum_source_records"]),
        scenario="all_unresolved",
    )
    percentiles = [int(value) for value in scenario["interval_percentiles"]]
    review_summary = _scenario_summary(review_rows, percentiles)
    candidate_summary = _scenario_summary(all_rows, percentiles)
    phase12 = json.loads(Path(phase12_summary_path).read_text(encoding="utf-8"))
    zero_evidence_sensitivity = int(phase12["blocking_summary"]["blocked_all_links"])
    candidate_lower = candidate_summary["identity_count_percentiles"]["p05"]
    candidate_median = candidate_summary["identity_count_percentiles"]["p50"]
    candidate_upper = candidate_summary["identity_count_percentiles"]["p95"]
    lower_sensitivity = max(0, candidate_lower - zero_evidence_sensitivity)
    workload = config["review_workload"]
    review_pairs = int(phase12["operational_review_context"]["review_pairs"])
    hours = {minutes: review_pairs * minutes / 60 for minutes in workload["minutes_per_pair_scenarios"]}
    marketing = int(config["reported_business_reference_counts"]["marketing_users"])
    finance = int(config["reported_business_reference_counts"]["finance_people"])
    traffic_rows = [
        {
            "source": source,
            "records": sum(counts.values()),
            "observable_automation_records": counts["automation"],
            "observable_internal_qa_records": counts["internal_qa"],
            "unflagged_records": counts["none"],
        }
        for source, counts in sorted(traffic["source_counts"].items())
    ]
    result: dict[str, Any] = {
        "phase": "business_customer_count_estimation",
        "selected_operational_model": "logistic_regression_mct_l2_0.001_with_rule1",
        "customer_count_estimate": {
            "source_records": traffic["records_classified"],
            "operational_identities": traffic["operational_clusters"],
            "marketing_safe_upper": base_count,
            "review_only_median": review_summary["identity_count_percentiles"]["p50"],
            "candidate_statistical_lower": candidate_lower,
            "recommended_candidate_resolvable_count": candidate_median,
            "candidate_statistical_upper": candidate_upper,
            "zero_evidence_link_sensitivity": zero_evidence_sensitivity,
            "defensible_range_lower": lower_sensitivity,
            "defensible_range_upper": base_count,
            "range_includes_unobservable_duplicate_sensitivity": True,
        },
        "observable_traffic_exclusions": {
            "automation_clusters": len(traffic["excluded_automation_clusters"]),
            "automation_records": sum(cluster_sizes[cluster] for cluster in traffic["excluded_automation_clusters"]),
            "internal_qa_clusters": len(traffic["excluded_internal_qa_clusters"]),
            "internal_qa_records": sum(cluster_sizes[cluster] for cluster in traffic["excluded_internal_qa_clusters"]),
            "mixed_policy_clusters_retained": len(traffic["mixed_policy_clusters_retained"]),
            "timestamp_windows": traffic["timestamp_windows"],
            "cluster_exclusion_requires_all_members": True,
        },
        "unresolved_edge_context": dict(edge_counts),
        "review_only_scenario": review_summary,
        "all_unresolved_candidate_scenario": candidate_summary,
        "review_workload": {
            "physical_review_pairs": review_pairs,
            "unique_review_cluster_pairs": edge_counts["unique_review_cluster_pairs"],
            "two_minute_hours": hours[2],
            "two_minute_days": hours[2] / float(workload["analyst_workday_hours"]),
            "five_minute_hours": hours[5],
            "five_minute_days": hours[5] / float(workload["analyst_workday_hours"]),
            "handling_times_are_assumptions": True,
        },
        "business_reference_comparison": {
            "marketing_reported_users": marketing,
            "finance_reported_people": finance,
            "marketing_minus_recommended": marketing - candidate_median,
            "finance_minus_recommended": finance - candidate_median,
            "marketing_is_account_like_count": True,
            "finance_is_directionally_closer_to_people": abs(finance - candidate_median) < abs(marketing - candidate_median),
        },
        "false_merge_risk": {
            "observed_false_merged_pairs_in_synthetic_evaluation": phase12["cluster_summary"]["false_merged_pairs"],
            "maximum_accepted_source_records_under_rule1": 12,
            "currency_cost_estimated": False,
            "reason_no_currency_cost": "No incident, remediation, notification, legal, regulatory or customer-churn cost inputs were supplied.",
            "consequences": [
                "cross-customer order, ticket, subscription or address exposure",
                "reportable privacy breach assessment",
                "merge reversal and downstream data correction",
                "incident investigation and possible customer notification",
            ],
        },
        "inputs": {
            "assignments": {"path": _portable_path(assignments_path), "sha256": _sha256(assignments_path)},
            "selected_scores": {"path": _portable_path(scored_path), "sha256": _sha256(scored_path)},
            "frozen_test_labels": {"path": _portable_path(labelled_test_path), "sha256": _sha256(labelled_test_path)},
            "phase12_summary": {"path": _portable_path(phase12_summary_path), "sha256": _sha256(phase12_summary_path)},
            "configuration": {"path": _portable_path(config_path), "sha256": _sha256(config_path)},
            "schema_mapping": {"path": _portable_path(mapping_path), "sha256": _sha256(mapping_path)},
        },
        "classification_output": {
            "path": _portable_path(classification_path),
            "rows": traffic["records_classified"],
            "sha256": traffic["classification_sha256"],
            "hidden_labels_included": False,
        },
        "isolation": {
            "person_map_read": False,
            "entity_type_read": False,
            "hidden_population_total_used": False,
            "operational_clusters_modified": False,
            "below_threshold_edges_operationally_merged": False,
            "simulation_is_aggregate_only": True,
        },
    }
    _write_csv(
        output_dir / "observable_traffic_summary.csv",
        traffic_rows,
        ["source", "records", "observable_automation_records", "observable_internal_qa_records", "unflagged_records"],
    )
    _write_csv(
        output_dir / "score_bin_match_rates.csv",
        calibration,
        [
            "bin_index", "lower_inclusive", "upper_exclusive", "test_pairs", "test_matches",
            "test_nonmatches", "observed_match_rate", "posterior_alpha", "posterior_beta",
            "posterior_mean_match_probability", "operational_unique_cluster_pairs",
            "operational_review_cluster_pairs", "operational_separate_cluster_pairs",
        ],
    )
    _write_csv(
        output_dir / "count_simulations.csv",
        [*review_rows, *all_rows],
        [
            "scenario", "simulation", "sampled_edges", "accepted_identity_reduction",
            "oversized_sampled_components", "estimated_identity_count",
        ],
    )
    (output_dir / "business_estimate.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / "business_estimate.md").write_text(_report(result), encoding="utf-8")
    if show_progress:
        print(
            f"[business] Complete: recommended {candidate_median:,}; "
            f"range {lower_sensitivity:,}–{base_count:,}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/generated"))
    parser.add_argument("--assignments", type=Path, default=Path("outputs/clustering/cluster_assignments.csv.gz"))
    parser.add_argument("--selected-scores", type=Path, default=Path("outputs/logistic/logistic_scored_candidate_pairs.csv.gz"))
    parser.add_argument("--frozen-test-labels", type=Path, default=Path("outputs/logistic/labelled_test_set.csv.gz"))
    parser.add_argument("--phase12-summary", type=Path, default=Path("outputs/evaluation/evaluation_summary.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/business"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--schema-mapping", type=Path, default=DEFAULT_MAPPING)
    args = parser.parse_args()
    try:
        estimate_customers(
            args.data_dir,
            args.assignments,
            args.selected_scores,
            args.frozen_test_labels,
            args.phase12_summary,
            args.output_dir,
            config_path=args.config,
            mapping_path=args.schema_mapping,
        )
    except BusinessEstimationError as exc:
        print(f"[business] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
