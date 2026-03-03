"""
Pipeline B - Onboarding Call -> Updated Agent (v2)

Steps:
  1. Load v1 memo from storage (must exist - run Pipeline A first)
  2. Ingest onboarding file and extract updates patch
  3. Apply patch to v1 memo -> v2 memo
  4. Re-generate Retell Agent Spec v2
  5. Compute diff (v1 -> v2) and generate changelog
  6. Store all v2 artefacts + changelog
  7. Update the GitHub Issue with a comment
  8. Return results dict

Usage (CLI)
-----------
  python -m scripts.pipeline_b --input inputs/onboarding/onboarding_001.txt --account_id ACE_PLB_001
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.config import AUDIO_EXTENSIONS, CHANGELOG_DIR, LOGS_DIR, TEXT_EXTENSIONS
from scripts.diff_engine import compute_diff, format_markdown_changelog, generate_changelog
from scripts.extractor import apply_patches, extract_onboarding_updates
from scripts.prompt_generator import build_all_outputs
from scripts.task_tracker import update_issue
from scripts.utils.storage import (
    load_json,
    load_text,
    save_json,
    save_text,
)

# -- Logging --------------------------------------------------------------------

def _setup_logging(account_id: str) -> None:
    log_file = LOGS_DIR / f"{account_id}_pipeline_b.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


logger = logging.getLogger(__name__)


# -- Ingest (shared with Pipeline A) -------------------------------------------

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
    raise ValueError(f"Unsupported file type: {suffix}")


# -- Main pipeline function -----------------------------------------------------

def run_pipeline_b(input_path: str | Path, account_id: str) -> dict:
    """
    Run Pipeline B end-to-end for one account.

    Returns a dict with keys:
        account_id, v1_memo, v2_memo, agent_spec, system_prompt,
        changelog, changelog_md, output_dir
    """
    input_path = Path(input_path)
    _setup_logging(account_id)
    logger.info("=== Pipeline B starting: %s -> %s ===", input_path.name, account_id)

    # -- Step 1: Load v1 memo --------------------------------------------------
    v1_memo = load_json(account_id, "memo.json", version="v1")
    if v1_memo is None:
        raise FileNotFoundError(
            f"v1 memo not found for account '{account_id}'. "
            "Run Pipeline A first:  python -m scripts.pipeline_a"
        )
    logger.info("Loaded v1 memo for %s", account_id)

    # -- Step 2: Ingest onboarding transcript ---------------------------------
    transcript = _ingest(input_path)
    save_text(transcript, account_id, "transcript.txt", version="v2")

    # -- Step 3: Extract onboarding updates -----------------------------------
    logger.info("Extracting onboarding updates via LLM…")
    patch_result = extract_onboarding_updates(transcript, v1_memo)
    save_json(patch_result, account_id, "patch_result.json", version="v2")

    # -- Step 4: Apply patch to produce v2 memo --------------------------------
    logger.info("Applying %d patch(es)…", len(patch_result.get("patches", [])))
    v2_memo = apply_patches(v1_memo, patch_result)
    v2_memo["account_id"] = account_id          # Ensure consistency

    # -- Step 5: Generate agent spec v2 ---------------------------------------
    logger.info("Generating Retell agent spec v2…")
    outputs = build_all_outputs(v2_memo, version="v2")
    agent_spec = outputs["agent_spec"]
    system_prompt = outputs["system_prompt"]

    # -- Step 6: Compute diff and changelog ------------------------------------
    logger.info("Computing diff v1 -> v2…")
    diff = compute_diff(v1_memo, v2_memo)
    changelog = generate_changelog(account_id, diff, patch_result)
    changelog_md = format_markdown_changelog(changelog)

    # -- Step 7: Persist all v2 artefacts ------------------------------------
    save_json(v2_memo, account_id, "memo.json", version="v2")
    save_json(agent_spec, account_id, "agent_spec.json", version="v2")
    save_text(system_prompt, account_id, "agent_prompt.txt", version="v2")
    save_json(changelog, account_id, "changelog.json", version="v2")
    save_text(changelog_md, account_id, "changelog.md", version="v2")

    # Also write to the global changelog directory
    global_cl = CHANGELOG_DIR / f"{account_id}_v1_to_v2.md"
    global_cl.write_text(changelog_md, encoding="utf-8")
    logger.info("Global changelog written to %s", global_cl)

    output_dir = str(Path(load_text.__module__).parent)  # just a label; use direct path
    from scripts.config import OUTPUTS_DIR
    output_dir = str(OUTPUTS_DIR / account_id / "v2")
    logger.info("Outputs saved to: %s", output_dir)

    # -- Step 8: Update GitHub Issue -------------------------------------------
    meta = load_json(account_id, "pipeline_meta.json", version="v1") or {}
    issue_url = meta.get("issue_url")
    update_issue(account_id, issue_url, changelog)

    # Save v2 metadata
    meta_v2 = {
        "account_id": account_id,
        "pipeline": "B",
        "version": "v2",
        "input_file": str(input_path),
        "issue_url": issue_url,
        "total_changes": changelog.get("total_changes", 0),
    }
    save_json(meta_v2, account_id, "pipeline_meta.json", version="v2")

    logger.info("=== Pipeline B complete: %s (%d changes) ===", account_id, len(diff))

    return {
        "account_id": account_id,
        "v1_memo": v1_memo,
        "v2_memo": v2_memo,
        "agent_spec": agent_spec,
        "system_prompt": system_prompt,
        "changelog": changelog,
        "changelog_md": changelog_md,
        "output_dir": output_dir,
    }


# -- CLI entry point ------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline B: onboarding transcript -> Retell agent v2 + changelog"
    )
    parser.add_argument(
        "--input", required=True, help="Path to onboarding transcript (.txt/.md) or audio file"
    )
    parser.add_argument(
        "--account_id", required=True, help="Account ID matching an existing v1 account"
    )
    args = parser.parse_args()

    result = run_pipeline_b(args.input, args.account_id)

    print("\n[ok] Pipeline B complete")
    print(f"  Account ID : {result['account_id']}")
    print(f"  Company    : {result['v2_memo'].get('company_name', '-')}")
    print(f"  Changes    : {result['changelog'].get('total_changes', 0)}")
    print(f"  Outputs    : {result['output_dir']}")
    print(f"\n  Changelog summary: {result['changelog'].get('summary', '-')}")


if __name__ == "__main__":
    _main()
