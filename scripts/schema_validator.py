from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "account_id": str,
    "company_name": str,
}

REQUIRED_BUSINESS_HOURS = {
    "days": list,
    "start": str,
    "end": str,
    "timezone": str,
}

REQUIRED_EMERGENCY_ROUTING = {
    "contacts": list,
    "fallback": str,
}

REQUIRED_CALL_TRANSFER = {
    "during_hours_primary": str,
    "timeout_rings": int,
    "retries": int,
    "on_transfer_fail": str,
}

SUPPORTED_INDUSTRIES = [
    "Fire protection",
    "Sprinkler contractors",
    "Alarm contractors",
    "Electrical service",
    "HVAC",
    "Facility maintenance",
    "Plumbing",
    "Heating",
    "Cooling",
]

VALID_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
]

VALID_DAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
]


class ValidationResult:
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.is_valid = True
        self.is_complete = True
        self.is_demo_derived = False
        self.is_onboarding_confirmed = False

    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        self.warnings.append(message)
        self.is_complete = False

    def add_info(self, message: str):
        self.info.append(message)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "is_valid": self.is_valid,
            "is_complete": self.is_complete,
            "is_demo_derived": self.is_demo_derived,
            "is_onboarding_confirmed": self.is_onboarding_confirmed,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }

    def __repr__(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        complete = "complete" if self.is_complete else "incomplete"
        return f"ValidationResult({self.account_id}: {status}, {complete})"


def _check_metadata_source(metadata: dict, result: ValidationResult) -> None:
    source = metadata.get("_source", "")
    if source == "demo":
        result.is_demo_derived = True
        result.add_info("This configuration is demo-derived (preliminary)")
    elif source in ("onboarding", "onboarding_form"):
        result.is_onboarding_confirmed = True
        result.add_info(f"This configuration is {source.replace('_', ' ')}-confirmed")


def _check_required_fields(memo: dict, result: ValidationResult) -> None:
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in memo:
            result.add_error(f"Missing required field: {field}")
        elif not isinstance(memo[field], expected_type):
            result.add_error(f"Field {field} has wrong type: expected {expected_type.__name__}")
        elif not memo[field] and expected_type == str:
            result.add_error(f"Field {field} is empty")


def _check_unknowns_and_flags(memo: dict, metadata: dict, result: ValidationResult) -> None:
    unknowns = memo.get("questions_or_unknowns", [])
    if unknowns:
        result.add_warning(f"{len(unknowns)} unknown(s) flagged: {', '.join(unknowns[:3])}")
        if len(unknowns) > 3:
            result.add_warning(f"  ... and {len(unknowns) - 3} more")

    for flag, is_complete in metadata.get("_confidence_flags", {}).items():
        if not is_complete:
            result.add_warning(f"Demo confidence flag: {flag} is incomplete")


def validate_account_memo(memo: dict) -> ValidationResult:
    account_id = memo.get("account_id", "unknown")
    result = ValidationResult(account_id)
    metadata = memo.get("_metadata", {})

    _check_metadata_source(metadata, result)
    _check_required_fields(memo, result)
    _validate_business_hours(memo.get("business_hours", {}), result)
    _validate_emergency_routing(memo.get("emergency_routing_rules", {}), result)
    _validate_call_transfer(memo.get("call_transfer_rules", {}), result)
    _check_unknowns_and_flags(memo, metadata, result)

    if not memo.get("services_supported"):
        result.add_warning("No services_supported defined")

    if not memo.get("emergency_definition"):
        result.add_warning("No emergency_definition - agent may not properly identify emergencies")

    return result


def _validate_business_hours(bh: dict, result: ValidationResult) -> None:
    if not bh:
        result.add_error("business_hours is missing or empty")
        return

    for field, expected_type in REQUIRED_BUSINESS_HOURS.items():
        if field not in bh:
            result.add_error(f"business_hours.{field} is missing")
        elif not isinstance(bh[field], expected_type):
            result.add_warning(f"business_hours.{field} has unexpected type")

    days = bh.get("days", [])
    if not days:
        result.add_error("business_hours.days is empty - agent cannot determine open/closed status")
    else:
        invalid_days = [d for d in days if d not in VALID_DAYS]
        if invalid_days:
            result.add_warning(f"Invalid day names: {invalid_days}")

    tz = bh.get("timezone", "")
    if tz and tz not in VALID_TIMEZONES:
        result.add_warning(f"Unknown timezone: {tz}")

    for time_field in ["start", "end"]:
        time_val = bh.get(time_field, "")
        if time_val and not _is_valid_time_format(time_val):
            result.add_warning(f"business_hours.{time_field} has invalid time format: {time_val}")


def _validate_emergency_routing(er: dict, result: ValidationResult) -> None:
    if not er:
        result.add_error("emergency_routing_rules is missing - critical for after-hours calls")
        return

    contacts = er.get("contacts", [])
    if not contacts:
        result.add_error("emergency_routing_rules.contacts is empty - no one to call for emergencies")
    elif len(contacts) < 2:
        result.add_warning("Only one emergency contact - consider adding backup")

    for i, contact in enumerate(contacts):
        if not isinstance(contact, dict):
            result.add_error(f"emergency_routing_rules.contacts[{i}] is not an object")
            continue
        if "phone" not in contact:
            result.add_error(f"emergency_routing_rules.contacts[{i}] missing 'phone'")
        if "order" not in contact:
            result.add_warning(f"emergency_routing_rules.contacts[{i}] missing 'order'")

    if not er.get("fallback", ""):
        result.add_warning("emergency_routing_rules.fallback is empty")


def _validate_call_transfer(ct: dict, result: ValidationResult) -> None:
    if not ct:
        result.add_warning("call_transfer_rules is missing - using defaults")
        return

    if not ct.get("during_hours_primary", ""):
        result.add_warning("call_transfer_rules.during_hours_primary is empty - daytime calls won't transfer")

    timeout = ct.get("timeout_rings", 4)
    if not isinstance(timeout, int) or timeout < 1:
        result.add_warning("call_transfer_rules.timeout_rings should be a positive integer")

    retries = ct.get("retries", 1)
    if not isinstance(retries, int) or retries < 0:
        result.add_warning("call_transfer_rules.retries should be a non-negative integer")


def _is_valid_time_format(time_str: str) -> bool:
    if not time_str or len(time_str) != 5:
        return False
    parts = time_str.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def validate_agent_spec(spec: dict) -> ValidationResult:
    account_id = spec.get("agent_name", "unknown").split(" - ")[0] if " - " in spec.get("agent_name", "") else "unknown"
    result = ValidationResult(account_id)

    for field in ["agent_name", "response_engine", "voice_id", "begin_message"]:
        if field not in spec:
            result.add_error(f"Missing required agent spec field: {field}")

    response_engine = spec.get("response_engine", {})
    if not response_engine:
        result.add_error("response_engine is missing")
    elif "system_prompt" not in response_engine:
        result.add_error("response_engine.system_prompt is missing")
    elif len(response_engine["system_prompt"]) < 100:
        result.add_warning("System prompt may be too short")

    if not spec.get("voice_id", ""):
        result.add_warning("voice_id is empty - Retell will use default")

    if not spec.get("key_variables", {}):
        result.add_warning("key_variables is empty - agent may lack context")

    if not spec.get("call_transfer_protocol", {}):
        result.add_warning("call_transfer_protocol is missing")

    return result


def get_completeness_score(memo: dict) -> dict:
    bh = memo.get("business_hours", {})
    bh_score = sum([
        25 if bh.get("days") else 0,
        25 if bh.get("start") else 0,
        25 if bh.get("end") else 0,
        25 if bh.get("timezone") else 0,
    ])

    er = memo.get("emergency_routing_rules", {})
    er_score = (60 if er.get("contacts") else 0) + (40 if er.get("fallback") else 0)

    ct = memo.get("call_transfer_rules", {})
    ct_score = sum([
        40 if ct.get("during_hours_primary") else 0,
        20 if ct.get("timeout_rings") else 0,
        20 if ct.get("retries") else 0,
        20 if ct.get("on_transfer_fail") else 0,
    ])

    services_score = min(100, len(memo.get("services_supported", [])) * 20)
    constraints_score = 100 if memo.get("integration_constraints") else 50

    weights = {
        "business_hours": (bh_score, 0.25),
        "emergency_routing": (er_score, 0.30),
        "call_transfer": (ct_score, 0.20),
        "services": (services_score, 0.15),
        "constraints": (constraints_score, 0.10),
    }

    overall = round(sum(score * w for score, w in weights.values()), 1)

    return {
        "business_hours": bh_score,
        "emergency_routing": er_score,
        "call_transfer": ct_score,
        "services": services_score,
        "constraints": constraints_score,
        "overall": overall,
    }
