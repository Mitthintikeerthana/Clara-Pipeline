"""
Transcript -> Account Memo extraction.

Primary path  : Gemini (free tier via AI Studio).
Fallback path : Rule-based regex extraction (no API key required).

Exported functions
------------------
extract_memo(transcript, account_id)            -> dict   (Pipeline A)
extract_onboarding_updates(transcript, v1_memo) -> dict   (Pipeline B)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from scripts.config import GEMINI_API_KEY
from scripts.utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

# -- Canonical empty memo schema ------------------------------------------------

def _empty_memo(account_id: str) -> dict:
    return {
        "account_id": account_id,
        "company_name": "",
        "business_hours": {
            "days": [],
            "start": "",
            "end": "",
            "timezone": "",
        },
        "office_address": "",
        "services_supported": [],
        "emergency_definition": [],
        "emergency_routing_rules": {
            "contacts": [],
            "fallback": "",
        },
        "non_emergency_routing_rules": {
            "after_hours": "",
            "during_hours": "",
        },
        "call_transfer_rules": {
            "during_hours_primary": "",
            "timeout_rings": 4,
            "retries": 2,
            "on_transfer_fail": "",
        },
        "integration_constraints": [],
        "after_hours_flow_summary": "",
        "office_hours_flow_summary": "",
        "questions_or_unknowns": [],
        "notes": "",
    }


# -- LLM extraction prompts -----------------------------------------------------

_DEMO_EXTRACTION_PROMPT = """\
You are a precise data extraction assistant. Your job is to extract structured information
from a demo sales call transcript between a Clara AI representative and a business owner.

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

Extract ONLY the information explicitly stated in the transcript. Do NOT invent, infer, or
hallucinate any details. If a field is not mentioned, leave it as an empty string or empty list.
Flag genuinely unclear items in "questions_or_unknowns".

Return a single valid JSON object with EXACTLY this structure:

{{
  "account_id": "{account_id}",
  "company_name": "...",
  "business_hours": {{
    "days": ["Monday", "Tuesday", ...],
    "start": "HH:MM",
    "end": "HH:MM",
    "timezone": "US timezone name"
  }},
  "office_address": "full street address or empty string",
  "services_supported": ["service1", "service2"],
  "emergency_definition": ["trigger1", "trigger2"],
  "emergency_routing_rules": {{
    "contacts": [
      {{"name": "...", "phone": "...", "order": 1}},
      {{"name": "...", "phone": "...", "order": 2}}
    ],
    "fallback": "what happens if all contacts fail"
  }},
  "non_emergency_routing_rules": {{
    "after_hours": "what to do with non-emergency after-hours calls",
    "during_hours": "how non-emergency daytime calls are handled"
  }},
  "call_transfer_rules": {{
    "during_hours_primary": "phone or extension for daytime transfers",
    "timeout_rings": 4,
    "retries": 1,
    "on_transfer_fail": "what to do if transfer fails"
  }},
  "integration_constraints": ["constraint1", "constraint2"],
  "after_hours_flow_summary": "one-sentence summary of after-hours call handling",
  "office_hours_flow_summary": "one-sentence summary of business-hours call handling",
  "questions_or_unknowns": ["item if truly unclear or missing"],
  "notes": "any other relevant operational details"
}}

Return ONLY the JSON object, no markdown fences, no explanations.
"""

_ONBOARDING_UPDATE_PROMPT = """\
You are a precise data extraction assistant. Your job is to extract CHANGES and UPDATES
from an onboarding call transcript and express them as a JSON patch to apply on top of
an existing v1 account memo.

EXISTING V1 MEMO:
\"\"\"
{v1_memo_json}
\"\"\"

ONBOARDING TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

Extract ONLY changes that are explicitly stated in the onboarding transcript.
Do NOT invent changes. If the transcript confirms an existing value without changing it,
do NOT include it in the patch.

Return a single valid JSON object with this structure:

{{
  "account_id": "{account_id}",
  "patches": [
    {{
      "field_path": "dot.separated.field.path",
      "old_value": <value from v1 or null if new>,
      "new_value": <updated value>,
      "reason": "brief reason from the transcript"
    }}
  ],
  "questions_or_unknowns": ["anything still unclear after onboarding"]
}}

Field path examples: "business_hours.days", "emergency_routing_rules.contacts",
"services_supported", "call_transfer_rules.during_hours_primary"

For list fields (e.g. services_supported, emergency_definition, contacts), provide the
entire updated list as new_value.

