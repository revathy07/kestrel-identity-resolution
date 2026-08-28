#!/usr/bin/env python3
"""Generate the deliberately messy Assessment No. 6 identity-resolution dataset.

The default output contains about 300,000 invented people and 420,000 source rows.
Use ``--scale 0.01`` for a fast, proportionally equivalent development dataset.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

try:
    from openpyxl import Workbook
except ImportError as exc:  # pragma: no cover - environment error
    raise SystemExit("Missing dependency: pip install openpyxl") from exc


FULL_PEOPLE = 300_000
FULL_ROWS = 420_000
FINAL_ROW_WEIGHTS = {
    "app_users": 120_000,
    "store_customers": 80_000,
    "ticketing": 80_000,
    "subscriptions": 50_000,
    "social_logins": 90_000,
}
EXACT_RATE = 0.02
NEAR_RATE = 0.01
BOT_RATE = 0.05
INTERNAL_TEST_RATE = 0.005
IMPOSSIBLE_RATE = 0.003
LATE_RATE = 0.032
ZERO_EVIDENCE_RATE = 0.08
ANCHOR = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
MISSING_SENTINELS = {"", "null", "none"}

SYLLABLES = (
    "zex", "mab", "kor", "rai", "vex", "lon", "bir", "sul", "te", "ri",
    "nan", "pha", "gui", "xon", "pre", "sha", "dri", "cam", "jor", "lek",
    "wul", "pav", "tur", "sek", "biv", "nox", "cra", "fiz", "yev", "qur",
)
CITY_VARIANTS = {
    "Metrocity": ("Metrocity", "metrocity", "METROCITY", "Metro City", "metro-city"),
    "Newtown": ("Newtown", "New Town", "new town", "NEWTOWN", "NewTown"),
    "Laketown": ("Laketown", "Lake Town", "lake town", "LAKETOWN", "LakeTown"),
    "Hillview": ("Hillview", "Hill View", "HILLVIEW", "hill view", "Hill-View"),
    "Greenfield": ("Greenfield", "Green Field", "GREENFIELD", "greenfield", "Green-Field"),
}
COUNTRY_VARIANTS = {
    "IN": ("IN", "India", "INDIA", "india", "IND"),
    "US": ("US", "USA", "United States", "united states", "U.S."),
    "GB": ("GB", "UK", "United Kingdom", "united kingdom", "GBR"),
    "AU": ("AU", "AUS", "Australia", "australia", "AUSTRALIA"),
}
DEVICE_VARIANTS = {
    "mobile": ("mobile", "Mobile", "MOBILE", "mob", "smartphone"),
    "desktop": ("desktop", "Desktop", "DESKTOP", "desk", "pc"),
    "tablet": ("tablet", "Tablet", "TABLET", "tab", "ipad"),
    "kiosk": ("kiosk", "Kiosk", "KIOSK", "check-in kiosk", "event kiosk"),
}
CHANNEL_VARIANTS = {
    "app": ("app", "App", "APP", "mobile app"),
    "web": ("web", "Web", "WEB", "website"),
    "event": ("event", "Event", "EVENT", "live-event"),
    "social": ("social", "Social", "SOCIAL", "social login"),
}
TIMESTAMP_FIELDS = {
    "app_users": "signup_ts",
    "store_customers": "updated_ts",
    "ticketing": "created_ts",
    "subscriptions": "start_date",
    "social_logins": "login_ts",
}


@dataclass
class Person:
    person_id: str
    first: str
    last: str
    email: str
    phone: str
    dob: str
    line1: str
    line2: str
    city_key: str
    postcode: str
    country_key: str
    device_id: str
    device_key: str


@dataclass
class Row:
    data: dict[str, Any]
    entity_id: str
    entity_type: str = "human"


def allocate(total: int, weights: dict[str, int]) -> dict[str, int]:
    weight_total = sum(weights.values())
    raw = {key: total * value / weight_total for key, value in weights.items()}
    result = {key: math.floor(value) for key, value in raw.items()}
    remainder = total - sum(result.values())
    order = sorted(weights, key=lambda item: raw[item] - result[item], reverse=True)
    for key in order[:remainder]:
        result[key] += 1
    return result


def scaled(full_value: int, scale: float) -> int:
    return max(1, round(full_value * scale))


def synth_name(rng: random.Random) -> tuple[str, str]:
    return (
        rng.choice(SYLLABLES).capitalize() + rng.choice(SYLLABLES),
        rng.choice(SYLLABLES).capitalize() + rng.choice(SYLLABLES),
    )


def synth_email(person_id: str, first: str, last: str, domain: str = "brand-example.test") -> str:
    return f"{first.lower()}.{last.lower()}.{person_id.lower()}@{domain}"


def synth_phone(index: int) -> str:
    """Use unassigned country code +999 so no value can reach a real subscriber."""
    return f"+999{index % 1_000_000_000:09d}"


def token(prefix: str, value: str, length: int = 12) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}{digest}"


def messy_text(value: str, rng: random.Random) -> str:
    if rng.random() < 0.025:
        value += ' "quoted, comma"'
    if rng.random() < 0.018:
        value += "\n multiline note"
    if rng.random() < 0.010:
        value += " 😊"
    if rng.random() < 0.014:
        value += " hello नमस्ते यार"
    return value


def mixed_timestamp(moment: datetime, rng: random.Random, style: int | None = None) -> str:
    style = rng.randrange(6) if style is None else style
    utc = moment.astimezone(timezone.utc)
    if style == 0:
        return utc.strftime("%d-%m-%Y %H:%M:%S")
    if style == 1:
        return utc.strftime("%Y/%m/%d %H:%M:%S")
    if style == 2:
        return utc.strftime("%m-%d-%y %H:%M")
    if style == 3:
        return utc.isoformat()
    if style == 4:
        return str(int(utc.timestamp() * 1000))
    # Genuine local clock value with its +05:30 offset deliberately omitted.
    return (utc + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")


def shift_timestamp(value: str, seconds: int) -> str:
    parsers = (
        (r"^\d{2}-\d{2}-\d{4} ", "%d-%m-%Y %H:%M:%S"),
        (r"^\d{4}/", "%Y/%m/%d %H:%M:%S"),
        (r"^\d{2}-\d{2}-\d{2} ", "%m-%d-%y %H:%M"),
        (r"^\d{4}-\d{2}-\d{2} ", "%Y-%m-%d %H:%M:%S"),
    )
    if re.fullmatch(r"\d{13}", value):
        return str(int(value) + seconds * 1000)
    if "T" in value:
        return (datetime.fromisoformat(value) + timedelta(seconds=seconds)).isoformat()
    for pattern, fmt in parsers:
        if re.match(pattern, value):
            effective_seconds = max(60, seconds) if fmt == "%m-%d-%y %H:%M" else seconds
            return (datetime.strptime(value, fmt) + timedelta(seconds=effective_seconds)).strftime(fmt)
    raise ValueError(f"unknown timestamp format: {value}")


def render_city(person: Person, rng: random.Random) -> str:
    return rng.choice(CITY_VARIANTS[person.city_key])


def render_country(person: Person, rng: random.Random) -> str:
    return rng.choice(COUNTRY_VARIANTS[person.country_key])


def render_device(person: Person, rng: random.Random) -> str:
    return rng.choice(DEVICE_VARIANTS[person.device_key])


def conditional_missing(base: float, person: Person, rng: random.Random) -> bool:
    rate = base + (0.025 if person.country_key == "IN" else 0) + (0.020 if person.device_key == "kiosk" else 0)
    return rng.random() < rate


def is_missing_identifier(value: Any) -> bool:
    """Return True for null, blank, quoted-empty, or null-like identifier values."""
    if value is None:
        return True
    text = str(value).strip()
    while len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text.casefold() in MISSING_SENTINELS


def clean_email_value(value: Any) -> str:
    """Parse the generator's escaped free-text artifacts before email normalization."""
    if is_missing_identifier(value):
        return ""
    text = str(value).splitlines()[0].split(' "quoted')[0].strip()
    return "" if is_missing_identifier(text) else text


