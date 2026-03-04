from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

def _fmt_days(days: list[str]) -> str:
    if not days:
        return "Monday-Friday"
    if len(days) == 1:
        return days[0]
    return ", ".join(days[:-1]) + " and " + days[-1]

def _fmt_hours(memo: dict) -> str:
    bh = memo.get("business_hours", {})
    days = _fmt_days(bh.get("days", []))
    start = bh.get("start", "8:00")
    end = bh.get("end", "17:00")
    tz = bh.get("timezone", "")
    tz_label = tz.split("/")[-1].replace("_", " ") if "/" in tz else tz
    return f"{days}, {start}-{end} {tz_label}".strip()

def _fmt_emergency_contacts(contacts: list[dict]) -> str:
    if not contacts:
        return "  (no emergency contacts on file)"
    lines = []
    for c in sorted(contacts, key=lambda x: x.get("order", 99)):
        lines.append(f"  {c.get('order', '?')}. {c.get('name', 'Unknown')} - {c.get('phone', 'no phone')}")
    return "\n".join(lines)

def _fmt_services(services: list[str]) -> str:
    return "\n".join(f"  - {s}" for s in services) if services else "  (see office for details)"

def _fmt_emergency_triggers(triggers: list[str]) -> str:
    return "\n".join(f"  - {t}" for t in triggers) if triggers else "  (consult with dispatch)"

def _fmt_constraints(constraints: list[str]) -> str:
    return "\n".join(f"  - {c}" for c in constraints) if constraints else ""

def _fmt_special_constraints(constraints: list[str]) -> str:
    return "\n".join(f"  - {c}" for c in constraints) if constraints else "  (none on file)"

_SYSTEM_PROMPT_TEMPLATE = """\
# IDENTITY
You are Clara, a professional AI phone answering agent for {company_name}.
You are friendly, concise, and efficient. You never reveal that you are AI unless
directly asked; if asked, you confirm you are an AI assistant.
You never mention "function calls", "tools", "APIs", or any technical processes.

# BUSINESS INFORMATION
Company: {company_name}
Address: {address}
Business Hours: {hours_formatted}

# SERVICES WE OFFER
{services_formatted}

# SERVICES WE DO NOT OFFER / EXCLUSIONS
{exclusions_formatted}

# OPERATIONAL CONSTRAINTS
{constraints_formatted}

# SPECIAL ROUTING RULES
{special_constraints_formatted}

---
# DURING BUSINESS HOURS FLOW

When the office is open:

1. GREET
   "Thank you for calling {company_name}, this is Clara speaking. How can I help you today?"

2. ASK PURPOSE
   - Listen carefully to understand what the caller needs.
   - Identify if this is: service request, appointment, question, emergency, or other.
   - If they ask about something we don't offer, politely inform them and offer to take a message.

3. COLLECT CALLER INFO
   - "May I have your full name, please?"
   - "And the best phone number to reach you?"
   - For service requests also ask: "What's the service address?" and a brief description of the issue.

4. TRANSFER OR ROUTE
   - "Let me connect you with our team. Please hold for just a moment."
   - Attempt transfer to: {during_hours_primary}
   - If no answer after {transfer_timeout_desc}: proceed to step 5.

5. FALLBACK IF TRANSFER FAILS
   - "I wasn't able to connect you right now, but I've captured all your details."
   - "Someone from our team will call you back within the hour. Is that okay?"
   - Confirm their callback number.{dispatch_note}

6. ASK IF THEY NEED ANYTHING ELSE
   - "Is there anything else I can help you with today?"

7. CLOSE CALL
   - "Thank you for calling {company_name}. Have a great day!"
   - Wait for caller to hang up first.

---
# AFTER HOURS FLOW

When the office is closed:

1. GREET
   "Thank you for calling {company_name}. Our office is currently closed - our normal hours
   are {hours_formatted}. This is Clara, the after-hours answering service."

2. ASK PURPOSE
   - "May I ask what's going on tonight? How can I help you?"
   - Listen carefully to what the caller describes.
   - Do NOT immediately ask if it's an emergency - let them explain first.

3. CONFIRM EMERGENCY
   - Based on their description, assess urgency.
   - "Just to make sure I get you the right help - is this something that needs
     immediate attention tonight, or can it wait until business hours?"
   - If they describe a known emergency trigger (see EMERGENCY TRIGGERS below),
     treat as emergency immediately without requiring further confirmation.

4A. IF EMERGENCY - Collect info FIRST, then transfer:

   a) COLLECT NAME, NUMBER, AND ADDRESS IMMEDIATELY:
      - "Can I get your full name?"
      - "What's the best callback number?"
      - "What's the service address where we need to send someone?"
      - Briefly confirm the emergency nature.

   b) ATTEMPT TRANSFER:
      - "I'm going to connect you with our on-call team right away."
      - Attempt emergency transfer in order:
{emergency_contacts_formatted}

   c) IF TRANSFER SUCCEEDS:
      - Stay on hold, confirm handoff to on-call technician.

   d) IF ALL TRANSFERS FAIL:
      - "{transfer_fail_message}"
      - "I have sent an urgent alert to our on-call team with your information.
         Someone will call you back within 15 minutes.
         If this is a life-threatening emergency, please call 9-1-1 immediately."

4B. IF NON-EMERGENCY:

   a) COLLECT DETAILS:
      - Full name
      - Best callback number
      - Service address (if applicable)
      - Brief description of the issue

   b) CONFIRM FOLLOW-UP DURING BUSINESS HOURS:
      - "Our office opens {next_open_hint}. I've got all your details and
         someone will call you back first thing when we open."

5. ASK IF THEY NEED ANYTHING ELSE
   - "Is there anything else I can help you with tonight?"

6. CLOSE CALL
   - "Thank you for calling {company_name}. Stay safe and have a good night."
   - Wait for caller to hang up first.

---
# EMERGENCY TRIGGERS
The following situations ALWAYS qualify as emergencies requiring immediate escalation:
{emergency_triggers_formatted}

# AFTER HOURS NON-EMERGENCY RULE
{non_emergency_after_hours}

# IMPORTANT REMINDERS
- Never promise a specific arrival time unless explicitly authorized.
- Never quote prices.
- Never create job records yourself - only collect information.
- Do not mention the names of specific technicians unless they are emergency contacts.
- Always be empathetic with distressed callers.
- If a caller is abusive, calmly state you are here to help and may need to end the call.
- For life-threatening emergencies, always direct caller to call 9-1-1 immediately.
"""

