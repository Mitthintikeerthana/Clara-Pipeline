"""
Task Tracker integration - GitHub Issues (free, no credit card required).

Creates one GitHub Issue per account when Pipeline A runs.
Updates the issue (adds a comment) when Pipeline B produces v2.

Falls back gracefully if GITHUB_TOKEN or GITHUB_REPO are not set.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

from scripts.config import GITHUB_TOKEN, GITHUB_REPO

logger = logging.getLogger(__name__)


# -- Internal HTTP helper (stdlib only, no requests dependency) -----------------

def _gh_request(method: str, path: str, body: dict | None = None) -> dict | None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return None

    url = f"https://api.github.com/repos/{GITHUB_REPO}{path}"
    data = json.dumps(body).encode() if body else None

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "clara-pipeline/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()[:400]
        logger.error("GitHub API %s %s -> %s: %s", method, path, exc.code, body_text)
        return None
    except Exception as exc:
        logger.error("GitHub request failed: %s", exc)
        return None


# -- Issue management -----------------------------------------------------------

def _build_issue_body(account_id: str, memo: dict, agent_spec: dict) -> str:
    bh = memo.get("business_hours", {})
    er = memo.get("emergency_routing_rules", {})
    contacts_md = "\n".join(
        f"  {c.get('order')}. {c.get('name')} - {c.get('phone')}"
        for c in er.get("contacts", [])
    )

    body = f"""## Clara Pipeline - New Account: `{account_id}`

**Company:** {memo.get("company_name", "-")}
**Address:** {memo.get("office_address", "-")}
**Business Hours:** {", ".join(bh.get("days", []))} {bh.get("start", "")}-{bh.get("end", "")} {bh.get("timezone", "")}

### Services Supported
{chr(10).join("- " + s for s in memo.get("services_supported", []))}

### Emergency Contacts
{contacts_md or "None on file"}

### Agent Spec Version
`{agent_spec.get("version", "v1")}` - generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

### Open Questions
{chr(10).join("- " + q for q in memo.get("questions_or_unknowns", [])) or "None"}

---
_Auto-created by Clara Pipeline. Review outputs at `outputs/accounts/{account_id}/v1/`_
"""
    return body


def _build_update_comment(account_id: str, changelog: dict) -> str:
    summary = changelog.get("summary", "See diff for details.")
    total = changelog.get("total_changes", 0)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"## Onboarding Update - `{account_id}` - v1 -> v2",
        f"",
        f"**{total} change(s) applied** at {ts}",
        f"",
        f"**Summary:** {summary}",
        f"",
        "### Changed Fields",
    ]
    for c in changelog.get("changes", [])[:20]:    # Cap to avoid huge comments
        old = str(c.get("old_value", ""))[:60]
        new = str(c.get("new_value", ""))[:60]
        lines.append(f"- `{c['field_path']}`: `{old}` -> `{new}`")

    lines += [
        f"",
        f"_v2 outputs stored at `outputs/accounts/{account_id}/v2/`_",
    ]
    return "\n".join(lines)


# -- Public API -----------------------------------------------------------------

def create_issue(account_id: str, memo: dict, agent_spec: dict) -> str | None:
    """
    Create a GitHub Issue for a newly processed account.
    Returns the issue URL on success, None if GitHub is not configured or fails.
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.info(
            "GitHub not configured - skipping issue creation for %s. "
            "Set GITHUB_TOKEN and GITHUB_REPO in .env to enable.",
            account_id,
        )
        return None

    company = memo.get("company_name", account_id)
    payload = {
        "title": f"[Clara Pipeline] New Account: {company} ({account_id})",
        "body": _build_issue_body(account_id, memo, agent_spec),
        "labels": ["clara-pipeline", "new-account"],
    }

    result = _gh_request("POST", "/issues", payload)
    if result and "html_url" in result:
        url = result["html_url"]
        logger.info("GitHub Issue created: %s", url)
        return url

    logger.warning("Failed to create GitHub issue for %s", account_id)
    return None


def update_issue(account_id: str, issue_url: str | None, changelog: dict) -> bool:
    """
    Add a comment to the existing GitHub Issue when v2 is produced.
    Falls back gracefully if the issue URL is unknown.
    """
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.info("GitHub not configured - skipping issue update for %s.", account_id)
        return False

    if not issue_url:
        logger.info("No issue URL for %s - creating a fresh issue comment is skipped.", account_id)
        return False

    # Extract issue number from URL: .../issues/42
    import re
    m = re.search(r"/issues/(\d+)", issue_url)
    if not m:
        logger.warning("Cannot parse issue number from %s", issue_url)
        return False

    issue_number = m.group(1)
    comment_body = _build_update_comment(account_id, changelog)
    result = _gh_request("POST", f"/issues/{issue_number}/comments", {"body": comment_body})

    if result and "html_url" in result:
        logger.info("GitHub Issue comment added: %s", result["html_url"])
        return True

    logger.warning("Failed to add GitHub comment for %s", account_id)
    return False


def close_issue(issue_url: str) -> bool:
    """Mark an issue as closed (optional, for cleanup)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False

    import re
    m = re.search(r"/issues/(\d+)", issue_url)
    if not m:
        return False

    issue_number = m.group(1)
    result = _gh_request("PATCH", f"/issues/{issue_number}", {"state": "closed"})
    return bool(result)
