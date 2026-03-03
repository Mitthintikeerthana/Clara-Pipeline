"""
Diff engine: produce a structured changelog between v1 and v2 account memos.

Exported functions
------------------
compute_diff(v1, v2)                -> list of ChangeEntry dicts
generate_changelog(account_id, diff, reason_map) -> changelog dict
format_markdown_changelog(changelog) -> str
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# -- Deep diff -----------------------------------------------------------------

def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """
    Recursively flatten a nested dict/list to dot-separated paths.
    Lists are stored as their JSON serialisation so they compare correctly.
    """
    items: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                items.update(_flatten(v, path))
            else:
                items[path] = v
    elif isinstance(obj, list):
        # Treat lists atomically so that order/membership changes are captured
        items[prefix] = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    else:
        items[prefix] = obj
    return items


def compute_diff(v1: dict, v2: dict) -> list[dict]:
    """
    Return a list of ChangeEntry dicts describing every field that changed
    between v1 and v2.

    ChangeEntry schema:
        field_path : str
        old_value  : any
        new_value  : any
        change_type: "added" | "removed" | "modified"
    """
    flat1 = _flatten(v1)
    flat2 = _flatten(v2)

    all_keys = set(flat1) | set(flat2)
    changes: list[dict] = []

    for key in sorted(all_keys):
        # Skip metadata fields that always differ
        if key in ("generated_at", "version"):
            continue

        in_v1 = key in flat1
        in_v2 = key in flat2
        val1 = flat1.get(key)
        val2 = flat2.get(key)

        if in_v1 and not in_v2:
            changes.append(
                {"field_path": key, "old_value": val1, "new_value": None, "change_type": "removed"}
            )
        elif not in_v1 and in_v2:
            changes.append(
                {"field_path": key, "old_value": None, "new_value": val2, "change_type": "added"}
            )
        elif val1 != val2:
            changes.append(
                {"field_path": key, "old_value": val1, "new_value": val2, "change_type": "modified"}
            )

    return changes


# -- Changelog builder ----------------------------------------------------------

def generate_changelog(
    account_id: str,
    diff: list[dict],
    patch_result: dict | None = None,
) -> dict:
    """
    Build a structured changelog dict.

    patch_result (optional) - the raw patch output from extract_onboarding_updates(),
    used to attach the human-readable "reason" to each change.
    """
    # Build a lookup from field_path -> reason using the patch result
    reason_map: dict[str, str] = {}
    if patch_result:
        for p in patch_result.get("patches", []):
            reason_map[p.get("field_path", "")] = p.get("reason", "")

    enriched_changes = []
    for entry in diff:
        enriched = dict(entry)
        # Try to find a reason from patch_result
        reason = reason_map.get(entry["field_path"], "")
        # Also try parent paths (e.g. "business_hours.days" -> "business_hours")
        if not reason:
            parts = entry["field_path"].split(".")
            for i in range(len(parts) - 1, 0, -1):
                reason = reason_map.get(".".join(parts[:i]), "")
                if reason:
                    break
        enriched["reason"] = reason or "Updated during onboarding."
        enriched_changes.append(enriched)

    # Compute a human-readable summary
    modified = [c for c in diff if c["change_type"] == "modified"]
    added = [c for c in diff if c["change_type"] == "added"]
    removed = [c for c in diff if c["change_type"] == "removed"]

    parts = []
    if modified:
        parts.append(f"{len(modified)} field(s) modified")
    if added:
        parts.append(f"{len(added)} field(s) added")
    if removed:
        parts.append(f"{len(removed)} field(s) removed")
    summary = "; ".join(parts) if parts else "No changes detected."

    return {
        "account_id": account_id,
        "from_version": "v1",
        "to_version": "v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "total_changes": len(diff),
        "changes": enriched_changes,
    }


# -- Markdown renderer ----------------------------------------------------------

def format_markdown_changelog(changelog: dict) -> str:
    """
    Render a changelog dict as a human-readable Markdown string.
    """
    lines: list[str] = [
        f"# Changelog - {changelog.get('account_id', 'unknown')}",
        "",
        f"**v1 -> v2** | Generated: {changelog.get('generated_at', '')}",
        "",
        f"## Summary",
        f"{changelog.get('summary', '')}",
        "",
        f"## Changes ({changelog.get('total_changes', 0)} total)",
        "",
    ]

    by_type: dict[str, list] = {"modified": [], "added": [], "removed": []}
    for c in changelog.get("changes", []):
        by_type.setdefault(c.get("change_type", "modified"), []).append(c)

    for change_type, label in [
        ("modified", "Modified"),
        ("added", "Added"),
        ("removed", "Removed"),
    ]:
        entries = by_type.get(change_type, [])
        if not entries:
            continue
        lines.append(f"### {label}")
        lines.append("")
        for c in entries:
            lines.append(f"**`{c['field_path']}`**")
            if change_type != "added":
                old_val = c.get("old_value")
                lines.append(f"- Before: `{_pretty(old_val)}`")
            if change_type != "removed":
                new_val = c.get("new_value")
                lines.append(f"- After:  `{_pretty(new_val)}`")
            reason = c.get("reason", "")
            if reason:
                lines.append(f"- Reason: {reason}")
            lines.append("")

    return "\n".join(lines)


def _pretty(val: Any) -> str:
    if val is None:
        return "(removed)"
    if isinstance(val, str) and val.startswith("["):
        # Was stored as JSON list string by _flatten
        try:
            parsed = json.loads(val)
            return ", ".join(str(v) for v in parsed) if parsed else "(empty)"
        except Exception:
            pass
    return str(val)