def generate_system_prompt(memo: dict, version: str = "v1") -> str:
    er = memo.get("emergency_routing_rules", {})
    ct = memo.get("call_transfer_rules", {})
    ne = memo.get("non_emergency_routing_rules", {})
    constraints = memo.get("integration_constraints", [])
    exclusions = memo.get("services_excluded", [])

    constraints_text = _fmt_constraints(constraints)
    if not constraints_text:
        constraints_text = "  (no specific constraints on file - use good judgment)"

    exclusions_text = _fmt_services(exclusions) if exclusions else "  (none specified)"

    company = memo.get("company_name", "our company")
    fallback = er.get("fallback", "") or "I was unable to reach our on-call team."

    timeout_seconds = ct.get("timeout_seconds")
    timeout_rings = ct.get("timeout_rings", 4)
    transfer_timeout_desc = f"{timeout_seconds} seconds" if timeout_seconds else f"{timeout_rings} rings"

    dispatch_note = (
        "\n   - An automatic dispatch alert will be sent if all transfers fail."
        if ct.get("notify_dispatch_on_fail")
        else ""
    )

    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        company_name=company,
        address=memo.get("office_address", "(address on file)"),
        hours_formatted=_fmt_hours(memo),
        services_formatted=_fmt_services(memo.get("services_supported", [])),
        exclusions_formatted=exclusions_text,
        constraints_formatted=constraints_text,
        special_constraints_formatted=_fmt_special_constraints(memo.get("special_constraints", [])),
        during_hours_primary=ct.get("during_hours_primary", "(office main line)"),
        transfer_timeout_desc=transfer_timeout_desc,
        emergency_contacts_formatted=_fmt_emergency_contacts(er.get("contacts", [])),
        transfer_fail_message=fallback,
        dispatch_note=dispatch_note,
        emergency_triggers_formatted=_fmt_emergency_triggers(memo.get("emergency_definition", [])),
        non_emergency_after_hours=ne.get(
            "after_hours",
            "Take message with name, number, and issue. Promise next-day callback.",
        ),
        next_open_hint="our next business day",
    )

    if version == "v2":
        prompt = f"# VERSION: v2 (updated after onboarding)\n\n{prompt}"

    return prompt.strip()

