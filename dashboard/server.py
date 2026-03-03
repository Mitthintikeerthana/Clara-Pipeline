from __future__ import annotations

import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "accounts"
LOGS_DIR = PROJECT_ROOT / "logs"
DASHBOARD_DIR = Path(__file__).parent

def _load_json(path: Path) -> dict | list | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _accounts_api() -> list[dict]:
    if not OUTPUTS_DIR.exists():
        return []
    accounts = []
    for account_dir in sorted(OUTPUTS_DIR.iterdir()):
        if not account_dir.is_dir():
            continue
        account_id = account_dir.name
        versions = sorted(p.name for p in account_dir.iterdir() if p.is_dir())
        v1_memo = _load_json(account_dir / "v1" / "memo.json") or {}
        v2_memo = _load_json(account_dir / "v2" / "memo.json")
        accounts.append({
            "account_id": account_id,
            "company_name": v1_memo.get("company_name", account_id),
            "versions": versions,
            "has_v2": "v2" in versions,
        })
    return accounts

def _account_api(account_id: str) -> dict:
    base = OUTPUTS_DIR / account_id
    if not base.exists():
        return {"error": f"Account '{account_id}' not found"}

    v1_memo = _load_json(base / "v1" / "memo.json")
    v1_spec = _load_json(base / "v1" / "agent_spec.json")
    v1_prompt_path = base / "v1" / "agent_prompt.txt"
    v1_prompt = v1_prompt_path.read_text(encoding="utf-8") if v1_prompt_path.exists() else None

    v2_memo = _load_json(base / "v2" / "memo.json")
    v2_spec = _load_json(base / "v2" / "agent_spec.json")
    v2_prompt_path = base / "v2" / "agent_prompt.txt"
    v2_prompt = v2_prompt_path.read_text(encoding="utf-8") if v2_prompt_path.exists() else None
    v2_changelog = _load_json(base / "v2" / "changelog.json")
    v2_changelog_md_path = base / "v2" / "changelog.md"
    v2_changelog_md = v2_changelog_md_path.read_text(encoding="utf-8") if v2_changelog_md_path.exists() else None

    return {
        "account_id": account_id,
        "v1": {
            "memo": v1_memo,
            "agent_spec": v1_spec,
            "system_prompt": v1_prompt,
        },
        "v2": {
            "memo": v2_memo,
            "agent_spec": v2_spec,
            "system_prompt": v2_prompt,
            "changelog": v2_changelog,
            "changelog_md": v2_changelog_md,
        } if v2_memo else None,
    }

def _summary_api() -> dict:
    summary = _load_json(LOGS_DIR / "batch_summary.json")
    if summary is None:
        return {"error": "No batch_summary.json found. Run batch_runner first."}
    return summary

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path: Path) -> None:
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/" or path == "/index.html":
            html_file = DASHBOARD_DIR / "index.html"
            if html_file.exists():
                self._send_html(html_file)
            else:
                self._send_json({"error": "dashboard/index.html not found"}, 404)

        elif path == "/api/accounts":
            self._send_json(_accounts_api())

        elif path.startswith("/api/account/"):
            account_id = path.split("/api/account/", 1)[1]
            self._send_json(_account_api(account_id))

        elif path == "/api/summary":
            self._send_json(_summary_api())

        else:
            self._send_json({"error": "Not found"}, 404)

def main(port: int = 8080) -> None:
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"  Clara Pipeline Dashboard")
    print(f"  Running at: http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    main(args.port)
