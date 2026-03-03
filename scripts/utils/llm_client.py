import json
import logging
import re
import time

from scripts.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

_client = None
_available = False

def _init():
    global _client, _available
    if _client is not None:
        return
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set - falling back to rule-based extraction.")
        return
    try:
        import os
        from google import genai
        os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
        _client = genai.Client(api_key=GEMINI_API_KEY)
        _available = True
        logger.info("Gemini client initialised (model: %s)", GEMINI_MODEL)
    except ImportError:
        try:
            import google.generativeai as genai_old
            genai_old.configure(api_key=GEMINI_API_KEY)

            class _OldClientWrapper:
                def __init__(self, model_name: str):
                    import google.generativeai as g
                    self._model = g.GenerativeModel(model_name)
                    self.models = self

                def generate_content(self, model: str, contents: str):
                    return self._model.generate_content(contents)

            _client = _OldClientWrapper(GEMINI_MODEL)
            _available = True
            logger.warning(
                "Using deprecated google-generativeai SDK. "
                "Upgrade: pip install google-genai"
            )
        except ImportError:
            logger.warning(
                "No Gemini SDK found. Install: pip install google-genai"
            )

def call_llm(prompt: str, retries: int = 3, delay: float = 4.0) -> str:
    _init()
    if not _available:
        raise RuntimeError(
            "Gemini is unavailable. Set GEMINI_API_KEY and install google-genai.\n"
            "  pip install google-genai"
        )

    for attempt in range(1, retries + 1):
        try:
            from google import genai as _genai
            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return response.text
        except Exception as exc:
            logger.warning("LLM attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay * attempt)
    raise RuntimeError("All LLM attempts exhausted.")

def call_llm_json(prompt: str, retries: int = 3) -> dict:
    raw = call_llm(prompt, retries=retries)
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error.\nRaw output:\n%s", raw[:2000])
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
