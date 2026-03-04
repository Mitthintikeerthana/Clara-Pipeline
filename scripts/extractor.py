from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from scripts.config import GEMINI_API_KEY
from scripts.utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

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
        "services_excluded": [],
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
            "timeout_seconds": None,
            "retries": 2,
            "on_transfer_fail": "",
            "notify_dispatch_on_fail": False,
        },
        "integration_constraints": [],
        "special_constraints": [],
        "after_hours_flow_summary": "",
        "office_hours_flow_summary": "",
        "questions_or_unknowns": [],
        "notes": "",
    }

_DEMO_EXTRACTION_PROMPT = """\
You are a precise data extraction assistant. Your job is to extract structured information
from a demo sales call transcript between a Clara AI representative and a business owner.

CONTEXT: Clara Answers is an AI voice agent for service trade businesses including:
- Fire protection companies
- Sprinkler and alarm contractors
- Electrical service providers
- HVAC and facility maintenance companies

These businesses handle: emergency calls, non-emergency service requests, inspection
scheduling, after-hours routing, and integration constraints (e.g., ServiceTrade).

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

CRITICAL RULES:
1. Extract ONLY information explicitly stated. Do NOT invent, infer, or hallucinate.
2. The demo call is EXPLORATORY - business hours, emergency definitions, routing rules,
   and integration constraints may be incomplete or vague.
3. If a field is not mentioned, leave it empty and flag it in "questions_or_unknowns".
4. Mark demo-derived assumptions with "_source": "demo" in the metadata field.
5. Flag missing critical config: business_hours, emergency_routing, transfer_rules, integrations.

Return a single valid JSON object with EXACTLY this structure:

{{
  "account_id": "{account_id}",
  "company_name": "...",
  "business_hours": {{
    "days": ["Monday", "Tuesday", ...],
    "start": "HH:MM",
    "end": "HH:MM",
    "timezone": "America/Phoenix"
  }},
  "office_address": "full street address or empty string",
  "services_supported": ["service1", "service2"],
  "services_excluded": ["services we do NOT offer"],
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
    "timeout_seconds": null,
    "retries": 1,
    "on_transfer_fail": "what to do if transfer fails",
    "notify_dispatch_on_fail": false
  }},
  "integration_constraints": ["e.g. never create jobs in ServiceTrade for X"],
  "special_constraints": ["service-specific or operational routing rules, e.g. all sprinkler emergencies go directly to phone tree"],
  "after_hours_flow_summary": "one-sentence summary of after-hours call handling",
  "office_hours_flow_summary": "one-sentence summary of business-hours call handling",
  "questions_or_unknowns": [
    "list any critical config NOT discussed: business hours, emergency triggers, routing, integrations"
  ],
  "notes": "any other relevant operational details",
  "_metadata": {{
    "_source": "demo",
    "_extraction_timestamp": "{timestamp}",
    "_confidence_flags": {{
      "business_hours_complete": false,
      "emergency_routing_complete": false,
      "integration_constraints_complete": false
    }}
  }}
}}

Return ONLY the JSON object, no markdown fences, no explanations.
"""

