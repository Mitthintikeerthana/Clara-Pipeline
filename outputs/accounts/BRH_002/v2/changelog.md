# Changelog - BRH_002

**v1 -> v2** | Generated: 2026-03-04T06:43:56.144462+00:00

## Summary
3 field(s) modified; 3 field(s) added

## Version Sources

- **v1 Source:** unknown
- **v2 Source:** onboarding

## Changes (6 total)

### Modified

**`business_hours.days`**
- Before: `Monday, Tuesday, Wednesday, Thursday, Friday`
- After:  `Saturday`
- Reason: Detected via rule-based onboarding scan
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
- After:  `0312 as the new primary emergency contact`
- Reason: Detected via rule-based onboarding scan
- Source: onboarding
