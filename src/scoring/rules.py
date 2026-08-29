"""Pure pair-feature and MCT scoring rules.

The scorer combines the strongest evidence in each independent family, subtracts explicit
conflicts, and applies the assessment's fixed MCT bands. No labelled data is accepted here.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.blocking.rules import email_skeleton


DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "mct_scoring.yaml"


class ScoringError(ValueError):
    """Raised when a scoring input or configuration violates the phase contract."""


@dataclass
class ScoringRecord:
    source: str
    ordinal: int
    source_record_id: str
    values: dict[str, set[str]] = field(default_factory=dict)
    roles: dict[tuple[str, str], set[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PairScore:
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]
    family_strengths: tuple[tuple[str, float], ...]
    positive_score: float
    conflict_penalty: float
    mct_score: float
    decision: str


def load_scoring_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    try:
        rules = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringError(f"Unable to load MCT scoring rules from {path}: {exc}") from exc
    required = {
        "version",
        "thresholds",
        "evidence_weights",
        "evidence_families",
        "conflict_penalties",
        "conflict_caps",
        "human_review_floor",
    }
    missing = required - set(rules) if isinstance(rules, dict) else required
    if missing:
        raise ScoringError(f"MCT scoring configuration is missing: {sorted(missing)}")
    auto = float(rules["thresholds"].get("auto_merge_minimum", -1))
    review = float(rules["thresholds"].get("human_review_minimum", -1))
    if not math.isclose(auto, 0.88) or not math.isclose(review, 0.62):
        raise ScoringError("The assessment requires exact MCT thresholds of 0.88 and 0.62")
    weights = rules["evidence_weights"]
    configured_features = {
        feature for features in rules["evidence_families"].values() for feature in features
    }
    if configured_features != set(weights):
        raise ScoringError("Every evidence feature must occur in exactly one configured family")
    if any(not 0 <= float(value) <= 1 for value in weights.values()):
        raise ScoringError("Evidence weights must lie between zero and one")
    return rules


def compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def person_names(values: Mapping[str, set[str]]) -> set[str]:
    names = {compact_text(value) for value in values.get("full_name", set())}
    for first in values.get("first_name", set()):
        for last in values.get("last_name", set()):
            names.add(compact_text(f"{first} {last}"))
    return {name for name in names if name}


def _usable(
    record: ScoringRecord, concept: str, worthless: set[tuple[str, str]]
) -> set[str]:
    return {
        value
        for value in record.values.get(concept, set())
        if (concept, value) not in worthless
    }


def _verified_emails(record: ScoringRecord, worthless: set[tuple[str, str]]) -> set[str]:
    return {
        value
        for value in _usable(record, "email", worthless)
        if "verified_identifier" in record.roles.get(("email", value), set())
    }


def _phone_suffixes(values: set[str]) -> set[str]:
    result = set()
    for value in values:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) >= 9:
            result.add(digits[-9:])
    return result


def _email_skeletons(values: set[str]) -> set[str]:
    return {item for value in values if (item := email_skeleton(value))}


def _email_hashes(values: set[str]) -> set[str]:
    return {hashlib.sha256(value.encode("utf-8")).hexdigest() for value in values}


def _numeric_references(values: set[str]) -> set[str]:
    return {value.lstrip("0") or "0" for value in values if value.isdigit()}


def _add_best_feature(
    candidates: dict[str, str], family: str, feature: str, weights: Mapping[str, Any]
) -> None:
    existing = candidates.get(family)
    if existing is None or float(weights[feature]) > float(weights[existing]):
        candidates[family] = feature


def _sets_conflict(left: set[str], right: set[str]) -> bool:
    return bool(left and right and left.isdisjoint(right))


def score_pair(
    left: ScoringRecord,
    right: ScoringRecord,
    worthless: set[tuple[str, str]],
    rules: Mapping[str, Any],
) -> PairScore:
    """Calculate an explainable MCT score for one candidate pair."""

    weights = rules["evidence_weights"]
    family_by_feature = {
        feature: family
        for family, features in rules["evidence_families"].items()
        for feature in features
    }
    selected: dict[str, str] = {}

    def evidence(feature: str) -> None:
        _add_best_feature(selected, family_by_feature[feature], feature, weights)

    if left.source == right.source and left.source_record_id == right.source_record_id:
        evidence("same_source_record_id")

    left_account = _usable(left, "account_reference", worthless)
    right_account = _usable(right, "account_reference", worthless)
    left_numeric_account = _numeric_references(left_account)
    right_numeric_account = _numeric_references(right_account)
    if left_account & right_account or left_numeric_account & right_numeric_account:
        evidence("exact_account_reference")

    left_provider = _usable(left, "provider_id", worthless)
    right_provider = _usable(right, "provider_id", worthless)
    if left_provider & right_provider:
        evidence("exact_provider_id")

    left_email = _usable(left, "email", worthless)
    right_email = _usable(right, "email", worthless)
    exact_email = left_email & right_email
    if exact_email:
        verified = _verified_emails(left, worthless) | _verified_emails(right, worthless)
        evidence("exact_verified_email" if exact_email & verified else "exact_email")
    elif _email_skeletons(left_email) & _email_skeletons(right_email):
        evidence("email_skeleton")

    left_hash = _usable(left, "hashed_email", worthless)
    right_hash = _usable(right, "hashed_email", worthless)
    if (
        left_hash & right_hash
        or _email_hashes(left_email) & right_hash
        or _email_hashes(right_email) & left_hash
    ):
        evidence("email_sha256_bridge")

    left_phone = _usable(left, "phone", worthless)
    right_phone = _usable(right, "phone", worthless)
    if left_phone & right_phone:
        evidence("exact_phone")
    elif _phone_suffixes(left_phone) & _phone_suffixes(right_phone):
        evidence("phone_suffix_9")

    left_device = _usable(left, "device_id", worthless)
    right_device = _usable(right, "device_id", worthless)
    if left_device & right_device:
        evidence("exact_device_id")

    left_payment = _usable(left, "payment_token", worthless)
    right_payment = _usable(right, "payment_token", worthless)
    if left_payment & right_payment:
        evidence("exact_payment_token")

    left_names = person_names(left.values)
    right_names = person_names(right.values)
    shared_names = left_names & right_names
    if shared_names:
        left_city = {compact_text(value) for value in left.values.get("city", set())}
        right_city = {compact_text(value) for value in right.values.get("city", set())}
        if left_city & right_city:
            evidence("name_city")
        if _usable(left, "date_of_birth", worthless) & _usable(right, "date_of_birth", worthless):
            evidence("name_date_of_birth")
        if _usable(left, "postcode", worthless) & _usable(right, "postcode", worthless):
            evidence("name_postcode")

    conflicts: set[str] = set()
    left_verified = _verified_emails(left, worthless)
    right_verified = _verified_emails(right, worthless)
    if _sets_conflict(left_numeric_account, right_numeric_account):
        conflicts.add("account_reference_conflict")
    if _sets_conflict(left_verified, right_verified):
        conflicts.add("verified_email_conflict")
    elif _sets_conflict(_email_skeletons(left_email), _email_skeletons(right_email)):
        conflicts.add("email_conflict")
    if _sets_conflict(_phone_suffixes(left_phone), _phone_suffixes(right_phone)):
        conflicts.add("phone_conflict")
    if _sets_conflict(
        _usable(left, "date_of_birth", worthless),
        _usable(right, "date_of_birth", worthless),
    ):
        conflicts.add("date_of_birth_conflict")
    if _sets_conflict(left_names, right_names):
        conflicts.add("name_conflict")
    if _sets_conflict(_usable(left, "country", worthless), _usable(right, "country", worthless)):
        conflicts.add("country_conflict")
    if (
        selected.get("email") == "exact_email"
        and selected.get("payment") == "exact_payment_token"
        and set(selected).issubset({"email", "payment"})
    ):
        conflicts.add("shared_email_payment_household_risk")

    family_strengths = tuple(
        sorted((family, float(weights[feature])) for family, feature in selected.items())
    )
    positive_score = 1.0
    for _family, strength in family_strengths:
        positive_score *= 1.0 - strength
    positive_score = 1.0 - positive_score if family_strengths else 0.0
    penalty = min(
        1.0,
        sum(float(rules["conflict_penalties"][conflict]) for conflict in conflicts),
    )
    score = max(0.0, positive_score - penalty)
    caps = rules["conflict_caps"]
    for conflict in conflicts:
        if conflict in caps:
            score = min(score, float(caps[conflict]))
    identity_conflicts = conflicts & {
        "account_reference_conflict",
        "verified_email_conflict",
        "email_conflict",
        "phone_conflict",
        "date_of_birth_conflict",
        "name_conflict",
    }
    if len(identity_conflicts) >= 2:
        score = min(score, float(caps["two_or_more_identity_conflicts"]))
    review_floor = rules["human_review_floor"]
    if (
        set(selected.values()) & set(review_floor["eligible_features"])
        and not conflicts & set(review_floor["disqualifying_conflicts"])
    ):
        score = max(score, float(review_floor["score"]))
    score = round(score, 6)
    positive_score = round(positive_score, 6)
    penalty = round(penalty, 6)
    auto = float(rules["thresholds"]["auto_merge_minimum"])
    review = float(rules["thresholds"]["human_review_minimum"])
    decision = "auto_merge" if score >= auto else "human_review" if score >= review else "leave_separate"
    return PairScore(
        evidence=tuple(sorted(selected.values())),
        conflicts=tuple(sorted(conflicts)),
        family_strengths=family_strengths,
        positive_score=positive_score,
        conflict_penalty=penalty,
        mct_score=score,
        decision=decision,
    )