Return ONLY the JSON object, no markdown fences, no explanations.
"""


# -- LLM-based extraction -------------------------------------------------------

def _llm_extract_memo(transcript: str, account_id: str) -> dict:
    prompt = _DEMO_EXTRACTION_PROMPT.format(
        transcript=transcript.strip(),
        account_id=account_id,
    )
    data = call_llm_json(prompt)
    # Ensure account_id is always correct
    data["account_id"] = account_id
    return data


def _llm_extract_updates(transcript: str, v1_memo: dict) -> dict:
    prompt = _ONBOARDING_UPDATE_PROMPT.format(
        v1_memo_json=json.dumps(v1_memo, indent=2),
        transcript=transcript.strip(),
        account_id=v1_memo.get("account_id", ""),
    )
    return call_llm_json(prompt)


# -- Rule-based fallback extraction (no API key required) ----------------------

_TIMEZONE_MAP = {
    "eastern": "America/New_York",
    "central": "America/Chicago",
    "mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "et": "America/New_York",
    "ct": "America/Chicago",
    "mt": "America/Denver",
    "pt": "America/Los_Angeles",
}

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(\d{3}[-.\s]\d{3}[-.\s]\d{4})\b")
_STREET_TYPES = r"(?:Street|Avenue|Road|Boulevard|Lane|Drive|Way|Court|Place|St|Ave|Rd|Blvd|Ln|Dr|Ct|Pl)"
_ADDRESS_RE = re.compile(
    r"\b\d+\s+[A-Za-z][A-Za-z\s]+" + _STREET_TYPES + r"\b[^.]*",
    re.IGNORECASE,
)


def _parse_time(text: str) -> str:
    m = _TIME_RE.search(text)
    if not m:
        return ""
    h, mn, am_pm = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    if am_pm == "pm" and h != 12:
        h += 12
    if am_pm == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mn:02d}"


def _extract_days(text: str) -> list[str]:
    lower = text.lower()
    # Handle "Monday through Friday" ranges
    range_m = re.search(
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"\s+(?:through|to|thru|-)\s+"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        lower,
    )
    if range_m:
        start_day = _DAY_NAMES.index(range_m.group(1))
        end_day = _DAY_NAMES.index(range_m.group(2))
        indices = list(range(start_day, end_day + 1)) if end_day >= start_day else list(range(start_day, 7)) + list(range(0, end_day + 1))
        return [_DAY_NAMES[i].capitalize() for i in indices]
    return [d.capitalize() for d in _DAY_NAMES if d in lower]


# Industry keywords that anchor the end of a company name
_INDUSTRY = r"(?:HVAC|Plumbing|Electrical|Heating|Cooling|Comfort|Air|Services|Systems|Solutions|Mechanical)"

# Match 1-4 title-case words (with optional "&") followed by an industry keyword.
# Handles: "ACE Plumbing & HVAC", "Blue Ridge Heating & Air", "Coastal Comfort Systems"
_COMPANY_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z]+ (?:& )?){1,4}" + _INDUSTRY + r")\b"
)
_HOURS_CONTEXT_RE = re.compile(r"\b(?:open|hours|monday|tuesday|available)\b", re.IGNORECASE)
_EMERGENCY_PATTERNS = [
    r"burst pipe", r"gas leak", r"no (?:heat|AC|air)",
    r"sewage backup", r"carbon monoxide", r"flooding", r"sparking",
    r"no power", r"boiler failure", r"complete.*failure",
]






def _extract_company_name(transcript: str) -> str:
    m = _COMPANY_RE.search(transcript)
    return m.group(1).strip() if m else ""


def _extract_hours_from_lines(lines: list[str]) -> dict:
    result: dict[str, Any] = {}
    for i in range(len(lines)):
        ctx = " ".join(lines[max(0, i - 1) : i + 2])
        if not _HOURS_CONTEXT_RE.search(ctx):
            continue
        days = _extract_days(ctx)
        if days:
            result["days"] = days
        times = _TIME_RE.findall(ctx)
        if len(times) >= 2:
            result["start"] = _parse_time(f"{times[0][0]}:{times[0][1]} {times[0][2]}")
            result["end"] = _parse_time(f"{times[1][0]}:{times[1][1]} {times[1][2]}")
    return result


def _extract_timezone(transcript: str) -> str:
    # Require the keyword to be adjacent to "time", "timezone", or abbreviation context
    # e.g. "Mountain Time", "Eastern Time", "PT", "ET"
    for tz_key, tz_val in _TIMEZONE_MAP.items():
        if re.search(r"(?:^|\s)" + tz_key + r"\s+time\b", transcript, re.I):
            return tz_val
    # Fallback: look for two-letter abbreviations (PT, ET, CT, MT) in parentheses or standalone
    for tz_key, tz_val in _TIMEZONE_MAP.items():
        if len(tz_key) == 2 and re.search(r"\b" + tz_key.upper() + r"\b", transcript):
            return tz_val
    return ""


def _extract_emergency_triggers(transcript: str) -> list[str]:
    triggers = []
    for pattern in _EMERGENCY_PATTERNS:
        if re.search(pattern, transcript, re.I):
            snippet = re.search(rf".{{0,50}}{pattern}.{{0,50}}", transcript, re.I)
            if snippet:
                triggers.append(snippet.group(0).strip())
    return list(set(triggers))


def _rule_based_extract(transcript: str, account_id: str) -> dict:
    """
    Best-effort extraction using regex patterns.
    Used when GEMINI_API_KEY is not set.
    """
    memo = _empty_memo(account_id)
    lines = transcript.strip().splitlines()

    memo["company_name"] = _extract_company_name(transcript)

    hours = _extract_hours_from_lines(lines)
    memo["business_hours"].update(hours)
    memo["business_hours"]["timezone"] = _extract_timezone(transcript)

    addr = _ADDRESS_RE.search(transcript)
    if addr:
        memo["office_address"] = addr.group(0).strip().rstrip(",")

    phones = _PHONE_RE.findall(transcript)
    for idx, ph in enumerate(phones[:3], start=1):
        memo["emergency_routing_rules"]["contacts"].append(
            {"name": f"Contact {idx}", "phone": ph, "order": idx}
        )

    memo["emergency_definition"] = _extract_emergency_triggers(transcript)

    memo["notes"] = (
        "Extracted via rule-based fallback (no GEMINI_API_KEY). "
        "Review all fields for accuracy."
    )
    memo["questions_or_unknowns"].append(
        "Full extraction not available - set GEMINI_API_KEY for LLM-based extraction."
    )
    return memo


# -- Apply patch to memo --------------------------------------------------------

def _set_nested(obj: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys[:-1]:
        obj = obj.setdefault(key, {})
    obj[keys[-1]] = value


def _get_nested(obj: dict, path: str) -> Any:
    keys = path.split(".")
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def apply_patches(v1_memo: dict, patch_result: dict) -> dict:
    """
    Apply onboarding patches to a v1 memo, returning the updated v2 memo.
    """
    import copy
    v2 = copy.deepcopy(v1_memo)
    for patch in patch_result.get("patches", []):
        path = patch.get("field_path", "")
        new_val = patch.get("new_value")
        if path and new_val is not None:
            _set_nested(v2, path, new_val)
            logger.info("Patched %s -> %s", path, repr(new_val)[:80])

    # Merge unknowns from onboarding
    existing = v2.get("questions_or_unknowns", [])
    new_unknowns = patch_result.get("questions_or_unknowns", [])
    v2["questions_or_unknowns"] = existing + new_unknowns

    return v2


# -- Public API -----------------------------------------------------------------

def extract_memo(transcript: str, account_id: str) -> dict:
    """
    Extract a full account memo from a demo call transcript.
    Uses LLM if GEMINI_API_KEY is set, otherwise falls back to rule-based.
    """
    if GEMINI_API_KEY:
        try:
            logger.info("Extracting memo via LLM for %s", account_id)
            return _llm_extract_memo(transcript, account_id)
        except Exception as exc:
            logger.warning("LLM extraction failed (%s); falling back to rule-based.", exc)

    logger.info("Extracting memo via rule-based fallback for %s", account_id)
    return _rule_based_extract(transcript, account_id)


def extract_onboarding_updates(transcript: str, v1_memo: dict) -> dict:
    """
    Extract a patch dict from an onboarding call transcript.
    Uses LLM if available; returns empty patch list otherwise.
    """
    account_id = v1_memo.get("account_id", "unknown")
    if GEMINI_API_KEY:
        try:
            logger.info("Extracting onboarding updates via LLM for %s", account_id)
            return _llm_extract_updates(transcript, v1_memo)
        except Exception as exc:
            logger.warning("LLM update extraction failed (%s).", exc)

    logger.warning(
        "Rule-based onboarding update extraction not supported. "
        "Set GEMINI_API_KEY for onboarding diff extraction."
    )
    return {
        "account_id": account_id,
        "patches": [],
        "questions_or_unknowns": [
            "Onboarding LLM extraction unavailable - set GEMINI_API_KEY."
        ],
    }
