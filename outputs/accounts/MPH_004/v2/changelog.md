# Changelog - MPH_004

**v1 -> v2** | Generated: 2026-03-04T06:44:27.436393+00:00

## Summary
3 field(s) modified; 3 field(s) added

## Version Sources

- **v1 Source:** unknown
- **v2 Source:** onboarding

## Changes (6 total)

### Modified

**`business_hours.days`**
- Before: `Monday, Tuesday, Wednesday, Thursday, Friday, Saturday`
- After:  `Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday`
- Reason: Detected via rule-based onboarding scan
- Source: onboarding

**`emergency_definition`**
- Before: `Jake: No heat when it's below twenty degrees Fahrenheit outside, ercial clients who have buildings full of people. Carbon monoxide alarm triggered. And complete system failure for, nheit outside. No AC when it's above ninety-five. Boiler failure — especially for commercial clients who have buil, l of people. Carbon monoxide alarm triggered. And complete system failure for any commercial client during operating hours`
- After:  `Riley: Adding to emergency definitions: complete building heating system failure for commercial clients — treat as priority emerge`
- Reason: Emergency triggers detected in onboarding transcript
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