def normalize_email(value: str) -> str:
    value = clean_email_value(value).lower()
    if not value:
        return ""
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    if domain == "brand-example.test":
        local = local.split("+", 1)[0].replace(".", "")
    return f"{local}@{domain}"


def identity_view(data: dict[str, Any]) -> dict[str, Any]:
    """Return identity attributes, flattening a nested social provider payload."""
    payload = data.get("identity_payload")
    if isinstance(payload, dict):
        return {**data, **payload}
    return data


def source_record_id(system: str, data: dict[str, Any]) -> str:
    fields = {
        "app_users": "account_id", "store_customers": "customer_id",
        "ticketing": "booking_id", "subscriptions": "subscription_id",
        "social_logins": "provider_id",
    }
    return str(identity_view(data).get(fields[system], ""))


def email_variant(value: str, index: int) -> str:
    local, domain = value.split("@", 1)
    if index % 3 == 0:
        return value.upper()
    if index % 3 == 1:
        return f"{local.replace('.', '')}@{domain}"
    return f"{local}+ticket{index}@{domain}"


def phone_variant(value: str, index: int) -> str:
    digits = re.sub(r"\D", "", value)
    if index % 3 == 0:
        return digits[3:]
    if index % 3 == 1:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return "0" + digits[3:]


def build_people(count: int, rng: random.Random) -> list[Person]:
    people: list[Person] = []
    for index in range(count):
        first, last = synth_name(rng)
        person_id = f"P{index + 1:06d}"
        people.append(Person(
            person_id=person_id,
            first=first,
            last=last,
            email=synth_email(person_id, first, last),
            phone=synth_phone(index + 1),
            dob=date(rng.randint(1938, 2005), rng.randint(1, 12), rng.randint(1, 28)).isoformat(),
            line1=f"{rng.randint(1, 999)} {rng.choice(('Ridge', 'Vale', 'Park', 'Lake', 'Garden', 'Market'))} {rng.choice(('St', 'Ave', 'Road'))}",
            line2=rng.choice(("", "", "", f"Suite {rng.randint(1, 200)}", f"Floor {rng.randint(1, 12)}")),
            city_key=rng.choice(tuple(CITY_VARIANTS)),
            postcode=f"{rng.randint(10000, 99999)}",
            country_key=rng.choice(tuple(COUNTRY_VARIANTS)),
            device_id=f"DEV-{token('', person_id, 12)}",
            device_key=rng.choice(tuple(DEVICE_VARIANTS)),
        ))
    return people


