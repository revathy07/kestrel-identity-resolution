"""Pure, conservative normalization rules for derived identity fields.

These transformations make values comparable but do not decide whether records match. They
preserve email dots/plus suffixes, do not infer phone country codes, and perform no fuzzy
name or address comparison.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "normalization_rules.yaml"
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
PHONE_ALLOWED = re.compile(r"^[+\d\s().-]+$")
PHONE_FORMATTING = re.compile(r"[\s().-]+")
WHITESPACE = re.compile(r"\s+")
TRAILING_QUOTED_ANNOTATION = re.compile(r"\s+\"[^\"\r\n]*\"\s*$")
CITY_PUNCTUATION = re.compile(r"[-_.]+")
COUNTRY_TOKEN = re.compile(r"[^A-Z0-9]+")
POSTCODE_ALLOWED = re.compile(r"^[\w\s-]+$", re.UNICODE)
POSTCODE_FORMATTING = re.compile(r"[\s-]+")


class NormalizationError(RuntimeError):
    """Raised when normalization configuration is missing or internally inconsistent."""


@dataclass(frozen=True)
class NormalizationResult:
    normalized_value: str | None
    status: str
    transformation: str
    quality_flags: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


def load_normalization_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    """Load JSON-compatible YAML using only the Python standard library."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            rules = json.load(handle)
    except FileNotFoundError as exc:
        raise NormalizationError(f"Normalization rules not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NormalizationError(f"Invalid normalization rules {path}: {exc}") from exc
    required = {
        "version",
        "missing_tokens",
        "email",
        "phone",
        "date_of_birth",
        "country_aliases",
        "concept_strategies",
    }
    missing = required - set(rules) if isinstance(rules, dict) else required
    if missing:
        raise NormalizationError(f"Normalization rules missing sections: {sorted(missing)}")
    rules["_missing_tokens_casefold"] = frozenset(
        str(token).casefold() for token in rules["missing_tokens"]
    )
    return rules


def _is_missing(value: Any, rules: Mapping[str, Any]) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in rules["_missing_tokens_casefold"]


def _unicode_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def _primary_export_text(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    lines = text.splitlines()
    primary = lines[0].strip() if lines else ""
    if len(lines) > 1 and any(line.strip() for line in lines[1:]):
        flags.append("trailing_multiline_annotation_removed")
    without_annotation = TRAILING_QUOTED_ANNOTATION.sub("", primary).strip()
    if without_annotation != primary:
        flags.append("trailing_quoted_annotation_removed")
    return without_annotation, flags


def _text_result(value: Any, strategy: str) -> NormalizationResult:
    text, flags = _primary_export_text(_unicode_text(value))
    normalized = WHITESPACE.sub(" ", text).casefold()
    if strategy == "city":
        normalized = WHITESPACE.sub(" ", CITY_PUNCTUATION.sub(" ", normalized)).strip()
    if any(unicodedata.category(character).startswith("S") for character in normalized):
        flags.append("contains_symbol")
    if any(character.isdigit() for character in normalized) and strategy == "name":
        flags.append("contains_digit")
    return NormalizationResult(
        normalized or None,
        "valid" if normalized else "missing",
        (
            "NFKC + primary export text + case-fold + whitespace collapse"
            if strategy in {"name", "address"}
            else "NFKC + case-fold + safe city punctuation + whitespace collapse"
        ),
        tuple(sorted(set(flags))),
    )


def _email_result(value: Any) -> NormalizationResult:
    text = _unicode_text(value)
    matches = EMAIL_PATTERN.findall(text)
    if len(matches) != 1:
        flag = "multiple_email_candidates" if len(matches) > 1 else "invalid_email_structure"
        return NormalizationResult(None, "invalid", "single-address extraction + case-fold", (flag,))
    candidate = matches[0]
    local, domain = candidate.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return NormalizationResult(None, "invalid", "single-address extraction + case-fold", ("invalid_email_local_part",))
    flags = () if candidate == text else ("email_extracted_from_export_text",)
    return NormalizationResult(
        f"{local.casefold()}@{domain.casefold()}",
        "valid",
        "NFKC + single-address extraction + case-fold; dots/plus preserved",
        flags,
    )


def _hash_result(value: Any) -> NormalizationResult:
    text = _unicode_text(value).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        return NormalizationResult(None, "invalid", "trim + case-fold + SHA-256 shape validation", ("invalid_sha256_hash",))
    return NormalizationResult(text, "valid", "trim + case-fold + SHA-256 shape validation")


def _phone_result(value: Any, rules: Mapping[str, Any]) -> NormalizationResult:
    text = _unicode_text(value)
    if not PHONE_ALLOWED.fullmatch(text) or text.count("+") > 1 or ("+" in text and not text.startswith("+")):
        return NormalizationResult(None, "invalid", "safe punctuation removal; no country inference", ("invalid_phone_characters",))
    digits = re.sub(r"\D", "", text)
    minimum = int(rules["phone"]["minimum_digits"])
    maximum = int(rules["phone"]["maximum_digits"])
    if not minimum <= len(digits) <= maximum:
        return NormalizationResult(None, "invalid", "safe punctuation removal; no country inference", ("invalid_phone_length",))
    normalized = f"+{digits}" if text.startswith("+") else digits
    flags = () if text.startswith("+") else ("country_code_not_explicit",)
    return NormalizationResult(
        normalized,
        "valid",
        "NFKC + safe punctuation removal; country code not inferred",
        flags,
    )


def _date_result(value: Any, rules: Mapping[str, Any]) -> NormalizationResult:
    if isinstance(value, datetime):
        parsed = value.date()
        transformation = "datetime value to ISO date"
    elif isinstance(value, date):
        parsed = value
        transformation = "date value to ISO date"
    else:
        text = _unicode_text(value)
        parsed = None
        transformation = "declared date format to ISO date"
        for date_format in rules["date_of_birth"]["accepted_formats"]:
            try:
                parsed = datetime.strptime(text, date_format).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return NormalizationResult(None, "invalid", transformation, ("unrecognized_date_format",))
    reference = date.fromisoformat(rules["date_of_birth"]["reference_date"])
    age = reference.year - parsed.year - ((reference.month, reference.day) < (parsed.month, parsed.day))
    flags: list[str] = []
    if age < 0:
        flags.append("future_date_of_birth")
    elif age > int(rules["date_of_birth"]["maximum_plausible_age"]):
        flags.append("age_above_plausible_limit")
    return NormalizationResult(parsed.isoformat(), "valid", transformation, tuple(flags))


def _identifier_result(value: Any) -> NormalizationResult:
    text = _unicode_text(value)
    return NormalizationResult(text or None, "valid" if text else "missing", "NFKC + trim; case preserved")


def _postcode_result(value: Any) -> NormalizationResult:
    text = _unicode_text(value)
    if not POSTCODE_ALLOWED.fullmatch(text):
        return NormalizationResult(None, "invalid", "NFKC + uppercase + safe space/hyphen removal", ("invalid_postcode_characters",))
    normalized = POSTCODE_FORMATTING.sub("", text).upper()
    return NormalizationResult(normalized or None, "valid" if normalized else "missing", "NFKC + uppercase + safe space/hyphen removal")


def _country_result(value: Any, rules: Mapping[str, Any]) -> NormalizationResult:
    text = _unicode_text(value)
    token = COUNTRY_TOKEN.sub("", text.upper())
    aliases = rules["country_aliases"]
    if token not in aliases:
        return NormalizationResult(None, "invalid", "NFKC + ISO country alias mapping", ("unknown_country_alias",))
    return NormalizationResult(str(aliases[token]), "valid", "NFKC + ISO country alias mapping")


def normalize_value(concept: str, value: Any, rules: Mapping[str, Any]) -> NormalizationResult:
    """Normalize one value according to its canonical concept."""

    if _is_missing(value, rules):
        return NormalizationResult(None, "missing", "documented missing-token recognition")
    strategy = rules["concept_strategies"].get(concept)
    if strategy is None:
        raise NormalizationError(f"No normalization strategy configured for concept {concept!r}")
    if strategy == "email":
        return _email_result(value)
    if strategy == "sha256_hash":
        return _hash_result(value)
    if strategy == "phone":
        return _phone_result(value, rules)
    if strategy == "date_of_birth":
        return _date_result(value, rules)
    if strategy in {"name", "address", "city"}:
        return _text_result(value, strategy)
    if strategy == "postcode":
        return _postcode_result(value)
    if strategy == "country":
        return _country_result(value, rules)
    if strategy == "identifier":
        return _identifier_result(value)
    raise NormalizationError(f"Unsupported normalization strategy {strategy!r} for {concept!r}")
