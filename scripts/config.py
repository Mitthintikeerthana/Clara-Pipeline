import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
INPUTS_DIR   = PROJECT_ROOT / "inputs"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs" / "accounts"
LOGS_DIR     = PROJECT_ROOT / "logs"
CHANGELOG_DIR = PROJECT_ROOT / "changelog"

for _d in (OUTPUTS_DIR, LOGS_DIR, CHANGELOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "")

RETELL_API_KEY   = os.getenv("RETELL_API_KEY", "")
RETELL_BASE_URL  = "https://api.retellai.com"

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
DRY_RUN      = os.getenv("DRY_RUN", "false").lower() == "true"

AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".flac", ".webm"}
TEXT_EXTENSIONS  = {".txt", ".md", ".json"}
