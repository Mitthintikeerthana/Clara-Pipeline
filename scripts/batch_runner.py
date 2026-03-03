from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from scripts.config import INPUTS_DIR, LOGS_DIR

logger = logging.getLogger(__name__)

def _setup_root_logging() -> None:
    log_file = LOGS_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logger.info("Batch log -> %s", log_file)

def _load_manifest() -> dict:
    manifest_path = INPUTS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found at {manifest_path}.\n"
            "Ensure inputs/manifest.json exists. See README for format."
        )
    with manifest_path.open(encoding="utf-8") as fh:
        return json.load(fh)

def _run_a_safe(input_path: str, account_id: str) -> dict:
    from scripts.pipeline_a import run_pipeline_a
    start = time.monotonic()
    try:
        result = run_pipeline_a(input_path, account_id)
        elapsed = time.monotonic() - start
        return {
            "account_id": account_id,
            "pipeline": "A",
            "status": "success",
            "elapsed_sec": round(elapsed, 2),
            "company": result["memo"].get("company_name", "-"),
            "output_dir": result["output_dir"],
            "issue_url": result.get("issue_url"),
            "error": None,
        }
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error("Pipeline A FAILED for %s: %s", account_id, exc, exc_info=True)
        return {
            "account_id": account_id,
            "pipeline": "A",
            "status": "failed",
            "elapsed_sec": round(elapsed, 2),
            "company": "-",
            "output_dir": None,
            "issue_url": None,
            "error": str(exc),
        }

def _run_b_safe(input_path: str, account_id: str) -> dict:
    from scripts.pipeline_b import run_pipeline_b
    start = time.monotonic()
    try:
        result = run_pipeline_b(input_path, account_id)
        elapsed = time.monotonic() - start
        return {
            "account_id": account_id,
            "pipeline": "B",
            "status": "success",
            "elapsed_sec": round(elapsed, 2),
            "company": result["v2_memo"].get("company_name", "-"),
            "output_dir": result["output_dir"],
            "total_changes": result["changelog"].get("total_changes", 0),
            "error": None,
        }
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error("Pipeline B FAILED for %s: %s", account_id, exc, exc_info=True)
        return {
            "account_id": account_id,
            "pipeline": "B",
            "status": "failed",
            "elapsed_sec": round(elapsed, 2),
            "company": "-",
            "output_dir": None,
            "total_changes": 0,
            "error": str(exc),
        }

def run_batch(
    run_demo: bool = True,
    run_onboarding: bool = True,
    filter_account: str | None = None,
) -> dict:
    manifest = _load_manifest()
    accounts: list[dict] = manifest.get("accounts", [])

    if filter_account:
        accounts = [a for a in accounts if a["account_id"] == filter_account]
        if not accounts:
            raise ValueError(f"Account '{filter_account}' not found in manifest.")

    results_a: list[dict] = []
    results_b: list[dict] = []

    if run_demo:
        logger.info("=== Running Pipeline A for %d accounts ===", len(accounts))
        for entry in accounts:
            account_id = entry["account_id"]
            demo_file = INPUTS_DIR / "demo" / entry["demo_file"]
            logger.info("-> Pipeline A: %s (%s)", account_id, demo_file.name)
            result = _run_a_safe(str(demo_file), account_id)
            results_a.append(result)
            if result["status"] == "success":
                logger.info("  OK %s - %s", account_id, result["company"])
            else:
                logger.warning("  FAIL %s - %s", account_id, result["error"])

    if run_onboarding:
        logger.info("=== Running Pipeline B for %d accounts ===", len(accounts))
        for entry in accounts:
            account_id = entry["account_id"]
            onboarding_file = INPUTS_DIR / "onboarding" / entry["onboarding_file"]
            logger.info("-> Pipeline B: %s (%s)", account_id, onboarding_file.name)
            result = _run_b_safe(str(onboarding_file), account_id)
            results_b.append(result)
            if result["status"] == "success":
                logger.info(
                    "  OK %s - %d changes", account_id, result.get("total_changes", 0)
                )
            else:
                logger.warning("  FAIL %s - %s", account_id, result["error"])

    all_results = results_a + results_b
    successes = sum(1 for r in all_results if r["status"] == "success")
    failures = sum(1 for r in all_results if r["status"] == "failed")

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_accounts": len(accounts),
        "pipeline_a_results": results_a,
        "pipeline_b_results": results_b,
        "successes": successes,
        "failures": failures,
    }

    summary_path = LOGS_DIR / "batch_summary.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    logger.info("Batch summary written to %s", summary_path)

    return summary

def _main() -> None:
    _setup_root_logging()

    parser = argparse.ArgumentParser(
        description="Run the Clara pipeline on all 5 demo + 5 onboarding files."
    )
    parser.add_argument("--demo-only", action="store_true", help="Run Pipeline A only")
    parser.add_argument(
        "--onboarding-only", action="store_true", help="Run Pipeline B only"
    )
    parser.add_argument(
        "--account", metavar="ACCOUNT_ID", help="Run for a single account only"
    )
    args = parser.parse_args()

    run_demo = not args.onboarding_only
    run_onboarding = not args.demo_only

    summary = run_batch(
        run_demo=run_demo,
        run_onboarding=run_onboarding,
        filter_account=args.account,
    )

    print("\n" + "=" * 60)
    print("  BATCH COMPLETE")
    print("=" * 60)

    if summary["pipeline_a_results"]:
        print("\n  Pipeline A (Demo -> v1)")
        print(f"  {'Account':<20} {'Company':<28} {'Status':<8} {'Time':>6}s")
        print(f"  {'-'*20} {'-'*28} {'-'*8} {'-'*7}")
        for r in summary["pipeline_a_results"]:
            status = "[ok]" if r["status"] == "success" else "[FAIL]"
            print(f"  {r['account_id']:<20} {r['company'][:27]:<28} {status:<8} {r['elapsed_sec']:>7.1f}")

    if summary["pipeline_b_results"]:
        print("\n  Pipeline B (Onboarding -> v2)")
        print(f"  {'Account':<20} {'Company':<28} {'Status':<8} {'Changes':>8}")
        print(f"  {'-'*20} {'-'*28} {'-'*8} {'-'*8}")
        for r in summary["pipeline_b_results"]:
            status = "[ok]" if r["status"] == "success" else "[FAIL]"
            changes = r.get("total_changes", "-")
            print(f"  {r['account_id']:<20} {r['company'][:27]:<28} {status:<8} {str(changes):>8}")

    print(f"\n  Successes: {summary['successes']}  |  Failures: {summary['failures']}")
    print("=" * 60)

    if summary["failures"] > 0:
        sys.exit(1)

if __name__ == "__main__":
    _main()
