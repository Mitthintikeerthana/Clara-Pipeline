import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import OUTPUTS_DIR

logger = logging.getLogger(__name__)

def _account_path(account_id: str, version: str) -> Path:
    path = OUTPUTS_DIR / account_id / version
    path.mkdir(parents=True, exist_ok=True)
    return path

def save_json(data: dict, account_id: str, filename: str, version: str = "v1") -> Path:
    path = _account_path(account_id, version) / filename
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    logger.info("Saved %s -> %s", filename, path)
    return path

def load_json(account_id: str, filename: str, version: str = "v1") -> dict | None:
    path = _account_path(account_id, version) / filename
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def save_text(content: str, account_id: str, filename: str, version: str = "v1") -> Path:
    path = _account_path(account_id, version) / filename
    path.write_text(content, encoding="utf-8")
    logger.info("Saved %s -> %s", filename, path)
    return path

def load_text(account_id: str, filename: str, version: str = "v1") -> str | None:
    path = _account_path(account_id, version) / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")

def list_accounts() -> list[str]:
    if not OUTPUTS_DIR.exists():
        return []
    return sorted(p.name for p in OUTPUTS_DIR.iterdir() if p.is_dir())

def list_versions(account_id: str) -> list[str]:
    base = OUTPUTS_DIR / account_id
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())

def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()
