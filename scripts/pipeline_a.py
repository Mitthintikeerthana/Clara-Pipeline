from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from scripts.config import (
    AUDIO_EXTENSIONS,
    LOGS_DIR,
    OUTPUTS_DIR,
    TEXT_EXTENSIONS,
)
from scripts.extractor import extract_memo
from scripts.prompt_generator import build_all_outputs
from scripts.task_tracker import create_issue
from scripts.utils.storage import save_json, save_text

def _setup_logging(account_id: str) -> None:
    log_file = LOGS_DIR / f"{account_id}_pipeline_a.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

logger = logging.getLogger(__name__)

def _ingest(input_path: Path) -> str:
    suffix = input_path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        text = input_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Input file is empty: {input_path}")
        logger.info("Loaded transcript (%d chars) from %s", len(text), input_path.name)
        return text

    if suffix in AUDIO_EXTENSIONS:
        logger.info("Audio file detected - running Whisper transcription…")
        from scripts.transcriber import transcribe
        return transcribe(input_path)

    raise ValueError(
        f"Unsupported file type '{suffix}'. "
        f"Accepted: {TEXT_EXTENSIONS | AUDIO_EXTENSIONS}"
    )

def run_pipeline_a(input_path: str | Path, account_id: str) -> dict:
    input_path = Path(input_path)
    _setup_logging(account_id)
    logger.info("=== Pipeline A starting: %s -> %s ===", input_path.name, account_id)

    transcript = _ingest(input_path)

    save_text(transcript, account_id, "transcript.txt", version="v1")

    logger.info("Extracting account memo…")
    memo = extract_memo(transcript, account_id)

    logger.info("Generating Retell agent spec v1…")
    outputs = build_all_outputs(memo, version="v1")
    agent_spec = outputs["agent_spec"]
    system_prompt = outputs["system_prompt"]

    save_json(memo, account_id, "memo.json", version="v1")
    save_json(agent_spec, account_id, "agent_spec.json", version="v1")
    save_text(system_prompt, account_id, "agent_prompt.txt", version="v1")

    output_dir = str(OUTPUTS_DIR / account_id / "v1")
    logger.info("Outputs saved to: %s", output_dir)

    issue_url = create_issue(account_id, memo, agent_spec)

    metadata = {
        "account_id": account_id,
        "pipeline": "A",
        "version": "v1",
        "input_file": str(input_path),
        "issue_url": issue_url,
    }
    save_json(metadata, account_id, "pipeline_meta.json", version="v1")

    logger.info("=== Pipeline A complete: %s ===", account_id)

    return {
        "account_id": account_id,
        "memo": memo,
        "agent_spec": agent_spec,
        "system_prompt": system_prompt,
        "output_dir": output_dir,
        "issue_url": issue_url,
    }

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline A: demo call transcript -> Retell agent v1"
    )
    parser.add_argument(
        "--input", required=True, help="Path to transcript (.txt/.md) or audio file"
    )
    parser.add_argument(
        "--account_id", required=True, help="Unique account identifier, e.g. ACE_PLB_001"
    )
    args = parser.parse_args()

    result = run_pipeline_a(args.input, args.account_id)

    print("\n[ok] Pipeline A complete")
    print(f"  Account ID : {result['account_id']}")
    print(f"  Company    : {result['memo'].get('company_name', '-')}")
    print(f"  Outputs    : {result['output_dir']}")
    if result["issue_url"]:
        print(f"  Issue URL  : {result['issue_url']}")
    else:
        print("  Issue URL  : (GitHub not configured)")

if __name__ == "__main__":
    _main()