_ONBOARDING_UPDATE_PROMPT = """\
You are a precise data extraction assistant. Your job is to extract CHANGES and UPDATES
from an onboarding call transcript and express them as a JSON patch to apply on top of
an existing v1 account memo.

CONTEXT: The onboarding call is CONFIGURATION-FOCUSED. This is where:
- Exact business hours are confirmed
- Time zones are finalized
- Emergency definitions are clearly defined
- After-hours routing logic is specified
- Transfer timeouts are decided (may be in seconds, e.g. "60 seconds" -> timeout_seconds: 60)
- Fallback logic is clarified (e.g. "if transfer fails, notify dispatch" -> notify_dispatch_on_fail: true)
- Integration rules are confirmed (e.g. "never create sprinkler jobs in ServiceTrade")
- Special constraints are introduced (e.g. "all emergency sprinkler calls go directly to the phone tree",
  "non-emergency extinguisher calls can be collected after hours without transfer")

NEW FIELDS TO WATCH FOR:
- call_transfer_rules.timeout_seconds: if a specific timeout in seconds is stated
- call_transfer_rules.notify_dispatch_on_fail: true if dispatch must be notified when all transfers fail
- special_constraints: service-specific or operational routing rules not covered by standard flow

EXISTING V1 MEMO (demo-derived, may have incomplete assumptions):
\"\"\"
{v1_memo_json}
\"\"\"

ONBOARDING TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"

CRITICAL RULES:
1. Extract ONLY changes explicitly stated in the onboarding transcript.
2. Do NOT invent changes. If the transcript confirms an existing value without changing it,
   do NOT include it in the patch.
3. Onboarding OVERRIDES or REFINES demo assumptions - resolve conflicts explicitly.
4. For list fields (services_supported, emergency_definition, contacts), provide the
   ENTIRE updated list as new_value.
5. Mark onboarding-confirmed fields with "_source": "onboarding" in metadata.
6. Flag any remaining unknowns after onboarding.

Return a single valid JSON object with this structure:

{{
  "account_id": "{account_id}",
  "patches": [
    {{
      "field_path": "dot.separated.field.path",
      "old_value": <value from v1 or null if new>,
      "new_value": <updated value>,
      "reason": "brief reason from the transcript",
      "change_type": "added|modified|removed|confirmed"
    }}
  ],
  "questions_or_unknowns": ["anything still unclear after onboarding"],
  "_metadata": {{
    "_source": "onboarding",
    "_extraction_timestamp": "{timestamp}",
    "_conflicts_resolved": [
      {{
        "field": "field.path",
        "demo_value": "...",
        "onboarding_value": "...",
        "resolution": "onboarding overrides demo"
      }}
    ]
  }}
}}

Field path examples: "business_hours.days", "emergency_routing_rules.contacts",
"services_supported", "call_transfer_rules.during_hours_primary"

Change types:
- "added": new field or list item
- "modified": existing value changed
- "removed": value removed
- "confirmed": onboarding explicitly confirmed demo assumption (no change)

Return ONLY the JSON object, no markdown fences, no explanations.
"""

def _llm_extract_memo(transcript: str, account_id: str) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = _DEMO_EXTRACTION_PROMPT.format(
        transcript=transcript.strip(),
        account_id=account_id,
        timestamp=timestamp,
    )
    data = call_llm_json(prompt)
    data["account_id"] = account_id
    return data

def _llm_extract_updates(transcript: str, v1_memo: dict) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = _ONBOARDING_UPDATE_PROMPT.format(
        v1_memo_json=json.dumps(v1_memo, indent=2),
        transcript=transcript.strip(),
        account_id=v1_memo.get("account_id", ""),
        timestamp=timestamp,
    )
    return call_llm_json(prompt)

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

_INDUSTRY = r"(?:HVAC|Plumbing|Electrical|Heating|Cooling|Comfort|Air|Services|Systems|Solutions|Mechanical)"

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
    for tz_key, tz_val in _TIMEZONE_MAP.items():
        if re.search(r"(?:^|\s)" + tz_key + r"\s+time\b", transcript, re.I):
            return tz_val
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

def _set_nested(obj: dict, path: str, value: Any) -> None:
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

def _is_meaningful(val: Any) -> bool:
    return val is not None and val != "" and val != [] and val != {}


def apply_patches(v1_memo: dict, patch_result: dict) -> dict:
    import copy
    v2 = copy.deepcopy(v1_memo)
    source = patch_result.get("_metadata", {}).get("_source", "onboarding")

    for patch in patch_result.get("patches", []):
        path = patch.get("field_path", "")
        new_val = patch.get("new_value")
        if not path or new_val is None:
            continue
        old_val = _get_nested(v2, path)
        if _is_meaningful(old_val) and old_val != new_val:
            logger.info(
                "Conflict resolved [%s]: %s | was: %s -> now: %s",
                source, path, repr(old_val)[:60], repr(new_val)[:60],
            )
        _set_nested(v2, path, new_val)
        logger.info("Patched [%s] %s -> %s", source, path, repr(new_val)[:80])

    existing = v2.get("questions_or_unknowns", [])
    new_unknowns = patch_result.get("questions_or_unknowns", [])
    v2["questions_or_unknowns"] = existing + new_unknowns

    if "_metadata" in patch_result:
        if "_metadata" not in v2:
            v2["_metadata"] = {}
        v2["_metadata"].update(patch_result["_metadata"])

    return v2

