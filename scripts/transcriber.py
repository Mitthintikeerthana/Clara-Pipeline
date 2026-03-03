from __future__ import annotations

import logging
from pathlib import Path

from scripts.config import WHISPER_MODEL

logger = logging.getLogger(__name__)

_whisper_model = None

def _load_model():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        import whisper
        logger.info("Loading Whisper model '%s' (first run may download weights)…", WHISPER_MODEL)
        _whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper model loaded.")
        return _whisper_model
    except ImportError:
        raise RuntimeError(
            "openai-whisper is not installed.\n"
            "Run:  pip install openai-whisper\n"
            "Or provide .txt transcript files instead of audio."
        )

def transcribe(audio_path: str | Path) -> str:
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _load_model()
    logger.info("Transcribing %s …", audio_path.name)

    result = model.transcribe(str(audio_path), fp16=False, language="en")
    text: str = result.get("text", "").strip()

    if not text:
        raise ValueError(f"Whisper returned an empty transcript for {audio_path.name}")

    logger.info("Transcribed %d characters from %s", len(text), audio_path.name)
    return text

def is_whisper_available() -> bool:
    try:
        import whisper
        return True
    except ImportError:
        return False