def pair_people(pool: list[Person], pair_count: int, rng: random.Random) -> list[tuple[Person, Person]]:
    pair_count = min(pair_count, len(pool) // 2)
    selected = rng.sample(pool, pair_count * 2)
    return list(zip(selected[::2], selected[1::2]))


def apply_hard_negative_profiles(
    store_people: list[Person],
    subscription_people: list[Person],
    app_people: list[Person],
    scale: float,
    rng: random.Random,
) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    shared_tokens: dict[str, str] = {}
    used_store: set[str] = set()
    for father, son in pair_people(store_people, scaled(4_000, scale), rng):
        son.first, son.last = father.first, father.last
        son.line1, son.line2, son.city_key, son.postcode = father.line1, father.line2, father.city_key, father.postcode
        son.dob = date(2002, (len(pairs["father_son"]) % 12) + 1, 15).isoformat()
        used_store.update((father.person_id, son.person_id))
        pairs["father_son"].append((father.person_id, son.person_id))
    remaining_store = [person for person in store_people if person.person_id not in used_store]
    for left, right in pair_people(remaining_store, scaled(4_000, scale), rng):
        right.first, right.last, right.city_key = left.first, left.last, left.city_key
        pairs["common_name_city"].append((left.person_id, right.person_id))
    for index, (left, right) in enumerate(pair_people(app_people, scaled(8_000, scale), rng), 1):
        device = f"UNIVERSITY-LAB-{index:04d}"
        left.device_id = right.device_id = device
        pairs["university_computer_lab"].append((left.person_id, right.person_id))
    for index, (left, right) in enumerate(pair_people(subscription_people, scaled(4_000, scale), rng), 1):
        email = f"couple{index:05d}@household.example.test"
        payment = f"tok_COUPLE_{index:05d}"
        left.email = right.email = email
        shared_tokens[left.person_id] = shared_tokens[right.person_id] = payment
        pairs["couple_shared_email_payment_token"].append((left.person_id, right.person_id))
    return pairs, shared_tokens


def make_app_row(person: Person, record_id: str, mode: str, rng: random.Random) -> Row:
    email, phone, first, last = person.email, person.phone, person.first, person.last
    preserve = {
        "exact_email": {"email"}, "email_variant": {"email"}, "phone_variant": {"phone"},
        "name_city": {"first", "last"}, "device_only": {"device"}, "zero": set(),
    }.get(mode, set())
    if "email" not in preserve and conditional_missing(0.050, person, rng):
        email = ""
    if "phone" not in preserve and conditional_missing(0.050, person, rng):
        phone = ""
    if "first" not in preserve and conditional_missing(0.045, person, rng):
        first = ""
    if "last" not in preserve and conditional_missing(0.045, person, rng):
        last = ""
    return Row({
        "account_id": record_id, "email": email, "phone": phone,
        "first_name": messy_text(first, rng), "last_name": messy_text(last, rng), "dob": person.dob,
        "device_id": person.device_id, "device_type": render_device(person, rng),
        "signup_ts": mixed_timestamp(ANCHOR - timedelta(days=rng.randint(1, 700)), rng),
        "country": render_country(person, rng), "city": render_city(person, rng),
        "channel": rng.choice(CHANNEL_VARIANTS["app"]), "engagement_count": rng.randint(1, 120),
    }, person.person_id)


def make_store_row(person: Person, record_id: str, app_ref: str, rng: random.Random) -> Row:
    email = "" if conditional_missing(0.035, person, rng) else person.email
    phone = "" if conditional_missing(0.035, person, rng) else person.phone
    return Row({
        "customer_id": record_id, "app_account_ref": f"{int(app_ref):09d}" if app_ref else "",
        "customer_email_address": messy_text(email, rng), "contact_no": phone,
        "first": messy_text(person.first, rng), "last": messy_text(person.last, rng), "dob": person.dob,
        "device": person.device_id, "device_type": render_device(person, rng),
        "line1": messy_text(person.line1, rng), "line2": messy_text(person.line2, rng),
        "city": render_city(person, rng), "postcode": person.postcode, "country": render_country(person, rng),
        "updated_ts": mixed_timestamp(ANCHOR - timedelta(days=rng.randint(1, 500)), rng),
        "channel": rng.choice(CHANNEL_VARIANTS["web"]),
    }, person.person_id)


def make_ticket_row(
    person: Person, record_id: str, app_id: str, mode: str,
    late: bool, orphan: bool, rng: random.Random,
) -> Row:
    event = ANCHOR - timedelta(days=rng.randint(1, 120), seconds=rng.randint(0, 86_399))
    created = event + (timedelta(days=rng.randint(10, 30)) if late else timedelta(seconds=rng.randint(10, 3_600)))
    style = rng.randrange(6)
    guest = rng.random() < 0.12
    unrelated = token("anon", record_id, 10)
    full_name = f"{person.first} {person.last}"
    email, phone, device, city = person.email, person.phone, person.device_id, render_city(person, rng)
    account_id = "" if guest else app_id
    if orphan and not guest:
        account_id = str(8_000_000_000 + int(re.sub(r"\D", "", record_id)))
    if mode == "zero":
        full_name, email, phone = f"Guest {unrelated}", f"{unrelated}@unlinked.example.test", ""
        device, city, account_id, guest = f"DEV-UNLINKED-{unrelated}", "Remote", "", True
    elif mode == "email_variant":
        email = email_variant(email, int(re.sub(r"\D", "", record_id)))
    elif mode == "phone_variant":
        email, phone = f"{unrelated}@ticket.example.test", phone_variant(phone, int(re.sub(r"\D", "", record_id)))
        full_name, device, account_id = f"Guest {unrelated}", f"DEV-{unrelated}", ""
    elif mode == "name_city":
        email, phone, device, account_id = f"{unrelated}@ticket.example.test", "", f"DEV-{unrelated}", ""
    elif mode == "device_only":
        email, phone, full_name, city, account_id = f"{unrelated}@ticket.example.test", "", f"Guest {unrelated}", "Remote", ""
    else:
        if conditional_missing(0.055, person, rng):
            email = ""
        if conditional_missing(0.040, person, rng):
            phone = ""
    return Row({
        "booking_id": record_id, "account_id": account_id, "full_name": messy_text(full_name, rng),
        "email": email, "phone": phone, "guest": guest, "device_id": device, "city": city,
        "event_ts": mixed_timestamp(event, rng, style), "created_ts": mixed_timestamp(created, rng, style),
        "channel": rng.choice(CHANNEL_VARIANTS["event"]),
    }, person.person_id)


def make_subscription_row(person: Person, record_id: str, shared_token: str | None, rng: random.Random) -> Row:
    roll = rng.random()
    billing = f"Parent {person.last}" if roll < 0.30 else f"Partner {person.last}" if roll < 0.55 else f"{person.first} {person.last}"
    return Row({
        "subscription_id": record_id, "email": messy_text(person.email, rng),
        "subscriber_name": messy_text(f"{person.first} {person.last}", rng),
        "billing_name": messy_text(billing, rng), "payment_token": shared_token or token("tok_", person.person_id),
        "start_date": mixed_timestamp(ANCHOR - timedelta(days=rng.randint(1, 1_000)), rng),
        "country": render_country(person, rng), "channel": rng.choice(CHANNEL_VARIANTS["web"]),
    }, person.person_id)


def make_social_row(person: Person, record_id: str, linked: bool, rng: random.Random) -> Row:
    provider = "google" if linked else rng.choice(("google", "facebook", "twitter", "apple"))
    row: dict[str, Any] = {
        "provider": provider,
        "login_ts": mixed_timestamp(ANCHOR - timedelta(days=rng.randint(1, 500)), rng),
        "channel": rng.choice(CHANNEL_VARIANTS["social"]), "engagement_count": rng.randint(1, 150),
    }
    identity: dict[str, Any] = {"provider_id": record_id}
    if provider == "google":
        identity["verified_email"] = person.email if linked or rng.random() < 0.72 else ""
        if rng.random() < 0.10 and identity["verified_email"]:
            identity["verified_email"] = email_variant(person.email, int(re.sub(r"\D", "", record_id) or 0))
        if linked:
            identity["phone"] = person.phone
            identity["device_id"] = person.device_id
            identity["display_name"] = f"{person.first} {person.last}"
            identity["city"] = render_city(person, rng)
    elif provider == "facebook":
        identity["display_name"] = f"{person.first[:3]}_{rng.randint(10, 999)}"
        if rng.random() < 0.35:
            identity["phone"] = person.phone
    elif provider == "twitter":
        # Deliberately minimal provider-returned identity: no email, phone,
        # hash, or real-name field. Operational metadata remains outside it.
        identity["display_name"] = f"{person.first[:3]}ie{rng.randint(1, 99)}"
    else:
        identity["hashed_email"] = hashlib.sha256(normalize_email(person.email).encode("utf-8")).hexdigest()
    row["identity_payload"] = identity
    return Row(row, person.person_id)


def make_bot_row(system: str, index: int, rng: random.Random) -> Row:
    entity = f"BOT{system[:2].upper()}{index:07d}"
    stamp = mixed_timestamp(ANCHOR - timedelta(seconds=index % 300), rng)
    first, last = synth_name(rng)
    public_key = 7_000_000 + index
    email = f"{first.lower()}.{last.lower()}.u{public_key}@brand-example.test"
    device = f"DEV-{token('', f'visitor-{public_key}', 12)}"
    device_type = rng.choice(tuple(value for variants in DEVICE_VARIANTS.values() for value in variants))
    city = rng.choice(tuple(value for variants in CITY_VARIANTS.values() for value in variants))
    country = rng.choice(tuple(value for variants in COUNTRY_VARIANTS.values() for value in variants))
    if system == "app_users":
        data = {"account_id": str(public_key), "email": email, "phone": "", "first_name": first, "last_name": last, "dob": "", "device_id": device, "device_type": device_type, "signup_ts": stamp, "country": country, "city": city, "channel": rng.choice(CHANNEL_VARIANTS["app"]), "engagement_count": index % 7}
    elif system == "store_customers":
        data = {"customer_id": f"SC{public_key:09d}", "app_account_ref": "", "customer_email_address": email, "contact_no": "", "first": first, "last": last, "dob": "", "device": device, "device_type": device_type, "line1": f"{100 + index % 800} Ridge Road", "line2": "", "city": city, "postcode": f"{10000 + index % 89999:05d}", "country": country, "updated_ts": stamp, "channel": rng.choice(CHANNEL_VARIANTS["web"])}
    elif system == "ticketing":
        data = {"booking_id": f"B{public_key}", "account_id": "", "full_name": f"{first} {last}", "email": email, "phone": "", "guest": False, "device_id": device, "city": city, "event_ts": stamp, "created_ts": stamp, "channel": rng.choice(CHANNEL_VARIANTS["event"])}
    elif system == "subscriptions":
        data = {"subscription_id": f"S{public_key}", "email": email, "subscriber_name": f"{first} {last}", "billing_name": f"{first} {last}", "payment_token": token("tok_", entity), "start_date": stamp, "country": country, "channel": rng.choice(CHANNEL_VARIANTS["web"])}
    else:
        data = {"provider": "google", "identity_payload": {"provider_id": f"google_{public_key:09d}", "verified_email": email, "display_name": f"{first} {last}"}, "login_ts": stamp, "channel": rng.choice(CHANNEL_VARIANTS["social"]), "engagement_count": index % 5}
    return Row(data, entity, "bot")


def add_artifacts(system: str, rows: list[Row], exact_count: int, near_count: int, rng: random.Random) -> None:
    bots = [row for row in rows if row.entity_type == "bot"]
    if not bots:
        raise ValueError(f"no bot rows available for {system} duplicate artifacts")
    for index in range(exact_count):
        rows.append(copy.deepcopy(bots[index % len(bots)]))
    field = TIMESTAMP_FIELDS[system]
    for index in range(near_count):
        duplicate = copy.deepcopy(bots[index % len(bots)])
        duplicate.data[field] = shift_timestamp(str(duplicate.data[field]), rng.randint(2, 8))
        rows.append(duplicate)


def apply_poison(
    rows_by_system: dict[str, list[Row]], systems: tuple[str, ...], target: int,
    multi_ids: set[str], field_by_system: dict[str, str], value: str,
    rng: random.Random, predicate: Any | None = None,
) -> None:
    candidates = [
        row for system in systems for row in rows_by_system[system]
        if row.entity_type == "human" and row.entity_id not in multi_ids
        and field_by_system[system] in row.data and (predicate is None or predicate(system, row))
    ]
    if len(candidates) < target:
        candidates.extend(
            row for system in systems for row in rows_by_system[system]
            if row.entity_type == "human" and field_by_system[system] in row.data and row not in candidates
        )
    for row in rng.sample(candidates, min(target, len(candidates))):
        for system in systems:
            field = field_by_system.get(system)
            if field in row.data:
                row.data[field] = value
                break


def apply_impossible_values(rows_by_system: dict[str, list[Row]], target: int, rng: random.Random) -> None:
    allocations = allocate(target, {"young_age": 1, "old_age": 1, "negative_duration": 1, "future_date": 1, "engagement": 1})
    app_store = [row for system in ("app_users", "store_customers") for row in rows_by_system[system] if row.entity_type == "human"]
    used: set[int] = set()
    for kind, dob in (("young_age", "2024-01-01"), ("old_age", "1900-06-15")):
        available = [row for row in app_store if id(row) not in used]
        for row in rng.sample(available, min(allocations[kind], len(available))):
            row.data["dob"] = dob
            used.add(id(row))
    ticket_rows = [row for row in rows_by_system["ticketing"] if row.entity_type == "human"]
    for row in rng.sample(ticket_rows, min(allocations["negative_duration"], len(ticket_rows))):
        style = rng.randrange(6)
        event = ANCHOR - timedelta(days=30)
        row.data["event_ts"] = mixed_timestamp(event, rng, style)
        row.data["created_ts"] = mixed_timestamp(event - timedelta(days=2), rng, style)
    sub_rows = [row for row in rows_by_system["subscriptions"] if row.entity_type == "human"]
    for row in rng.sample(sub_rows, min(allocations["future_date"], len(sub_rows))):
        row.data["start_date"] = mixed_timestamp(datetime(2035, 1, 1, tzinfo=timezone.utc), rng)
    engagement_rows = [row for system in ("app_users", "social_logins") for row in rows_by_system[system] if row.entity_type == "human"]
    for row in rng.sample(engagement_rows, min(allocations["engagement"], len(engagement_rows))):
        row.data["engagement_count"] = 100_000


def record_id(system: str, index: int) -> str:
    if system == "app_users":
        return str(1_000_000 + index)
    if system == "store_customers":
        return f"SC{200_000 + index:09d}"
    if system == "ticketing":
        return f"B{300_000 + index}"
    if system == "subscriptions":
        return f"S{400_000 + index}"
    provider = ("google", "facebook", "twitter", "apple")[index % 4]
    return f"{provider}_{500_000 + index:09d}"


def identity_tokens(row: Row) -> set[str]:
    data = identity_view(row.data)
    result: set[str] = set()
    for key in ("email", "customer_email_address", "verified_email"):
        normalized = normalize_email(data.get(key, ""))
        if normalized and normalized not in {"bookings@events.example", "qa+001@staff.test"}:
            result.add("email:" + normalized)
    if data.get("hashed_email"):
        result.add("hash:" + str(data["hashed_email"]))
    for key in ("phone", "contact_no"):
        if data.get(key):
            digits = re.sub(r"\D", "", str(data[key]))
            if digits and digits not in {"0000000000", "9999999999"}:
                result.add("phone:" + digits.removeprefix("999").lstrip("0"))
    for key in ("device_id", "device"):
        if data.get(key) and data[key] != "KIOSK-DEVICE-1":
            result.add("device:" + str(data[key]))
    if data.get("account_id"):
        result.add("account:" + str(int(str(data["account_id"]))))
    if data.get("app_account_ref"):
        result.add("account:" + str(int(str(data["app_account_ref"]))))
    if data.get("payment_token"):
        result.add("payment:" + str(data["payment_token"]))
    city = data.get("city")
    if city:
        if data.get("first_name") or data.get("last_name"):
            name = f"{data.get('first_name', '')} {data.get('last_name', '')}"
        elif data.get("first") or data.get("last"):
            name = f"{data.get('first', '')} {data.get('last', '')}"
        else:
            name = str(data.get("full_name") or data.get("display_name") or "")
        first_line = name.splitlines()
        name = (first_line[0] if first_line else "").split(' "quoted')[0].split(" hello ")[0].replace("😊", "")
        clean_name = re.sub(r"[^a-z]", "", name.lower())
        clean_city = re.sub(r"[^a-z]", "", str(city).lower())
        if clean_name and clean_city:
            result.add(f"name_city:{clean_name}:{clean_city}")
    return result


def naive_identity_tokens(row: Row) -> set[str]:
    """Evidence a deliberately naive matcher would use, including poison values."""
    result = identity_tokens(row)
    data = identity_view(row.data)
    for key in ("email", "customer_email_address", "verified_email"):
        normalized = normalize_email(data.get(key, ""))
        if normalized in {"bookings@events.example", "qa+001@staff.test"}:
            result.add("email:" + normalized)
    for key in ("phone", "contact_no"):
        value = str(data.get(key, ""))
        digits = re.sub(r"\D", "", value)
        if digits in {"0000000000", "9999999999"}:
            result.add("phone:" + digits)
    for key in ("device_id", "device"):
        if data.get(key) == "KIOSK-DEVICE-1":
            result.add("device:KIOSK-DEVICE-1")
    if data.get("dob") in {"1900-01-01", "1970-01-01", "01-01-1900", "01-01-1970"}:
        result.add("dob:" + str(data["dob"]))
    return result


def is_poison_token(value: str) -> bool:
    return value in {
        "phone:0000000000", "phone:9999999999", "dob:1900-01-01",
        "dob:1970-01-01", "dob:01-01-1900", "dob:01-01-1970",
        "email:bookings@events.example", "email:qa+001@staff.test",
        "device:KIOSK-DEVICE-1",
    }


def row_has_poison(row: Row) -> bool:
    values = list(identity_view(row.data).values())
    return (
        "0000000000" in values
        or "9999999999" in values
        or "1900-01-01" in values
        or "1970-01-01" in values
        or "01-01-1900" in values
        or "01-01-1970" in values
        or "bookings@events.example" in values
        or "KIOSK-DEVICE-1" in values
        or any(isinstance(value, str) and value.lower().endswith("@staff.test") for value in values)
    )


def naive_poisoned_cluster_metrics(rows_by_system: dict[str, list[Row]]) -> tuple[int, int, list[str]]:
    """Return record size, distinct truth entities and causes for the largest poisoned component."""
    rows = [row for system_rows in rows_by_system.values() for row in system_rows]
    parent = list(range(len(rows)))
    size = [1] * len(rows)
    owner: dict[str, int] = {}
    poisoned: list[int] = []

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        if size[left_root] < size[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        size[left_root] += size[right_root]

    for index, row in enumerate(rows):
        if row_has_poison(row):
            poisoned.append(index)
        for evidence in naive_identity_tokens(row):
            previous = owner.setdefault(evidence, index)
            if previous != index:
                union(index, previous)
    roots = {find(index) for index in poisoned}
    if not roots:
        return 0, 0, []
    largest_root = max(roots, key=lambda root: size[root])
    distinct_entities = len({row.entity_id for index, row in enumerate(rows) if find(index) == largest_root})
    causes = sorted(evidence for evidence, index in owner.items() if is_poison_token(evidence) and find(index) == largest_root)
    return size[largest_root], distinct_entities, causes


def largest_naive_poisoned_cluster(rows_by_system: dict[str, list[Row]]) -> int:
    return naive_poisoned_cluster_metrics(rows_by_system)[0]


def measured_zero_evidence(rows_by_system: dict[str, list[Row]]) -> tuple[int, int, float, dict[str, int]]:
    by_person: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    frequencies: Counter[str] = Counter()
    for system, rows in rows_by_system.items():
        for row in rows:
            frequencies.update(identity_tokens(row))
            if row.entity_type == "human":
                by_person[row.entity_id].append((system, identity_tokens(row)))
    zero = total = 0
    zero_by_source_pair: Counter[str] = Counter()
    for records in by_person.values():
        token_sets = [tokens for _system, tokens in records]
        for left, right in combinations(token_sets, 2):
            total += 1
            if not {value for value in left.intersection(right) if frequencies[value] <= 40}:
                zero += 1
        for (left_system, left), (right_system, right) in combinations(records, 2):
            if not {value for value in left.intersection(right) if frequencies[value] <= 40}:
                zero_by_source_pair["+".join(sorted((left_system, right_system)))] += 1
    return zero, total, zero / total if total else 0.0, dict(zero_by_source_pair)


def candidate_hard_negative_rate(rows_by_system: dict[str, list[Row]]) -> tuple[int, int, float]:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for rows in rows_by_system.values():
        for row in rows:
            for evidence in naive_identity_tokens(row):
                buckets[evidence][row.entity_id] += 1
    candidates = hard_negatives = 0
    for entity_counts in buckets.values():
        size = sum(entity_counts.values())
        if size < 2:
            continue
        pairs = math.comb(size, 2)
        candidates += pairs
        hard_negatives += pairs - sum(math.comb(count, 2) for count in entity_counts.values() if count > 1)
    return hard_negatives, candidates, hard_negatives / candidates if candidates else 0.0


def source_refs(rows_by_system: dict[str, list[Row]]) -> tuple[dict[str, list[dict[str, str]]], dict[tuple[str, str], Row]]:
    refs: dict[str, list[dict[str, str]]] = defaultdict(list)
    records: dict[tuple[str, str], Row] = {}
    for system, rows in rows_by_system.items():
        for row in rows:
            rid = source_record_id(system, row.data)
            key = (system, rid)
            records.setdefault(key, row)
            if row.entity_type == "human" and not any(item["system"] == system and item["record_id"] == rid for item in refs[row.entity_id]):
                refs[row.entity_id].append({"system": system, "record_id": rid})
    return refs, records


def raw_email_values(row: Row) -> list[tuple[str, str]]:
    data = identity_view(row.data)
    return [(key, clean_email_value(data.get(key))) for key in ("email", "customer_email_address", "verified_email") if clean_email_value(data.get(key))]


def observed_evidence_modes(left: Row, right: Row, usable: set[str]) -> list[str]:
    modes: set[str] = set()
    for left_key, left_raw in raw_email_values(left):
        for right_key, right_raw in raw_email_values(right):
            if not left_raw or not right_raw or normalize_email(left_raw) != normalize_email(right_raw):
                continue
            left_local, right_local = left_raw.split("@", 1)[0], right_raw.split("@", 1)[0]
            if left_raw == right_raw and "verified_email" in {left_key, right_key}:
                modes.add("exact_verified_email")
            elif left_raw == right_raw:
                modes.add("exact_email")
            if left_raw != right_raw and left_raw.casefold() == right_raw.casefold():
                modes.add("email_case_variation")
            if left_raw.casefold() != right_raw.casefold() and left_local.split("+", 1)[0].replace(".", "").casefold() == right_local.split("+", 1)[0].replace(".", "").casefold() and ("." in left_local) != ("." in right_local):
                modes.add("email_dotted_local_part")
            if ("+" in left_local) != ("+" in right_local):
                modes.add("email_plus_suffix")
    left_data, right_data = identity_view(left.data), identity_view(right.data)
    left_phone = next((str(left_data[key]) for key in ("phone", "contact_no") if left_data.get(key)), "")
    right_phone = next((str(right_data[key]) for key in ("phone", "contact_no") if right_data.get(key)), "")
    if left_phone and right_phone:
        left_digits, right_digits = re.sub(r"\D", "", left_phone), re.sub(r"\D", "", right_phone)
        normalized_left = left_digits.removeprefix("999").lstrip("0")
        normalized_right = right_digits.removeprefix("999").lstrip("0")
        if normalized_left and normalized_left == normalized_right and left_phone != right_phone:
            if left_digits.startswith("999") != right_digits.startswith("999"): modes.add("phone_country_code")
            if " " in left_phone or " " in right_phone: modes.add("phone_spaced")
            if left_phone.startswith("0") or right_phone.startswith("0"): modes.add("phone_leading_zero")
    if usable and all(value.startswith("name_city:") for value in usable): modes.add("name_city_only")
    if usable and all(value.startswith("device:") for value in usable): modes.add("device_only")
    if not usable: modes.add("no_usable_evidence")
    if usable and not modes:
        modes.add("multiple_or_other_evidence")
    return sorted(modes)


def build_hidden_metadata(
    rows_by_system: dict[str, list[Row]],
    hard_negative_pairs: dict[str, list[tuple[str, str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs, records = source_refs(rows_by_system)
    frequencies: Counter[str] = Counter()
    for rows in rows_by_system.values():
        for row in rows:
            frequencies.update(identity_tokens(row))
    canonical: list[dict[str, Any]] = []
    for person_id, person_refs in refs.items():
        if len(person_refs) < 2:
            continue
        anchor = person_refs[0]
        left = records[(anchor["system"], anchor["record_id"])]
        truth_key = hashlib.sha256(f"canonical:{person_id}".encode("utf-8")).hexdigest()
        for other in person_refs[1:]:
            right = records[(other["system"], other["record_id"])]
            usable = {value for value in identity_tokens(left) & identity_tokens(right) if frequencies[value] <= 40}
            modes = observed_evidence_modes(left, right, usable)
            canonical.append({
                "source_system_a": anchor["system"], "source_record_id_a": anchor["record_id"],
                "source_system_b": other["system"], "source_record_id_b": other["record_id"],
                "truth_key": truth_key, "evidence_mode": modes[0], "evidence_modes": modes,
                "intended_recoverability": bool(usable), "scenario_type": "canonical_duplicate_link",
            })
    hard_manifest: list[dict[str, Any]] = []
    for kind, pairs in hard_negative_pairs.items():
        for left, right in pairs:
            hard_manifest.append({"type": kind, "person_ids": [left, right], "source_records": [refs[left][0], refs[right][0]], "must_not_merge": True})
    return canonical, hard_manifest


def _pair_code(left: int, right: int) -> int:
    if left > right:
        left, right = right, left
    return (left << 20) | right


def _high_frequency_edge_union(groups: list[set[int]]) -> int:
    total = 0
    for mask in range(1, 1 << len(groups)):
        selected = [groups[index] for index in range(len(groups)) if mask & (1 << index)]
        common = set.intersection(*selected)
        pairs = math.comb(len(common), 2) if len(common) > 1 else 0
        total += pairs if len(selected) % 2 else -pairs
    return total


def candidate_pair_metrics(
    rows_by_system: dict[str, list[Row]], hard_manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    """Measure incidences and exact unique record-key pairs without materializing poison cliques."""
    record_tokens: dict[tuple[str, str], set[str]] = defaultdict(set)
    incidence_buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for system, rows in rows_by_system.items():
        for row in rows:
            key = (system, source_record_id(system, row.data))
            tokens = naive_identity_tokens(row)
            record_tokens[key].update(tokens)
            for value in tokens:
                incidence_buckets[value][row.entity_id] += 1
    incidences = different_person_incidences = 0
    for counts in incidence_buckets.values():
        size = sum(counts.values())
        if size > 1:
            incidences += math.comb(size, 2)
            different_person_incidences += math.comb(size, 2) - sum(math.comb(n, 2) for n in counts.values() if n > 1)
    keys = sorted(record_tokens); key_index = {key: index for index, key in enumerate(keys)}
    buckets: dict[str, set[int]] = defaultdict(set)
    for key, tokens in record_tokens.items():
        for value in tokens: buckets[value].add(key_index[key])
    physical_frequency = {value: sum(counts.values()) for value, counts in incidence_buckets.items()}
    high_items = [(value, members) for value, members in buckets.items() if physical_frequency[value] > 40]
    poison_high = [members for value, members in high_items if is_poison_token(value)]
    moderate_high_pairs: set[int] = set()
    for value, members in high_items:
        if is_poison_token(value):
            continue
        for left, right in combinations(sorted(members), 2): moderate_high_pairs.add(_pair_code(left, right))
    rule2_pairs: set[int] = set()
    for value, members in buckets.items():
        if 2 <= len(members) and physical_frequency[value] <= 40:
            for left, right in combinations(sorted(members), 2): rule2_pairs.add(_pair_code(left, right))
    poison_union = _high_frequency_edge_union(poison_high)
    moderate_also_poison = 0
    for code in moderate_high_pairs:
        left, right = code >> 20, code & ((1 << 20) - 1)
        if any(left in members and right in members for members in poison_high): moderate_also_poison += 1
    excluded_union = poison_union + len(moderate_high_pairs) - moderate_also_poison
    normal_also_high = 0
    for code in rule2_pairs:
        left, right = code >> 20, code & ((1 << 20) - 1)
        if code in moderate_high_pairs or any(left in members and right in members for members in poison_high): normal_also_high += 1
    unique_naive = excluded_union + len(rule2_pairs) - normal_also_high
    non_poison_pairs = rule2_pairs | moderate_high_pairs
    poison_overlap_nonpoison = 0
    for code in non_poison_pairs:
        left, right = code >> 20, code & ((1 << 20) - 1)
        if any(left in members and right in members for members in poison_high): poison_overlap_nonpoison += 1
    explicit_pairs: set[int] = set()
    for item in hard_manifest:
        refs = item["source_records"]
        left = key_index.get((refs[0]["system"], refs[0]["record_id"]))
        right = key_index.get((refs[1]["system"], refs[1]["record_id"]))
        if left is not None and right is not None and left != right: explicit_pairs.add(_pair_code(left, right))
    explicit_candidates = len(explicit_pairs & rule2_pairs)
    return {
        "candidate_pair_incidences_before_deduplication": incidences,
        "different_person_candidate_incidences": different_person_incidences,
        "unique_unordered_naive_candidate_pairs": unique_naive,
        "pairs_created_only_through_rule2_values": excluded_union - normal_also_high,
        "pairs_created_only_through_poison_identifiers": poison_union - poison_overlap_nonpoison,
        "rule2_unique_candidate_pairs": len(rule2_pairs),
        "candidate_percentage_after_rule2": len(rule2_pairs) / unique_naive if unique_naive else 0.0,
        "explicit_hard_negative_pairs": len(explicit_pairs),
        "explicit_hard_negative_candidate_pairs": explicit_candidates,
        "explicit_hard_negative_rate_rule2": explicit_candidates / len(rule2_pairs) if rule2_pairs else 0.0,
        "rule2_high_frequency_value_count": len(high_items),
    }


def poison_counts(rows_by_system: dict[str, list[Row]]) -> dict[str, int]:
    counts = Counter()
    for rows in rows_by_system.values():
        for row in rows:
            values = [value for value in identity_view(row.data).values() if not isinstance(value, dict)]
            counts["placeholder_phone"] += "0000000000" in values or "9999999999" in values
            counts["default_dob"] += any(value in {"1900-01-01", "1970-01-01", "01-01-1900", "01-01-1970"} for value in values)
            counts["corporate_email"] += "bookings@events.example" in values
            counts["kiosk_device"] += "KIOSK-DEVICE-1" in values
            counts["test_email"] += any(isinstance(value, str) and value.lower().endswith("@staff.test") for value in values)
    return dict(counts)


def write_outputs(
    output_dir: Path,
    rows_by_system: dict[str, list[Row]],
    hard_manifest: list[dict[str, Any]],
    canonical_links: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for system, filename in (("app_users", "app_users.csv"), ("store_customers", "store_customers.csv")):
        fields = list(rows_by_system[system][0].data)
        with (output_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(row.data for row in rows_by_system[system])
    with (output_dir / "ticketing.jl").open("w", encoding="utf-8") as handle:
        for row in rows_by_system["ticketing"]:
            handle.write(json.dumps(row.data, ensure_ascii=False) + "\n")
    workbook = Workbook(write_only=False)
    subscriptions = workbook.active
    subscriptions.title = "subscriptions"
    subscriptions.append(["Monthly subscriptions export — generated dataset v3 (do not edit)"])
    sub_fields = list(rows_by_system["subscriptions"][0].data)
    subscriptions.append(sub_fields)
    for row in rows_by_system["subscriptions"]:
        subscriptions.append([row.data.get(field) for field in sub_fields])
    notes = workbook.create_sheet("notes")
    notes.append(["exported_at", ANCHOR.isoformat()])
    notes.append(["note", "Auto-generated synthetic assessment data. Do not use for reporting."])
    workbook.save(output_dir / "subscriptions.xlsx")
    with (output_dir / "social_logins.json").open("w", encoding="utf-8") as handle:
        json.dump([row.data for row in rows_by_system["social_logins"]], handle, ensure_ascii=False)
    with (output_dir / "person_map.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("system", "record_id", "person_id", "entity_type"))
        for system, rows in rows_by_system.items():
            for row in rows:
                writer.writerow((system, source_record_id(system, row.data), row.entity_id, row.entity_type))
    with (output_dir / "hard_negatives.json").open("w", encoding="utf-8") as handle:
        json.dump(hard_manifest, handle, indent=2)
    hidden_dir = output_dir / "hidden"
    hidden_dir.mkdir(parents=True, exist_ok=True)
    with (hidden_dir / "canonical_duplicate_links.jsonl").open("w", encoding="utf-8") as handle:
        for link in canonical_links:
            handle.write(json.dumps(link, ensure_ascii=False) + "\n")
    with (output_dir / "generation_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)


def generate(scale: float, output_dir: Path, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    people_count = max(100, round(FULL_PEOPLE * scale))
    total_rows = max(140, round(FULL_ROWS * scale))
    final_counts = allocate(total_rows, FINAL_ROW_WEIGHTS)
    exact_counts = {system: round(count * EXACT_RATE) for system, count in final_counts.items()}
    near_counts = {system: round(count * NEAR_RATE) for system, count in final_counts.items()}
    bot_base_counts = {
        system: max(1, round(count * BOT_RATE) - exact_counts[system] - near_counts[system])
        for system, count in final_counts.items()
    }
    human_counts = {
        system: final_counts[system] - exact_counts[system] - near_counts[system] - bot_base_counts[system]
        for system in final_counts
    }
    if sum(human_counts.values()) < people_count:
        raise ValueError("scale is too small to preserve person/row proportions")
    people = build_people(people_count, rng)
    rng.shuffle(people)
    app_primary = people[: human_counts["app_users"]]
    cursor = len(app_primary)
    store_primary = people[cursor : cursor + human_counts["store_customers"]]
    cursor += len(store_primary)
    subscription_primary = people[cursor : cursor + human_counts["subscriptions"]]
    cursor += len(subscription_primary)
    social_primary = people[cursor:]
    if len(social_primary) > human_counts["social_logins"]:
        raise ValueError("invalid scaled primary allocation")
    # Move a small primary group from app to ticketing, then give the same number
    # of store people an app row. These are genuine cross-system IDs: integer in
    # app_users and zero-padded in store_customers.
    shared_store_count = min(scaled(5_000, scale), len(store_primary), len(app_primary) // 4)
    shared_store_people = rng.sample(store_primary, shared_store_count)
    displaced_app_people = rng.sample(app_primary, shared_store_count)
    displaced_ids = {person.person_id for person in displaced_app_people}
    app_source_people = [person for person in app_primary if person.person_id not in displaced_ids] + shared_store_people

    multi_count = min(round(people_count * 0.25), len(app_source_people))
    additional_multi = rng.sample(
        [person for person in app_source_people if person not in shared_store_people],
        multi_count - len(shared_store_people),
    )
    multi_people = shared_store_people + additional_multi
    multi_ids = {person.person_id for person in multi_people}
    six_count = min(max(1, round(people_count / 600)), multi_count)
    six_people = additional_multi[:six_count]
    ticket_primary_people = displaced_app_people
    ticket_link_people = additional_multi
    ticket_extra_target = human_counts["ticketing"] - len(ticket_primary_people)
    ticket_extra_people = list(ticket_link_people[: min(ticket_extra_target, len(ticket_link_people))])
    ticket_remaining = ticket_extra_target - len(ticket_extra_people)
    if ticket_remaining > 0:
        repeat_candidates = [person for person in ticket_link_people if person not in six_people]
        ticket_extra_people.extend(rng.sample(repeat_candidates, min(ticket_remaining, len(repeat_candidates))))
    while len(ticket_extra_people) < ticket_extra_target:
        ticket_extra_people.append(rng.choice(repeat_candidates or ticket_link_people))
    ticket_people = ticket_primary_people + ticket_extra_people
    social_extra_people: list[Person] = []
    for person in six_people:
        social_extra_people.extend([person] * 4)
    social_extra_target = human_counts["social_logins"] - len(social_primary)
    remaining = social_extra_target - len(social_extra_people)
    eligible = [person for person in multi_people if person not in six_people]
    if remaining > 0:
        social_extra_people.extend(rng.sample(eligible, min(remaining, len(eligible))))
    while len(social_extra_people) < social_extra_target:
        social_extra_people.append(rng.choice(eligible or multi_people))
    social_extra_people = social_extra_people[:social_extra_target]
    planned_counts = Counter(person.person_id for person in app_source_people + store_primary + subscription_primary + social_primary + ticket_people + social_extra_people)
    simple_ticket_people = [person for person in ticket_extra_people if planned_counts[person.person_id] == 2]
    total_true_pairs = sum(math.comb(count, 2) for count in planned_counts.values() if count > 1)
    zero_target = min(round(total_true_pairs * ZERO_EVIDENCE_RATE), len(simple_ticket_people))
    zero_ids = {person.person_id for person in rng.sample(simple_ticket_people, zero_target)}
    modes = ("exact_email", "email_variant", "phone_variant", "name_city", "device_only")
    evidence_mode = {person.person_id: ("zero" if person.person_id in zero_ids else modes[index % len(modes)]) for index, person in enumerate(multi_people)}
    hard_pairs, shared_tokens = apply_hard_negative_profiles(store_primary, subscription_primary, app_source_people, scale, rng)
    rows_by_system: dict[str, list[Row]] = {system: [] for system in final_counts}
    app_id_by_person: dict[str, str] = {}
    for index, person in enumerate(app_source_people, 1):
        rid = record_id("app_users", index)
        app_id_by_person[person.person_id] = rid
        rows_by_system["app_users"].append(make_app_row(person, rid, evidence_mode.get(person.person_id, "regular"), rng))
    for index, person in enumerate(store_primary, 1):
        rows_by_system["store_customers"].append(make_store_row(person, record_id("store_customers", index), app_id_by_person.get(person.person_id, ""), rng))
    late_target = round(final_counts["ticketing"] * LATE_RATE)
    # Only about a quarter of ticket rows expose an account reference because
    # guest and weak-evidence modes intentionally omit it. 1.2% of all human
    # ticket rows therefore becomes roughly 4.5% of the IDs that are present.
    orphan_target = round(human_counts["ticketing"] * 0.014)
    orphan_candidates_seen = 0
    for index, person in enumerate(ticket_people, 1):
        mode = evidence_mode.get(person.person_id, "regular")
        linked_app_id = app_id_by_person.get(person.person_id, "")
        can_expose_account = bool(linked_app_id) and mode in {"regular", "exact_email", "email_variant"}
        if can_expose_account:
            orphan_candidates_seen += 1
        rows_by_system["ticketing"].append(make_ticket_row(
            person, record_id("ticketing", index), linked_app_id, mode,
            index <= late_target, can_expose_account and orphan_candidates_seen <= orphan_target, rng,
        ))
    for index, person in enumerate(subscription_primary, 1):
        rows_by_system["subscriptions"].append(make_subscription_row(person, record_id("subscriptions", index), shared_tokens.get(person.person_id), rng))
    social_people = social_primary + social_extra_people
    for index, person in enumerate(social_people, 1):
        rows_by_system["social_logins"].append(make_social_row(person, record_id("social_logins", index), person.person_id in multi_ids, rng))
    for system, bot_count in bot_base_counts.items():
        for index in range(1, bot_count + 1):
            rows_by_system[system].append(make_bot_row(system, index, rng))
    apply_poison(rows_by_system, ("app_users", "store_customers"), scaled(3_000, scale), multi_ids, {"app_users": "phone", "store_customers": "contact_no"}, "0000000000", rng)
    apply_poison(rows_by_system, ("app_users", "store_customers"), scaled(4_200, scale), multi_ids, {"app_users": "dob", "store_customers": "dob"}, "1970-01-01", rng)
    apply_poison(rows_by_system, ("ticketing",), scaled(900, scale), set(), {"ticketing": "email"}, "bookings@events.example", rng, lambda _system, row: not row.data["guest"])
    apply_poison(rows_by_system, ("app_users", "store_customers"), scaled(40_000, scale), multi_ids, {"app_users": "device_id", "store_customers": "device"}, "KIOSK-DEVICE-1", rng)
    apply_poison(rows_by_system, ("app_users", "store_customers"), scaled(1_500, scale), multi_ids, {"app_users": "email", "store_customers": "customer_email_address"}, "qa+001@staff.test", rng)
    for row in rows_by_system["app_users"]:
        if row.data.get("email") == "qa+001@staff.test":
            row.data["first_name"], row.data["last_name"] = "load-test", "QA"
    apply_impossible_values(rows_by_system, round(total_rows * IMPOSSIBLE_RATE), rng)
    for system in final_counts:
        add_artifacts(system, rows_by_system[system], exact_counts[system], near_counts[system], rng)
        rng.shuffle(rows_by_system[system])
        if len(rows_by_system[system]) != final_counts[system]:
            raise AssertionError(f"{system}: expected {final_counts[system]}, got {len(rows_by_system[system])}")
    human_record_counts = Counter(row.entity_id for rows in rows_by_system.values() for row in rows if row.entity_type == "human")
    zero_count, true_pairs, zero_rate, zero_by_source_pair = measured_zero_evidence(rows_by_system)
    canonical_links, hard_manifest = build_hidden_metadata(rows_by_system, hard_pairs)
    candidate_metrics = candidate_pair_metrics(rows_by_system, hard_manifest)
    canonical_unrecoverable = sum(not link["intended_recoverability"] for link in canonical_links)
    canonical_rate = canonical_unrecoverable / len(canonical_links) if canonical_links else 0.0
    poisons = poison_counts(rows_by_system)
    largest_poisoned_cluster, largest_poisoned_people, largest_poison_causes = naive_poisoned_cluster_metrics(rows_by_system)
    row_counts = {system: len(rows) for system, rows in rows_by_system.items()}
    report = {
        "generation_parameters": {"scale": scale, "seed": seed, "expected_people": people_count, "expected_rows": total_rows},
        "row_counts": row_counts,
        "total_row_count": sum(row_counts.values()),
        "injected_problem_rates": {
            "exact_duplicate_rate": EXACT_RATE, "near_duplicate_rate": NEAR_RATE, "bot_rate": BOT_RATE,
            "internal_test_rate": INTERNAL_TEST_RATE, "late_event_rate": LATE_RATE,
            "impossible_value_rate": IMPOSSIBLE_RATE, "zero_evidence_duplicate_rate": ZERO_EVIDENCE_RATE,
        },
        "measured_problem_rates": {
            "measured_zero_evidence_duplicate_pair_rate": zero_rate, "zero_evidence_pairs": zero_count,
            "true_duplicate_pairs": true_pairs, "zero_evidence_by_source_pair": zero_by_source_pair,
            "canonical_duplicate_links": len(canonical_links),
            "canonical_unrecoverable_links": canonical_unrecoverable,
            "canonical_unrecoverable_rate": canonical_rate,
            **candidate_metrics,
            "duplicate_evidence_mode_counts": dict(Counter(link["evidence_mode"] for link in canonical_links)),
        },
        "true_number_of_distinct_people": len(human_record_counts),
        "true_duplicate_rate_people_with_multiple_records": sum(count > 1 for count in human_record_counts.values()) / len(human_record_counts),
        "people_with_six_or_more_records": sum(count >= 6 for count in human_record_counts.values()),
        "poison_cluster_sizes": poisons,
        "largest_poisoned_cluster_naive_matcher": largest_poisoned_cluster,
        "largest_poisoned_cluster_distinct_true_people": largest_poisoned_people,
        "largest_poisoned_cluster_causes": largest_poison_causes,
        "estimated_largest_poisoned_cluster": largest_poisoned_cluster,
        "definitions": {
            "naive_candidate": "Each exact normalized email, phone, device, account reference, payment token, hash, default DOB, or name+city token creates an incidence. Unique candidates are unordered pairs of distinct source-record keys. Rule 2 removes every value occurring on more than 40 physical rows before the explicit-hard-negative percentage is calculated.",
            "naive_cluster": "Rows are unioned transitively on every naive-candidate evidence token, including default DOB, placeholder phone, kiosk device, corporate email, and staff-test email. The reported largest cluster is the largest connected component containing a poison value.",
            "zero_evidence": "A pair is unrecoverable when its rows share no normalized non-poison evidence token occurring on at most 40 physical rows. Pairwise uses every same-person combination; canonical uses a star of intentionally generated source-record links per multi-record person.",
            "canonical_links": "For each human with multiple unique source-record keys, the first generated key is the anchor and one hidden link connects it to every additional key. This is a smaller denominator than all pairwise combinations for people with three or more records.",
            "missing_identifier": "Actual null, empty/whitespace, quoted-empty, and case-insensitive null/None strings are missing. Emails are artifact-parsed and normalized before a nonempty edge can be created.",
            "explicit_hard_negative": "Only source-record pairs listed in hard_negatives.json, verified to have different hidden person IDs, count as explicit hard negatives.",
            "ground_truth": "person_map.csv includes every physical row; entity_type separates invented humans from automated traffic.",
            "reserved_phone_range": "+999 is unassigned and cannot route to a real subscriber.",
            "timestamp_semantics": "Offset/epoch formats use UTC; LOCAL_TEXT is the same instant rendered at UTC+05:30 with the offset marker deliberately omitted.",
        },
    }
    write_outputs(output_dir, rows_by_system, hard_manifest, canonical_links, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=float, default=1.0, help="proportional size; 0.01 produces about 4,200 rows")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "generated")
    args = parser.parse_args()
    if not 0 < args.scale <= 1:
        parser.error("--scale must be greater than 0 and no more than 1")
    report = generate(args.scale, args.output_dir.resolve(), args.seed)
    print(json.dumps(report, indent=2))
    print(f"\nGenerated files in {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