_ONBOARDING_FORM_PROMPT = """\
You are a precise data extraction assistant. Your job is to merge a structured client
onboarding form with an existing v1 account memo derived from a demo call.

EXISTING V1 MEMO (demo-derived, may have incomplete assumptions):
\"\"\"
{v1_memo_json}
\"\"\"

CLIENT ONBOARDING FORM (authoritative — client-submitted):
\"\"\"
{form_data_json}
\"\"\"

CONFLICT RESOLUTION HIERARCHY (highest to lowest authority):
  1. Client onboarding form (this document — most authoritative)
  2. Demo call memo (v1 — preliminary assumptions only)

CRITICAL RULES:
1. Form data ALWAYS overrides demo assumptions. The form is the client's authoritative intent.
2. Detect and explicitly flag every conflict between form data and v1 memo.
3. Preserve ALL fields from v1 that are NOT mentioned in the form — do not remove them.
4. Clarify missing demo details: if the form fills in a field that was empty/unknown in v1, mark it "added".
5. Introduce new constraints: if the form adds fields not in v1, include them as "added" patches.
6. Mark form-derived fields with "_source": "onboarding_form" in metadata.
7. Flag any fields in the form that are ambiguous or require manual review.

Return a single valid JSON object with this structure:

{{
  "account_id": "{account_id}",
  "patches": [
    {{
      "field_path": "dot.separated.field.path",
      "old_value": <value from v1 or null if new>,
      "new_value": <value from form>,
      "reason": "brief reason: e.g. 'clarifies demo assumption', 'new constraint from client', 'overrides assumed value'",
      "change_type": "added|modified|removed|confirmed",
      "source": "onboarding_form"
    }}
  ],
  "conflicts": [
    {{
      "field": "field.path",
      "v1_value": "value in v1 memo",
      "form_value": "value in form",
      "resolution": "form overrides v1 — [brief reason why form value is correct]",
      "requires_review": false
    }}
  ],
  "questions_or_unknowns": ["anything still unclear or requiring manual review after form merge"],
  "_metadata": {{
    "_source": "onboarding_form",
    "_extraction_timestamp": "{timestamp}",
    "_form_merged": true,
    "_conflict_count": <number of conflicts detected>,
    "_fields_clarified": <number of previously-empty fields now filled>
  }}
}}

Change type guidance:
- "added": form fills a field that was empty/null/[] in v1
- "modified": form changes an existing non-empty v1 value (ALWAYS flag as conflict too)
- "removed": form explicitly removes a value (rare)
- "confirmed": form matches v1 exactly (no change needed — include to show explicit confirmation)

Return ONLY the JSON object, no markdown fences, no explanations.
"""

_RULE_BASED_REASON = "Detected via rule-based onboarding scan"


def _make_patch(field_path: str, v1_val: Any, new_val: Any, reason: str) -> dict:
    return {
        "field_path": field_path,
        "old_value": v1_val,
        "new_value": new_val,
        "reason": reason,
        "change_type": "added" if not v1_val else "modified",
    }


def _diff_scalar_fields(rough: dict, v1_memo: dict) -> list[dict]:
    patches = []
    for field in ("office_address", "company_name"):
        v1_val = v1_memo.get(field, "")
        new_val = rough.get(field, "")
        if new_val and new_val != v1_val:
            patches.append(_make_patch(field, v1_val, new_val, _RULE_BASED_REASON))
    return patches


def _diff_business_hours(rough: dict, v1_memo: dict) -> list[dict]:
    patches = []
    bh_v1 = v1_memo.get("business_hours", {})
    bh_new = rough.get("business_hours", {})
    for sub in ("days", "start", "end", "timezone"):
        v1_val = bh_v1.get(sub)
        new_val = bh_new.get(sub)
        if new_val and new_val != v1_val:
            patches.append(_make_patch(f"business_hours.{sub}", v1_val, new_val, _RULE_BASED_REASON))
    return patches


def _diff_emergency_data(rough: dict, v1_memo: dict) -> list[dict]:
    patches = []
    er_v1 = v1_memo.get("emergency_routing_rules", {})
    er_new = rough.get("emergency_routing_rules", {})
    new_contacts = er_new.get("contacts", [])
    if new_contacts and new_contacts != er_v1.get("contacts", []):
        patches.append({
            "field_path": "emergency_routing_rules.contacts",
            "old_value": er_v1.get("contacts", []),
            "new_value": new_contacts,
            "reason": "Phone numbers detected in onboarding transcript",
            "change_type": "modified",
        })
    new_triggers = rough.get("emergency_definition", [])
    if new_triggers and new_triggers != v1_memo.get("emergency_definition", []):
        patches.append({
            "field_path": "emergency_definition",
            "old_value": v1_memo.get("emergency_definition", []),
            "new_value": new_triggers,
            "reason": "Emergency triggers detected in onboarding transcript",
            "change_type": "modified",
        })
    return patches