_DEFAULT_VOICE = "openai-Alloy"

_RECOMMENDED_VOICES = {
    "professional_female": "openai-Nova",
    "professional_male": "openai-Onyx",
    "friendly_female": "openai-Alloy",
    "friendly_male": "openai-Echo",
}

def generate_agent_spec(memo: dict, version: str = "v1") -> dict:
    system_prompt = generate_system_prompt(memo, version=version)
    bh = memo.get("business_hours", {})
    er = memo.get("emergency_routing_rules", {})
    ct = memo.get("call_transfer_rules", {})
    company = memo.get("company_name", "Unknown Company")

    agent_name = f"{company} - Clara ({version.upper()})"

    spec: dict[str, Any] = {
        "agent_name": agent_name,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),

        "response_engine": {
            "type": "retell-llm",
            "model": "gpt-4o-mini",
            "system_prompt": system_prompt,
            "temperature": 0.3,
        },

        "voice_id": _DEFAULT_VOICE,
        "voice_speed": 1.0,
        "voice_temperature": 0.7,
        "language": "en-US",

        "begin_message": f"Thank you for calling {company}, this is Clara speaking. How can I help you today?",
        "max_call_duration_sec": 600,
        "boosted_keywords": [
            company.split()[0],
            "emergency",
            "urgent",
            "transfer",
        ],

        "key_variables": {
            "company_name": company,
            "timezone": bh.get("timezone", ""),
            "business_hours_start": bh.get("start", ""),
            "business_hours_end": bh.get("end", ""),
            "business_days": ", ".join(bh.get("days", [])),
            "office_address": memo.get("office_address", ""),
            "emergency_primary_phone": (
                er["contacts"][0]["phone"] if er.get("contacts") else ""
            ),
            "emergency_secondary_phone": (
                er["contacts"][1]["phone"] if len(er.get("contacts", [])) > 1 else ""
            ),
            "daytime_transfer_number": ct.get("during_hours_primary", ""),
            "special_constraints": memo.get("special_constraints", []),
        },

        "tool_invocation_placeholders": [
            {
                "tool_name": "transfer_call",
                "description": "Transfer the active call to the specified phone number.",
                "parameters": {
                    "destination_phone": "string",
                    "caller_name": "string",
                    "caller_phone": "string",
                    "issue_summary": "string",
                },
            },
            {
                "tool_name": "create_voicemail_note",
                "description": "Log caller info for callback when transfer fails.",
                "parameters": {
                    "caller_name": "string",
                    "caller_phone": "string",
                    "service_address": "string",
                    "issue_description": "string",
                    "priority": "normal|urgent",
                },
            },
        ],

        "call_transfer_protocol": {
            "during_hours": {
                "primary_number": ct.get("during_hours_primary", ""),
                "timeout_rings": ct.get("timeout_rings", 4),
                "timeout_seconds": ct.get("timeout_seconds"),
                "retries": ct.get("retries", 1),
                "notify_dispatch_on_fail": ct.get("notify_dispatch_on_fail", False),
                "on_fail": ct.get(
                    "on_transfer_fail",
                    "Take message and promise callback within one hour.",
                ),
            },
            "emergency_after_hours": {
                "contacts": er.get("contacts", []),
                "attempt_each_contact": True,
                "on_all_fail": er.get(
                    "fallback",
                    "Advise caller that on-call team has been alerted. ETA 15 minutes. 911 for life-threatening.",
                ),
            },
        },

        "fallback_protocol": {
            "max_transfer_attempts": len(er.get("contacts", [])) or 2,
            "message_if_all_fail": (
                "I was unable to connect you right now. Your information has been "
                "logged and our team will call you back as soon as possible."
            ),
            "send_sms_alert": False,
        },
    }

    return spec

def build_all_outputs(memo: dict, version: str = "v1") -> dict:
    prompt = generate_system_prompt(memo, version=version)
    spec = generate_agent_spec(memo, version=version)
    return {"system_prompt": prompt, "agent_spec": spec}
