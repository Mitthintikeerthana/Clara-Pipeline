from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import AUDIO_EXTENSIONS, CHANGELOG_DIR, LOGS_DIR, OUTPUTS_DIR, TEXT_EXTENSIONS
from scripts.diff_engine import compute_diff, format_markdown_changelog, generate_changelog
from scripts.extractor import apply_patches, extract_onboarding_updates, merge_onboarding_form
from scripts.prompt_generator import build_all_outputs
from scripts.schema_validator import validate_account_memo, get_completeness_score
from scripts.task_tracker import update_issue
from scripts.utils.storage import (
    load_json,
    load_text,
    save_json,
    save_text,
)

_MEMO_FILE = "memo.json"
_META_FILE = "pipeline_meta.json"

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

def _ingest(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        text = input_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Input file is empty: {input_path}")
        logger.info("Loaded transcript (%d chars) from %s", len(text), input_path.name)
        return text
    if suffix in AUDIO_EXTENSIONS:
        logger.info("Audio file detected - running Whisper transcription...")
        from scripts.transcriber import transcribe
        return transcribe(input_path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _load_or_skip_v2(account_id: str, force: bool) -> dict | None:
    existing_memo = load_json(account_id, _MEMO_FILE, version="v2")
    if existing_memo is None or force:
        return None
    logger.info(
        "v2 outputs already exist for %s - skipping (use --force to re-run).", account_id
    )
    existing_meta = load_json(account_id, _META_FILE, version="v2") or {}
    return {
        "account_id": account_id,
        "v1_memo": load_json(account_id, _MEMO_FILE, version="v1") or {},
        "v2_memo": existing_memo,
        "agent_spec": load_json(account_id, "agent_spec.json", version="v2") or {},
        "system_prompt": load_text(account_id, "agent_prompt.txt", version="v2") or "",
        "changelog": load_json(account_id, "changelog.json", version="v2") or {},
        "changelog_md": load_text(account_id, "changelog.md", version="v2") or "",
        "output_dir": str(OUTPUTS_DIR / account_id / "v2"),
        "validation": None,
        "completeness_score": existing_meta.get("completeness_score", {}),
        "skipped": True,
    }


def _check_lifecycle_stage(account_id: str, v1_meta: dict) -> None:
    lifecycle_stage = v1_meta.get("lifecycle_stage", "unknown")
    if lifecycle_stage != "purchased":
        logger.warning(
            "Account %s lifecycle_stage is '%s', expected 'purchased'. "
            "Run: python -m scripts.record_purchase --account_id %s",
            account_id, lifecycle_stage, account_id,
        )


def _collect_patches(
    input_path: Path | None,
    form_path: Path | None,
    v1_memo: dict,
    account_id: str,
) -> tuple[dict, dict]:
    combined_patches: list[dict] = []
    combined_unknowns: list[str] = []
    patch_result: dict = {"patches": [], "questions_or_unknowns": []}
    form_patch_result: dict = {}

    if input_path is not None:
        transcript = _ingest(input_path)
        save_text(transcript, account_id, "transcript.txt", version="v2")
        logger.info("Extracting onboarding updates...")
        patch_result = extract_onboarding_updates(transcript, v1_memo)
        save_json(patch_result, account_id, "patch_result.json", version="v2")
        combined_patches.extend(patch_result.get("patches", []))
        combined_unknowns.extend(patch_result.get("questions_or_unknowns", []))

    if form_path is not None:
        logger.info("Processing onboarding form: %s", form_path.name)
        with form_path.open(encoding="utf-8") as fh:
            form_data = json.load(fh)
        form_patch_result = merge_onboarding_form(form_data, v1_memo)
        save_json(form_patch_result, account_id, "form_patch_result.json", version="v2")
        combined_patches.extend(form_patch_result.get("patches", []))
        combined_unknowns.extend(form_patch_result.get("questions_or_unknowns", []))
        conflicts = form_patch_result.get("conflicts", [])
        if conflicts:
            logger.warning("Form merge conflicts detected (%d): %s", len(conflicts), conflicts)

    merged_patch = dict(patch_result)
    merged_patch["patches"] = combined_patches
    merged_patch["questions_or_unknowns"] = list(dict.fromkeys(combined_unknowns))
    if form_patch_result:
        merged_patch.setdefault("_metadata", {})
        merged_patch["_metadata"]["_form_merged"] = True
        merged_patch["_metadata"]["_form_conflicts"] = form_patch_result.get("conflicts", [])

    return merged_patch, form_patch_result


def _save_v2_outputs(
    account_id: str,
    v2_memo: dict,
    agent_spec: dict,
    system_prompt: str,
    changelog: dict,
    changelog_md: str,
) -> str:
    save_json(v2_memo, account_id, _MEMO_FILE, version="v2")
    save_json(agent_spec, account_id, "agent_spec.json", version="v2")
    save_text(system_prompt, account_id, "agent_prompt.txt", version="v2")
    save_json(changelog, account_id, "changelog.json", version="v2")
    save_text(changelog_md, account_id, "changelog.md", version="v2")

    global_cl = CHANGELOG_DIR / f"{account_id}_v1_to_v2.md"
    global_cl.write_text(changelog_md, encoding="utf-8")
    logger.info("Global changelog written to %s", global_cl)

    output_dir = str(OUTPUTS_DIR / account_id / "v2")
    logger.info("Outputs saved to: %s", output_dir)
    return output_dir


def run_pipeline_b(
    input_path: str | Path | None,
    account_id: str,
    form_path: str | Path | None = None,
    force: bool = False,
) -> dict:
    if input_path is None and form_path is None:
        raise ValueError("At least one of --input (transcript) or --form must be provided.")

    _setup_logging(account_id)

    skipped = _load_or_skip_v2(account_id, force)
    if skipped is not None:
        return skipped

    input_label = Path(input_path).name if input_path else "(form only)"
    logger.info("=== Pipeline B starting: %s -> %s ===", input_label, account_id)

    v1_memo = load_json(account_id, _MEMO_FILE, version="v1")
    if v1_memo is None:
        raise FileNotFoundError(
            f"v1 memo not found for account '{account_id}'. "
            "Run Pipeline A first:  python -m scripts.pipeline_a"
        )
    logger.info("Loaded v1 memo for %s", account_id)

    v1_meta = load_json(account_id, _META_FILE, version="v1") or {}
    _check_lifecycle_stage(account_id, v1_meta)

    merged_patch, form_patch_result = _collect_patches(
        Path(input_path) if input_path else None,
        Path(form_path) if form_path else None,
        v1_memo,
        account_id,
    )

    logger.info("Applying %d patch(es)...", len(merged_patch.get("patches", [])))
    v2_memo = apply_patches(v1_memo, merged_patch)
    v2_memo["account_id"] = account_id

    logger.info("Validating v2 account memo...")
    validation = validate_account_memo(v2_memo)
    completeness = get_completeness_score(v2_memo)

    if validation.errors:
        logger.warning("Validation errors: %s", validation.errors)
    if validation.warnings:
        logger.warning("Validation warnings: %s", validation.warnings)

    logger.info(
        "Completeness score: overall=%s (was demo-derived: %s)",
        completeness["overall"],
        validation.is_demo_derived,
    )

    logger.info("Generating Retell agent spec v2...")
    outputs = build_all_outputs(v2_memo, version="v2")
    agent_spec = outputs["agent_spec"]
    system_prompt = outputs["system_prompt"]

    logger.info("Computing diff v1 -> v2...")
    diff = compute_diff(v1_memo, v2_memo)
    changelog = generate_changelog(
        account_id,
        diff,
        merged_patch,
        v1_metadata=v1_memo.get("_metadata", {}),
        v2_metadata=v2_memo.get("_metadata", {}),
    )
    changelog_md = format_markdown_changelog(changelog)

    output_dir = _save_v2_outputs(
        account_id, v2_memo, agent_spec, system_prompt, changelog, changelog_md
    )

    issue_url = v1_meta.get("issue_url")
    update_issue(account_id, issue_url, changelog)

    meta_v2 = {
        "account_id": account_id,
        "pipeline": "B",
        "version": "v2",
        "lifecycle_stage": "onboarding_complete",
        "input_file": str(input_path) if input_path else None,
        "form_file": str(form_path) if form_path else None,
        "issue_url": issue_url,
        "total_changes": changelog.get("total_changes", 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation.to_dict(),
        "completeness_score": completeness,
        "source": v2_memo.get("_metadata", {}).get("_source", "onboarding"),
        "conflicts_resolved": changelog.get("conflicts_resolved", []),
        "form_conflicts": form_patch_result.get("conflicts", []) if form_patch_result else [],
        "v1_source": v1_memo.get("_metadata", {}).get("_source", "demo"),
    }
    save_json(meta_v2, account_id, _META_FILE, version="v2")

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
        "validation": validation,
        "completeness_score": completeness,
    }

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline B: onboarding transcript -> Retell agent v2 + changelog"
    )
    parser.add_argument(
        "--input", default=None,
        help="Path to onboarding transcript (.txt/.md) or audio file"
    )
    parser.add_argument(
        "--account_id", required=True, help="Account ID matching an existing v1 account"
    )
    parser.add_argument(
        "--form", default=None, metavar="FORM_JSON",
        help="Path to structured onboarding form JSON (optional, can be used alone or with --input)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-run even if v2 outputs already exist"
    )
    args = parser.parse_args()

    result = run_pipeline_b(
        args.input,
        args.account_id,
        form_path=args.form,
        force=args.force,
    )

    if result.get("skipped"):
        print(f"\n[skip] v2 already exists for {result['account_id']} (use --force to re-run)")
        return

    print("\n[ok] Pipeline B complete")
    print(f"  Account ID : {result['account_id']}")
    print(f"  Company    : {result['v2_memo'].get('company_name', '-')}")
    print(f"  Changes    : {result['changelog'].get('total_changes', 0)}")
    print(f"  Outputs    : {result['output_dir']}")
    print(f"\n  Changelog summary: {result['changelog'].get('summary', '-')}")

if __name__ == "__main__":
    _main()