def _merge_form_recursive(
    form: dict,
    base: dict,
    path: str,
    patches: list[dict],
    conflicts: list[dict],
) -> None:
    for key, form_val in form.items():
        if key.startswith("_"):
            continue
        current_path = f"{path}.{key}" if path else key
        if key not in base:
            base[key] = form_val
            patches.append({
                "field_path": current_path,
                "old_value": None,
                "new_value": form_val,
                "reason": "onboarding form - new field",
                "change_type": "added",
            })
        elif isinstance(form_val, dict) and isinstance(base[key], dict):
            _merge_form_recursive(form_val, base[key], current_path, patches, conflicts)
        elif base[key] != form_val:
            conflicts.append({"field": current_path, "v1_value": base[key], "form_value": form_val, "resolution": "form overrides v1"})
            patches.append({
                "field_path": current_path,
                "old_value": base[key],
                "new_value": form_val,
                "reason": "onboarding form - override",
                "change_type": "modified",
            })
            base[key] = form_val


def _llm_merge_form(form_data: dict, v1_memo: dict) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    prompt = _ONBOARDING_FORM_PROMPT.format(
        v1_memo_json=json.dumps(v1_memo, indent=2),
        form_data_json=json.dumps(form_data, indent=2),
        account_id=v1_memo.get("account_id", ""),
        timestamp=timestamp,
    )
    return call_llm_json(prompt)

def merge_onboarding_form(form_data: dict, v1_memo: dict) -> dict:
    account_id = v1_memo.get("account_id", "unknown")
    
    if GEMINI_API_KEY:
        try:
            logger.info("Merging onboarding form via LLM for %s", account_id)
            return _llm_merge_form(form_data, v1_memo)
        except Exception as exc:
            logger.warning("LLM form merge failed (%s); falling back to direct merge.", exc)
    
    import copy
    result = copy.deepcopy(v1_memo)
    conflicts: list[dict] = []
    patches: list[dict] = []
    _merge_form_recursive(form_data, result, "", patches, conflicts)
    
    return {
        "account_id": account_id,
        "patches": patches,
        "conflicts": conflicts,
        "questions_or_unknowns": v1_memo.get("questions_or_unknowns", []),
        "_metadata": {
            "_source": "onboarding_form",
            "_extraction_timestamp": datetime.now(timezone.utc).isoformat(),
            "_form_merged": True,
            "_fallback_merge": not GEMINI_API_KEY
        }
    }

def extract_memo(transcript: str, account_id: str) -> dict:
    if GEMINI_API_KEY:
        try:
            logger.info("Extracting memo via LLM for %s", account_id)
            return _llm_extract_memo(transcript, account_id)
        except Exception as exc:
            logger.warning("LLM extraction failed (%s); falling back to rule-based.", exc)

    logger.info("Extracting memo via rule-based fallback for %s", account_id)
    return _rule_based_extract(transcript, account_id)

def _rule_based_onboarding_diff(transcript: str, v1_memo: dict) -> dict:
    account_id = v1_memo.get("account_id", "unknown")
    rough = _rule_based_extract(transcript, account_id)
    patches = (
        _diff_scalar_fields(rough, v1_memo)
        + _diff_business_hours(rough, v1_memo)
        + _diff_emergency_data(rough, v1_memo)
    )

    return {
        "account_id": account_id,
        "patches": patches,
        "questions_or_unknowns": [
            "Rule-based onboarding extraction used - set GEMINI_API_KEY for precise diff.",
            "Manual review recommended: routing logic, integration constraints, and "
            "transfer timeouts may not be captured.",
        ],
        "_metadata": {
            "_source": "onboarding",
            "_extraction_timestamp": datetime.now(timezone.utc).isoformat(),
            "_confidence_flags": {
                "is_rule_based": True,
                "may_miss_config_details": True,
            },
        },
    }


def extract_onboarding_updates(transcript: str, v1_memo: dict) -> dict:
    account_id = v1_memo.get("account_id", "unknown")
    if GEMINI_API_KEY:
        try:
            logger.info("Extracting onboarding updates via LLM for %s", account_id)
            return _llm_extract_updates(transcript, v1_memo)
        except Exception as exc:
            logger.warning("LLM update extraction failed (%s); falling back to rule-based.", exc)

    logger.warning(
        "No GEMINI_API_KEY set - using rule-based onboarding diff for %s.", account_id
    )
    return _rule_based_onboarding_diff(transcript, v1_memo)
