"""
Central configuration. All values come from environment variables.
Copy .env.example to .env and fill in your keys before running.
"""

import os
from pathlib import Path

# Auto-load .env file if present (requires python-dotenv)
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass  # dotenv is optional; keys can also be set via shell export

# -- Paths ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
INPUTS_DIR   = PROJECT_ROOT / "inputs"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs" / "accounts"
LOGS_DIR     = PROJECT_ROOT / "logs"
CHANGELOG_DIR = PROJECT_ROOT / "changelog"

for _d in (OUTPUTS_DIR, LOGS_DIR, CHANGELOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# -- LLM (Google Gemini - free tier via AI Studio) -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# -- Task Tracker (GitHub Issues - free) ---------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "")          # format: owner/repo

# -- Retell (mock layer if no paid access) -------------------------------------
RETELL_API_KEY   = os.getenv("RETELL_API_KEY", "")
RETELL_BASE_URL  = "https://api.retellai.com"

# -- Whisper (local, free) -----------------------------------------------------
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")   # tiny | base | small | medium | large

# -- Pipeline behaviour --------------------------------------------------------
LOG_LEVEL    = os.getenv("LOG_LEVEL", "INFO")
DRY_RUN      = os.getenv("DRY_RUN", "false").lower() == "true"

# Supported audio extensions for auto-transcription
AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".ogg", ".flac", ".webm"}
TEXT_EXTENSIONS  = {".txt", ".md", ".json"}
