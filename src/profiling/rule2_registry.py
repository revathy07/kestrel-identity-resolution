"""Pure helpers for conservative profiling keys and Rule 2 registry entries."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any


RULE2_THRESHOLD = 40
MISSING_TEXT_TOKENS = frozenset({"", '""', "''", "null", "none"})
EMAIL_CONCEPTS = frozenset({"email", "hashed_email"})
PHONE_SAFE_CHARACTERS = re.compile(r"^[+\d\s().-]+$")
PHONE_FORMATTING = re.compile(r"[\s().-]+")


def is_missing(value: Any) -> bool:
    """Apply the documented missing semantics without changing the raw value."""

    if value is None:
        return True
    return str(value).strip().casefold() in MISSING_TEXT_TOKENS


def make_profiling_key(concept: str, value: Any) -> tuple[str | None, str]:
    """Return a conservative, phase-specific key and its named transformation.

    This is deliberately narrower than a matching normalizer. It does not remove email
    dots or plus suffixes, infer phone country codes, or apply fuzzy name/address logic.
    """

    if is_missing(value):
        return None, "missing-token exclusion"
    text = str(value).strip()
    if concept in EMAIL_CONCEPTS:
        return text.casefold(), "trim + case-fold"
    if concept == "phone" and PHONE_SAFE_CHARACTERS.fullmatch(text):
        return PHONE_FORMATTING.sub("", text), "trim + safe punctuation removal"
    return text, "trim only"


def deterministic_value_hash(concept: str, profiling_key: str) -> str:
    """Hash the concept and key so equal registry builds are byte-for-byte stable."""

    payload = f"{concept}\x00{profiling_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mask_display_value(concept: str, value: str) -> str:
    """Return a stakeholder-safe representation of an identifier value."""

    text = str(value)
    if concept == "email" and "@" in text:
        local, domain = text.split("@", 1)
        domain_parts = domain.split(".")
        local_mask = (local[:1] or "*") + "***"
        domain_mask = (domain_parts[0][:1] or "*") + "***"
        suffix = "." + ".".join(domain_parts[1:]) if len(domain_parts) > 1 else ""
        return f"{local_mask}@{domain_mask}{suffix}"
    if concept == "date_of_birth" and len(text) >= 4:
        year = text[:4] if text[:4].isdigit() else "****"
        return f"{year}-**-**"
    if concept == "country" and len(text) <= 3:
        return text[:1] + "**"
    if concept == "phone":
        return "*" * max(4, len(text) - 2) + text[-2:]
    if concept == "hashed_email":
        return f"{text[:6]}…{text[-4:]}" if len(text) > 12 else "***"
    if len(text) <= 2:
        return "*" * len(text)
    if len(text) <= 6:
        return text[:1] + "***"
    return f"{text[:3]}…{text[-2:]}"


def potential_pairs(frequency: int) -> int:
    """Return n choose 2 without constructing any candidate pairs."""

    if frequency < 2:
        return 0
    return frequency * (frequency - 1) // 2


def make_registry_entry(
    *,
    concept: str,
    profiling_key: str,
    representative_raw_value: str,
    global_frequency: int,
    frequency_by_source: Mapping[str, int],
    transformation: str,
) -> dict[str, Any]:
    """Build one deterministic machine-readable Rule 2 entry."""

    return {
        "attribute_concept": concept,
        "masked_display_value": mask_display_value(concept, representative_raw_value),
        "value_hash": deterministic_value_hash(concept, profiling_key),
        "profiling_key": profiling_key,
        "global_frequency": global_frequency,
        "frequency_by_source": dict(sorted(frequency_by_source.items())),
        "source_count": len(frequency_by_source),
        "rule2_status": "worthless" if global_frequency > RULE2_THRESHOLD else "usable_by_frequency",
        "reason": (
            f"Observed on {global_frequency:,} physical records; strict Rule 2 threshold is "
            f"greater than {RULE2_THRESHOLD}."
        ),
        "profiling_transformation": transformation,
        "affected_records": global_frequency,
        "potential_pair_incidences": potential_pairs(global_frequency),
    }
