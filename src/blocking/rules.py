"""Pure, deterministic candidate-key rules.

The transformations in this module are candidate-discovery aids only. They neither
constitute pair evidence nor award a match score.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "blocking_rules.yaml"


class BlockingError(ValueError):
    """Raised when blocking inputs or configuration violate the contract."""


def load_blocking_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    try:
        rules = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlockingError(f"Unable to load blocking rules from {path}: {exc}") from exc
    required = {
        "version",
        "rule2_threshold",
        "maximum_block_size",
        "minimum_block_size",
        "exact_concepts",
        "derived_rules",
    }
    missing = required - set(rules)
    if missing:
        raise BlockingError(f"Blocking configuration is missing: {sorted(missing)}")
    if int(rules["rule2_threshold"]) != 40:
        raise BlockingError("The assessment requires the strict Rule 2 threshold to be 40")
    if int(rules["maximum_block_size"]) > int(rules["rule2_threshold"]):
        raise BlockingError("Derived blocks cannot exceed the Rule 2 threshold")
    if int(rules["minimum_block_size"]) < 2:
        raise BlockingError("Candidate blocks must contain at least two records")
    return rules


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _person_names(values: Mapping[str, set[str]]) -> set[str]:
    names = {_compact_text(value) for value in values.get("full_name", set())}
    for first in values.get("first_name", set()):
        for last in values.get("last_name", set()):
            names.add(_compact_text(f"{first} {last}"))
    return {name for name in names if name}


def email_skeleton(value: str) -> str | None:
    """Remove plus suffix and dots for discovery without changing stored normalization."""

    if value.count("@") != 1:
        return None
    local, domain = value.rsplit("@", 1)
    local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}" if local and domain else None


def derive_candidate_keys(
    values: Mapping[str, set[str]],
    normalized_frequencies: Mapping[tuple[str, str], int],
    rules: Mapping[str, Any],
) -> set[tuple[str, str]]:
    """Return candidate keys for one physical record without consulting labels."""

    keys: set[tuple[str, str]] = set()
    threshold = int(rules["rule2_threshold"])
    minimum = int(rules["minimum_block_size"])
    for concept in rules["exact_concepts"]:
        for value in values.get(str(concept), set()):
            frequency = normalized_frequencies.get((str(concept), value), 0)
            if minimum <= frequency <= threshold:
                keys.add((f"exact_{concept}", value))

    enabled = rules["derived_rules"]
    if enabled.get("email_skeleton"):
        for value in values.get("email", set()):
            skeleton = email_skeleton(value)
            if skeleton:
                keys.add(("email_skeleton", skeleton))

    if enabled.get("email_sha256_bridge"):
        for value in values.get("email", set()):
            keys.add(("email_sha256_bridge", hashlib.sha256(value.encode("utf-8")).hexdigest()))
        for value in values.get("hashed_email", set()):
            keys.add(("email_sha256_bridge", value.casefold()))

    if enabled.get("phone_suffix_9"):
        for value in values.get("phone", set()):
            digits = "".join(character for character in value if character.isdigit())
            if len(digits) >= 9:
                keys.add(("phone_suffix_9", digits[-9:]))

    if enabled.get("numeric_account_reference"):
        for value in values.get("account_reference", set()):
            if value.isdigit():
                keys.add(("numeric_account_reference", value.lstrip("0") or "0"))

    names = _person_names(values)
    composite_specs = (
        ("name_city", "city"),
        ("name_date_of_birth", "date_of_birth"),
        ("name_postcode", "postcode"),
    )
    for rule_name, concept in composite_specs:
        if not enabled.get(rule_name):
            continue
        for name in names:
            for value in values.get(concept, set()):
                component = _compact_text(value)
                if component:
                    keys.add((rule_name, f"{name}\x1f{component}"))
    return keys
