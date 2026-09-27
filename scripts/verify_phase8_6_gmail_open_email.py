"""
WorkFlowOS — Phase 8.6: Live Gmail open_email Integration Verification Script
=============================================================================
Performs a controlled live, read-only Gmail open_email verification through:
    execution_service -> IntegrationRegistry -> GmailAdapter -> Gmail API

Verification Flow:
1. Validates local OAuth configuration without printing any secrets.
2. Performs a narrow controlled search (label:INBOX, max_results=1) to select
   exactly ONE real message ID from the mailbox.
3. Prepares an approved Gmail open_email workflow.
4. Executes open_email live via execution_service.execute_live().
5. Prints safe verification metadata (workflow name, IDs, status, sender, subject)
   with zero body exposure and zero credential leakage.

Security Constraints:
- Scope: strictly 'https://www.googleapis.com/auth/gmail.readonly'.
- Zero Mutation: No email sending, modification, trashing, archiving, or labeling.
- Controlled Scope: Exactly ONE message opened; NO mailbox dump.
- Never prints secrets, refresh tokens, access tokens, or Authorization headers.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

# Load .env
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.database.mongodb import get_database
from app.integrations.base import StepExecutionContext
from app.integrations.registry import get_integration_registry
from app.models.workflow import upsert_workflow
from app.schemas.execution import ExecutionMode, ExecutionStatus, ExecutionStepStatus
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.execution_service import execute_live


def find_or_create_approved_open_email_workflow() -> Optional[WorkflowDefinition]:
    """
    Find an existing approved workflow dedicated to Gmail open_email,
    or create and approve one if none exists.
    """
    db = get_database()
    col = db["workflows"]

    # Search existing approved workflows where step 1 is Gmail / open_email and only 1 step exists
    cursor = col.find({"status": "approved"}).sort("created_at", -1)
    for doc in cursor:
        doc.pop("_id", None)
        try:
            wf = WorkflowDefinition.model_validate(doc)
            if (
                len(wf.steps) == 1
                and wf.steps[0].application.strip().lower() == "gmail"
                and wf.steps[0].action.strip().lower() == "open_email"
            ):
                return wf
        except Exception:
            continue

    # If none found, create and approve a dedicated open_email workflow
    wf_id = f"wf-gmail-open-{uuid.uuid4().hex[:8]}"
    wf = WorkflowDefinition(
        workflow_id=wf_id,
        understanding_id=f"und-{wf_id}",
        name="Gmail Open Email Verification Workflow",
        description="Phase 8.6 live verification workflow for Gmail open_email integration",
        status="approved",
        reviewed_by="developer_verification",
        reviewer_notes="Approved for Phase 8.6 live Gmail open_email read-only verification",
        approved_at=datetime.now(timezone.utc),
        trigger=WorkflowTrigger(
            application="Gmail",
            event="email_selected",
            description="Triggered to open a specific email by ID",
        ),
        steps=[
            WorkflowStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                order=1,
                application="Gmail",
                action="open_email",
                description="Retrieve single email metadata by messageId",
                inputs=["messageId"],
                outputs=["messageId", "threadId", "subject", "sender", "recipient", "snippet"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email metadata inspection",
                required_capabilities=["open_email"],
            )
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="stop",
        ),
        created_at=datetime.now(timezone.utc),
    )
    upsert_workflow(wf)
    return wf


def get_single_message_id_safely() -> Optional[str]:
    """
    Safely find ONE real message ID in the mailbox via a narrow controlled search.
    """
    registry = get_integration_registry()
    adapter = registry.get_adapter("Gmail", "read_email")
    if not adapter:
        return None

    ctx = StepExecutionContext(
        workflow_id="wf-precheck-find-id",
        execution_id="exec-precheck-find-id",
        step=WorkflowStep(
            step_id="step-find-id",
            order=1,
            application="Gmail",
            action="read_email",
            description="Find single message ID for open_email test",
            inputs=["query"],
        ),
        variables={"query": "label:INBOX", "max_results": 1},
        dry_run=False,
    )

    res = adapter.execute(ctx)
    if not res.success:
        return None

    msg_ids = res.outputs.get("message_ids", [])
    if msg_ids:
        return str(msg_ids[0])
    return None


def main() -> None:
    print("================================================================================")
    print("WorkFlowOS Phase 8.6: Live Gmail open_email Verification (Read-Only)")
    print("================================================================================\n")

    # 1. Verify OAuth Configuration
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()

    missing = []
    if not client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not refresh_token:
        missing.append("GOOGLE_REFRESH_TOKEN")

    if missing:
        print(f"[FAILED] Missing required environment variable(s): {', '.join(missing)}")
        print("Please configure these in your local .env file before running verification.")
        sys.exit(1)

    print("[OK] Google OAuth configuration present (Client ID, Secret, and Refresh Token configured).")
    print("[OK] Credentials hidden for security.")

    # 2. Locate ONE real message ID via narrow controlled search
    print("\nFinding ONE controlled test message ID safely via narrow read-only query...")
    target_message_id = get_single_message_id_safely()
    if not target_message_id:
        print("[FAILED] Could not retrieve a test message ID from mailbox (no messages in INBOX).")
        sys.exit(1)

    print(f"[OK] Selected target message ID: '{target_message_id}' (single message selected; zero mailbox dump).")

    # 3. Find or prepare approved open_email workflow
    wf = find_or_create_approved_open_email_workflow()
    if not wf:
        print("[FAILED] Could not locate or create an approved Gmail open_email verification workflow.")
        sys.exit(1)

    print(f"\n[OK] Target Workflow Name  : {wf.name}")
    print(f"[OK] Target Workflow ID    : {wf.workflow_id}")
    print(f"[OK] Workflow Status       : {wf.status}")
    print(f"[OK] Step 1 Target         : {wf.steps[0].application} / {wf.steps[0].action}")

    # 4. Execute open_email LIVE via ExecutionService
    print("\nExecuting live workflow via execution_service -> IntegrationRegistry -> GmailAdapter...")
    try:
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"messageId": target_message_id},
        )
    except Exception as exc:
        print(f"\n[FAILED] Live execution raised exception: {exc}")
        sys.exit(1)

    # 5. Inspect Execution Record
    print(f"\nExecution ID     : {execution.execution_id}")
    print(f"Execution Mode   : {execution.mode}")
    print(f"Execution Status : {execution.status}")
    print(f"Completed Steps  : {execution.completed_steps} / {len(execution.step_records)}")

    if execution.status != ExecutionStatus.COMPLETED:
        print(f"\n[FAILED] Execution ended with status: {execution.status}")
        if execution.error_information:
            print(f"Error information: {execution.error_information}")
        sys.exit(1)

    # 6. Display Step Verification Details
    step_record = execution.step_records[0]
    print(f"\nStep 1 Status    : {step_record.status}")
    print(f"Result Summary   : {step_record.result_summary}")

    print("\n================================================================================")
    print("Live Gmail open_email Read-Only Verification SUCCESSFUL")
    print("--------------------------------------------------------------------------------")
    print(f"- Verified Action : {step_record.application} / {step_record.action}")
    print(f"- Target Message  : {target_message_id}")
    print(f"- Operation Mode  : Read-Only (NO emails sent, modified, deleted, or labeled)")
    print(f"- Execution Path  : execution_service -> IntegrationRegistry -> GmailAdapter")
    print("================================================================================")


if __name__ == "__main__":
    main()
