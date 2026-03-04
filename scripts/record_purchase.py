from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from scripts.config import LOGS_DIR
from scripts.utils.storage import load_json, save_json

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    log_file = LOGS_DIR / "record_purchase.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8", mode="a"),
        ],
    )


def record_purchase(account_id: str, notes: str = "") -> dict:
    meta = load_json(account_id, "pipeline_meta.json", version="v1")
    if meta is None:
        raise FileNotFoundError(
            f"No v1 pipeline_meta.json found for account '{account_id}'. "
            "Run Pipeline A first:  python -m scripts.pipeline_a"
        )

    current_stage = meta.get("lifecycle_stage", "unknown")
    if current_stage == "purchased":
        logger.warning(
            "Account %s is already marked as purchased (recorded at %s).",
            account_id,
            meta.get("purchase_recorded_at", "unknown"),
        )
        return {"account_id": account_id, "lifecycle_stage": "purchased", "already_recorded": True}

    meta["lifecycle_stage"] = "purchased"
    meta["purchase_recorded_at"] = datetime.now(timezone.utc).isoformat()
    if notes:
        meta["purchase_notes"] = notes

    save_json(meta, account_id, "pipeline_meta.json", version="v1")

    logger.info(
        "Account %s: lifecycle_stage %s -> purchased", account_id, current_stage
    )

    return {
        "account_id": account_id,
        "lifecycle_stage": "purchased",
        "previous_stage": current_stage,
        "purchase_recorded_at": meta["purchase_recorded_at"],
        "already_recorded": False,
    }


def _main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="Stage 2 – Record that an account has purchased the service."
    )
    parser.add_argument(
        "--account_id", required=True,
        help="Account ID, e.g. ACE_PLB_001"
    )
    parser.add_argument(
        "--notes", default="",
        help="Optional notes about the purchase decision"
    )
    args = parser.parse_args()

    result = record_purchase(args.account_id, notes=args.notes)

    if result["already_recorded"]:
        print(f"\n[skip] {args.account_id} is already marked as purchased")
    else:
        print(f"\n[ok] Purchase recorded for {args.account_id}")
        print(f"  Stage         : demo_complete -> purchased")
        print(f"  Recorded at   : {result['purchase_recorded_at']}")
        if args.notes:
            print(f"  Notes         : {args.notes}")
        print("\n  Next step: run Pipeline B (onboarding)")
        print(f"  python -m scripts.pipeline_b --account_id {args.account_id} --input <onboarding_transcript>")


if __name__ == "__main__":
    _main()
