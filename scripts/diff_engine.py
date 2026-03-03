from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    items: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                items.update(_flatten(v, path))
            else:
                items[path] = v
    elif isinstance(obj, list):
        items[prefix] = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    else:
        items[prefix] = obj
    return items

def compute_diff(v1: dict, v2: dict) -> list[dict]:
    flat1 = _flatten(v1)
    flat2 = _flatten(v2)

    all_keys = set(flat1) | set(flat2)
    changes: list[dict] = []

    for key in sorted(all_keys):
        if key in ("generated_at", "version", "_metadata._extraction_timestamp"):
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

def generate_changelog(
    account_id: str,
    diff: list[dict],
    patch_result: dict | None = None,
    v1_metadata: dict | None = None,
    v2_metadata: dict | None = None,
) -> dict:
    reason_map: dict[str, str] = {}
    change_type_map: dict[str, str] = {}
    conflicts: list[dict] = []
    
    if patch_result:
        for p in patch_result.get("patches", []):
            reason_map[p.get("field_path", "")] = p.get("reason", "")
            if "change_type" in p:
                change_type_map[p.get("field_path", "")] = p.get("change_type", "")
        conflicts = patch_result.get("conflicts", [])

    enriched_changes = []
    for entry in diff:
        enriched = dict(entry)
        reason = reason_map.get(entry["field_path"], "")
        
        # Try parent paths for reason
        if not reason:
            parts = entry["field_path"].split(".")
            for i in range(len(parts) - 1, 0, -1):
                reason = reason_map.get(".".join(parts[:i]), "")
                if reason:
                    break
        
        # Add change type from patch if available
        if entry["field_path"] in change_type_map:
            enriched["change_type"] = change_type_map[entry["field_path"]]
        
        # Determine source tracking
        enriched["source"] = "onboarding"
        if v1_metadata and v1_metadata.get("_source") == "demo":
            enriched["previous_source"] = "demo"
        
        enriched["reason"] = reason or "Updated during onboarding."
        enriched_changes.append(enriched)

    # Add conflict entries
    for conflict in conflicts:
        enriched_changes.append({
            "field_path": conflict.get("field", ""),
            "old_value": conflict.get("v1_value"),
            "new_value": conflict.get("form_value") or conflict.get("onboarding_value"),
            "change_type": "conflict_resolved",
            "reason": f"Conflict resolved: {conflict.get('resolution', 'onboarding overrides demo')}",
            "source": "onboarding",
            "previous_source": "demo"
        })

    modified = [c for c in diff if c["change_type"] == "modified"]
    added = [c for c in diff if c["change_type"] == "added"]
    removed = [c for c in diff if c["change_type"] == "removed"]
    confirmed = [c for c in enriched_changes if c.get("change_type") == "confirmed"]

    parts = []
    if modified:
        parts.append(f"{len(modified)} field(s) modified")
    if added:
        parts.append(f"{len(added)} field(s) added")
    if removed:
        parts.append(f"{len(removed)} field(s) removed")
    if confirmed:
        parts.append(f"{len(confirmed)} field(s) confirmed")
    if conflicts:
        parts.append(f"{len(conflicts)} conflict(s) resolved")
    
    summary = "; ".join(parts) if parts else "No changes detected."

    return {
        "account_id": account_id,
        "from_version": "v1",
        "to_version": "v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "total_changes": len(diff) + len(conflicts),
        "changes": enriched_changes,
        "conflicts_resolved": conflicts,
        "metadata": {
            "v1_source": v1_metadata.get("_source", "unknown") if v1_metadata else "unknown",
            "v2_source": v2_metadata.get("_source", "unknown") if v2_metadata else "onboarding",
        }
    }

def format_markdown_changelog(changelog: dict) -> str:
    lines: list[str] = [
        f"# Changelog - {changelog.get('account_id', 'unknown')}",
        "",
        f"**v1 -> v2** | Generated: {changelog.get('generated_at', '')}",
        "",
        f"## Summary",
        f"{changelog.get('summary', '')}",
        "",
    ]

    # Add metadata section if available
    metadata = changelog.get('metadata', {})
    if metadata:
        lines.append("## Version Sources")
        lines.append("")
        lines.append(f"- **v1 Source:** {metadata.get('v1_source', 'unknown')}")
        lines.append(f"- **v2 Source:** {metadata.get('v2_source', 'onboarding')}")
        lines.append("")

    # Add conflicts section if any
    conflicts = changelog.get('conflicts_resolved', [])
    if conflicts:
        lines.append("## Conflicts Resolved")
        lines.append("")
        for c in conflicts:
            lines.append(f"**`{c.get('field', '')}`**")
            lines.append(f"- Demo value: `{_pretty(c.get('v1_value'))}`")
            lines.append(f"- Onboarding value: `{_pretty(c.get('form_value') or c.get('onboarding_value'))}`")
            lines.append(f"- Resolution: {c.get('resolution', 'onboarding overrides demo')}")
            lines.append("")

    lines.append(f"## Changes ({changelog.get('total_changes', 0)} total)")
    lines.append("")

    by_type: dict[str, list] = {"modified": [], "added": [], "removed": [], "confirmed": [], "conflict_resolved": []}
    for c in changelog.get("changes", []):
        by_type.setdefault(c.get("change_type", "modified"), []).append(c)

    for change_type, label in [
        ("confirmed", "Confirmed (No Change)"),
        ("modified", "Modified"),
        ("added", "Added"),
        ("removed", "Removed"),
        ("conflict_resolved", "Conflict Resolved"),
    ]:
        entries = by_type.get(change_type, [])
        if not entries:
            continue
        lines.append(f"### {label}")
        lines.append("")
        for c in entries:
            lines.append(f"**`{c['field_path']}`**")
            if change_type not in ("added", "confirmed"):
                old_val = c.get("old_value")
                lines.append(f"- Before: `{_pretty(old_val)}`")
            if change_type not in ("removed", "confirmed"):
                new_val = c.get("new_value")
                lines.append(f"- After:  `{_pretty(new_val)}`")
            reason = c.get("reason", "")
            if reason:
                lines.append(f"- Reason: {reason}")
            source = c.get("source", "")
            if source:
                lines.append(f"- Source: {source}")
            lines.append("")

    return "\n".join(lines)

def _pretty(val: Any) -> str:
    if val is None:
        return "(removed)"
    if isinstance(val, str) and val.startswith("["):
        try:
            parsed = json.loads(val)
            return ", ".join(str(v) for v in parsed) if parsed else "(empty)"
        except Exception:
            pass
    return str(val)
