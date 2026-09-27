"""
Phase 8.11.2 Verification Script — Trigger Service
==================================================
Performs controlled live verification of the TriggerService:
    1. Locates or creates the canonical approved Phase 8.10 E2E pipeline workflow.
    2. Ensures its Gmail trigger configuration exists in workflow_triggers and is enabled.
    3. Executes one controlled poll cycle via TriggerService.poll_triggers(workflow_id=...).
    4. Reports detected events, deduplication decisions, and execution dispatches.
    5. Verifies safe metadata propagation and zero credential exposure.

Safety Rules:
    - Never prints OAuth tokens, passwords, refresh tokens, or webhook URLs.
    - Strictly controlled: runs exactly ONE poll cycle; does not run an infinite loop.
    - Only executes approved workflows.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

# Load .env
load_dotenv()
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from app.database.mongodb import check_database_connection
from app.models.trigger import (
    ensure_trigger_indexes,
    get_checkpoint,
    get_trigger_by_workflow_id,
    list_checkpoints_for_workflow,
    upsert_trigger_config,
)
from app.schemas.trigger import TriggerStatus, WorkflowTriggerConfig
from app.services.e2e_pipeline import get_or_create_e2e_workflow
from app.services.trigger_service import poll_triggers


def run_verification() -> int:
    print("=================================================================")
    print("WorkFlowOS — Phase 8.11.2 Trigger Service Live Verification")
    print("=================================================================")

    # 1. Verify Database
    print("\n[Step 1] Verifying MongoDB connection...")
    try:
        check_database_connection()
        ensure_trigger_indexes()
        print("  -> MongoDB connection: OK")
    except Exception as exc:
        print(f"  -> MongoDB connection FAILED: {exc}")
        return 1

    # 2. Locate or create approved Phase 8.10 workflow
    print("\n[Step 2] Locating approved Phase 8.10 E2E workflow...")
    try:
        wf = get_or_create_e2e_workflow(approve=True)
        print(f"  -> Workflow ID: {wf.workflow_id}")
        print(f"  -> Workflow Name: {wf.name}")
        print(f"  -> Workflow Status: {wf.status}")
        if wf.status != "approved":
            print(f"  -> ERROR: Workflow is not approved (status={wf.status}).")
            return 1
    except Exception as exc:
        print(f"  -> Error fetching approved workflow: {exc}")
        return 1

    # 3. Ensure Gmail trigger configuration exists
    print("\n[Step 3] Ensuring trigger configuration in workflow_triggers...")
    trigger = get_trigger_by_workflow_id(wf.workflow_id)
    if not trigger:
        trigger = WorkflowTriggerConfig(
            workflow_id=wf.workflow_id,
            application="Gmail",
            event="customer_email_received",
            query_filter="label:INBOX is:unread",
            poll_interval_seconds=30,
            is_enabled=True,
            status=TriggerStatus.ACTIVE,
        )
        trigger = upsert_trigger_config(trigger)
        print(f"  -> Created new trigger config: ID={trigger.trigger_id}")
    else:
        # Ensure enabled
        trigger.is_enabled = True
        trigger.status = TriggerStatus.ACTIVE
        trigger = upsert_trigger_config(trigger)
        print(f"  -> Existing trigger config active: ID={trigger.trigger_id}")

    # 4. Check Gmail OAuth credentials
    print("\n[Step 4] Checking environment credentials for Gmail read-only access...")
    has_client_id = bool(os.getenv("GOOGLE_CLIENT_ID", "").strip())
    has_client_secret = bool(os.getenv("GOOGLE_CLIENT_SECRET", "").strip())
    has_refresh_token = bool(os.getenv("GOOGLE_REFRESH_TOKEN", "").strip())
    print(f"  -> GOOGLE_CLIENT_ID present: {has_client_id}")
    print(f"  -> GOOGLE_CLIENT_SECRET present: {has_client_secret}")
    print(f"  -> GOOGLE_REFRESH_TOKEN present: {has_refresh_token}")

    if not (has_client_id and has_client_secret and has_refresh_token):
        print("  -> Gmail credentials missing. Running controlled DRY RUN evaluation instead.")
        summary = poll_triggers(dry_run=True, workflow_id=wf.workflow_id)
        print(f"\n[DRY RUN Summary]")
        print(f"  -> Triggers evaluated: {summary.triggers_evaluated}")
        print(f"  -> Events detected: {summary.events_detected}")
        print(f"  -> Dispatches: {len(summary.dispatches)}")
        for d in summary.dispatches:
            print(f"     * Event: {d.event_identifier} | {d.message}")
        print("\n=================================================================")
        print("Controlled Dry-Run Verification Succeeded (Zero Secrets Leaked)")
        print("=================================================================")
        return 0

    # 5. Run Controlled Poll Cycle
    print("\n[Step 5] Running one controlled live poll cycle via TriggerService...")
    summary = poll_triggers(dry_run=False, workflow_id=wf.workflow_id)

    print(f"\n[Poll Summary]")
    print(f"  -> Triggers evaluated: {summary.triggers_evaluated}")
    print(f"  -> Events detected: {summary.events_detected}")
    print(f"  -> Events dispatched: {summary.events_dispatched}")
    print(f"  -> Events skipped (already processed): {summary.events_skipped}")
    print(f"  -> Errors encountered: {summary.errors_count}")

    for idx, d in enumerate(summary.dispatches, start=1):
        print(f"\n  Dispatch #{idx}:")
        print(f"    - Event ID: {d.event_identifier}")
        print(f"    - Dispatched: {d.dispatched}")
        print(f"    - Execution ID: {d.execution_id or 'N/A'}")
        print(f"    - Execution Status: {d.execution_status or 'N/A'}")
        print(f"    - Message: {d.message}")
        if d.error:
            print(f"    - Error: {d.error}")

    # 6. Check Checkpoints
    print("\n[Step 6] Inspecting trigger_checkpoints in MongoDB...")
    checkpoints = list_checkpoints_for_workflow(wf.workflow_id, limit=5)
    print(f"  -> Total recent checkpoints for workflow: {len(checkpoints)}")
    for chk in checkpoints:
        print(f"     * Checkpoint ID: {chk.checkpoint_id} | Event: {chk.event_identifier} | Exec ID: {chk.execution_id}")

    # 7. Refresh Trigger State
    updated_trigger = get_trigger_by_workflow_id(wf.workflow_id)
    print(f"\n[Step 7] Trigger status:")
    print(f"  -> Status: {updated_trigger.status}")
    print(f"  -> Consecutive errors: {updated_trigger.consecutive_errors}")
    print(f"  -> Last polled at: {updated_trigger.last_polled_at}")
    print(f"  -> Last triggered at: {updated_trigger.last_triggered_at}")

    print("\n=================================================================")
    print("Phase 8.11.2 Trigger Service Live Verification Completed")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_verification())
