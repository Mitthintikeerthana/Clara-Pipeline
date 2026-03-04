# Changelog - ACE_PLB_001

**v1 -> v2** | Generated: 2026-03-04T06:43:39.626664+00:00

## Summary
4 field(s) modified; 3 field(s) added

## Version Sources

- **v1 Source:** unknown
- **v2 Source:** onboarding

## Changes (7 total)

### Modified

**`business_hours.days`**
- Before: `Monday, Tuesday, Wednesday, Thursday, Friday`
- After:  `Monday`
- Reason: Detected via rule-based onboarding scan
- Source: onboarding

**`emergency_routing_rules.contacts`**
- Before: `{'name': 'Contact 1', 'order': 1, 'phone': '602-555-0142'}, {'name': 'Contact 2', 'order': 2, 'phone': '602-555-0198'}, {'name': 'Contact 3', 'order': 3, 'phone': '602-555-0100'}`
- After:  `{'name': 'Contact 1', 'order': 1, 'phone': '602-555-0142'}, {'name': 'Contact 2', 'order': 2, 'phone': '602-555-0198'}, {'name': 'Contact 3', 'order': 3, 'phone': '602-555-0210'}`
- Reason: Phone numbers detected in onboarding transcript
- Source: onboarding

**`questions_or_unknowns`**
- Before: `Full extraction not available - set GEMINI_API_KEY for LLM-based extraction.`
- After:  `Full extraction not available - set GEMINI_API_KEY for LLM-based extraction., Rule-based onboarding extraction used - set GEMINI_API_KEY for precise diff., Manual review recommended: routing logic, integration constraints, and transfer timeouts may not be captured.`
- Reason: Updated during onboarding.
- Source: onboarding

### Added

**`_metadata._confidence_flags.is_rule_based`**
- After:  `True`
- Reason: Updated during onboarding.
- Source: onboarding

**`_metadata._confidence_flags.may_miss_config_details`**
- After:  `True`
- Reason: Updated during onboarding.
- Source: onboarding

**`_metadata._source`**
- After:  `onboarding`
- Reason: Updated during onboarding.
- Source: onboarding

**`office_address`**
- After:  `0210 as the third emergency contact`
- Reason: Detected via rule-based onboarding scan
- Source: onboarding
