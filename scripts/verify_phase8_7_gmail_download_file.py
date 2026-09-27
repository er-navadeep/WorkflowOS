"""
WorkFlowOS — Phase 8.7: Live Gmail download_file Integration Verification Script
=================================================================================
Performs a controlled live, read-only Gmail download_file verification through:
    execution_service -> IntegrationRegistry -> GmailAdapter -> Gmail API

Verification Flow:
1. Validates local OAuth configuration without printing any secrets.
2. Performs a narrow controlled search (q='has:attachment', max_results=1) to select
   ONE real message from the mailbox.
3. Inspects that ONE message's metadata to locate ONE supported attachment.
4. Prepares an approved Gmail download_file workflow.
5. Executes download_file live via execution_service.execute_live().
6. Verifies:
   - Execution and step status are COMPLETED
   - Downloaded file exists in the controlled runtime download directory
   - File size is within configured limit
   - Path remains strictly within the download directory (no traversal)
7. Prints safe verification metadata with zero credential leakage and zero
   raw attachment content exposure.

Security Constraints:
- Scope: strictly 'https://www.googleapis.com/auth/gmail.readonly'.
- Zero Mutation: No email sending, modification, trashing, archiving, or labeling.
- Controlled Scope: Exactly ONE attachment from ONE message; NO mailbox dump.
- Never prints secrets, refresh tokens, access tokens, or Authorization headers.
- Never prints raw attachment bytes.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

# Load .env
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.database.mongodb import get_database
from app.integrations.base import StepExecutionContext
from app.integrations.gmail.adapter import (
    DEFAULT_MAX_ATTACHMENT_SIZE_BYTES,
    MAX_ATTACHMENT_SIZE_ENV_KEY,
    SUPPORTED_ATTACHMENT_EXTENSIONS,
    GmailAdapter,
)
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


def find_or_create_approved_download_file_workflow() -> Optional[WorkflowDefinition]:
    """
    Find an existing approved workflow dedicated to Gmail download_file,
    or create and approve one if none exists.
    """
    db = get_database()
    col = db["workflows"]

    # Search existing approved workflows where step 1 is Gmail / download_file and only 1 step exists
    cursor = col.find({"status": "approved"}).sort("created_at", -1)
    for doc in cursor:
        doc.pop("_id", None)
        try:
            wf = WorkflowDefinition.model_validate(doc)
            if (
                len(wf.steps) == 1
                and wf.steps[0].application.strip().lower() == "gmail"
                and wf.steps[0].action.strip().lower() == "download_file"
            ):
                return wf
        except Exception:
            continue

    # If none found, create and approve a dedicated download_file workflow
    wf_id = f"wf-gmail-dl-{uuid.uuid4().hex[:8]}"
    wf = WorkflowDefinition(
        workflow_id=wf_id,
        understanding_id=f"und-{wf_id}",
        name="Gmail Download File Verification Workflow",
        description="Phase 8.7 live verification workflow for Gmail download_file integration",
        status="approved",
        reviewed_by="developer_verification",
        reviewer_notes="Approved for Phase 8.7 live Gmail download_file read-only verification",
        approved_at=datetime.now(timezone.utc),
        trigger=WorkflowTrigger(
            application="Gmail",
            event="attachment_selected",
            description="Triggered to download a specific email attachment by ID",
        ),
        steps=[
            WorkflowStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                order=1,
                application="Gmail",
                action="download_file",
                description="Download single email attachment by messageId and attachmentId",
                inputs=["messageId", "attachmentId", "filename"],
                outputs=["filename", "path", "size_bytes", "content_type", "message_id", "attachment_id"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email attachment download",
                required_capabilities=["download_file"],
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


def find_supported_attachment_part(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Safely traverse message payload parts to find the first part
    that represents a supported attachment with an attachmentId.
    """
    stack = [payload]
    while stack:
        part = stack.pop(0)
        filename = part.get("filename", "")
        body = part.get("body", {})
        att_id = body.get("attachmentId")
        if filename and att_id:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_ATTACHMENT_EXTENSIONS:
                return {
                    "attachmentId": att_id,
                    "filename": filename,
                    "size": body.get("size", 0),
                    "mimeType": part.get("mimeType", ""),
                }
        for sub in part.get("parts", []):
            stack.append(sub)
    return None


def inspect_single_message_for_attachment(message_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch message metadata only (format='full') to inspect its payload parts for attachments.
    Does NOT download attachment bytes.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    user_id = os.getenv("GMAIL_USER_ID", "me").strip() or "me"

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    creds.refresh(Request())
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    try:
        msg = service.users().messages().get(userId=user_id, id=message_id, format="full").execute()
    except Exception as exc:
        print(f"[ERROR] Could not inspect message {message_id}: {exc}")
        return None

    payload = msg.get("payload", {})
    return find_supported_attachment_part(payload)


def get_controlled_test_attachment() -> Optional[Dict[str, Any]]:
    """
    Safely find ONE controlled test email using a narrow query ('has:attachment', max_results=1).
    Inspect that ONE message for a supported attachment.
    """
    registry = get_integration_registry()
    adapter = registry.get_adapter("Gmail", "read_email")
    if not adapter or not isinstance(adapter, GmailAdapter):
        return None

    ctx = StepExecutionContext(
        workflow_id="wf-precheck-find-attachment",
        execution_id="exec-precheck-find-attachment",
        step=WorkflowStep(
            step_id="step-find-attachment",
            order=1,
            application="Gmail",
            action="read_email",
            description="Find single message with attachment for download_file test",
            inputs=["query"],
        ),
        variables={"query": "has:attachment", "max_results": 1},
        dry_run=False,
    )

    res = adapter.execute(ctx)
    if not res.success:
        print(f"[WARNING] Controlled search failed: {res.error_summary}")
        return None

    msg_ids = res.outputs.get("message_ids", [])
    if not msg_ids:
        print("[INFO] No messages found matching query 'has:attachment'.")
        return None

    target_message_id = str(msg_ids[0])
    print(f"[OK] Found controlled test message ID: '{target_message_id}'.")
    print("     Inspecting message for supported attachment...")

    att_info = inspect_single_message_for_attachment(target_message_id)
    if not att_info:
        print(f"[INFO] Controlled message '{target_message_id}' does not contain a supported attachment.")
        return None

    att_info["messageId"] = target_message_id
    return att_info


def main() -> None:
    print("================================================================================")
    print("WorkFlowOS Phase 8.7: Live Gmail download_file Verification (Read-Only)")
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

    # 2. Find ONE controlled test email and inspect for attachment
    print("\nLocating ONE controlled test email with an attachment (query='has:attachment', max_results=1)...")
    att_target = get_controlled_test_attachment()
    if not att_target:
        print("\n--------------------------------------------------------------------------------")
        print("[NOTICE] No controlled test message with a supported attachment found.")
        print("To verify live attachment downloading:")
        print("1. Send a test email to the configured Gmail address with a supported attachment")
        print(f"   (e.g., a small .txt, .pdf, or .png file from {sorted(SUPPORTED_ATTACHMENT_EXTENSIONS)}).")
        print("2. Re-run this verification script.")
        print("--------------------------------------------------------------------------------")
        print("\nControlled search completed without broad mailbox scanning.")
        sys.exit(0)

    msg_id = att_target["messageId"]
    att_id = att_target["attachmentId"]
    filename = att_target["filename"]
    print(f"[OK] Selected target message ID   : '{msg_id}'")
    print(f"[OK] Selected target attachment ID: '{att_id[:16]}...' (truncated)")
    print(f"[OK] Attachment filename          : '{filename}'")

    # 3. Find or prepare approved download_file workflow
    wf = find_or_create_approved_download_file_workflow()
    if not wf:
        print("[FAILED] Could not locate or create an approved Gmail download_file verification workflow.")
        sys.exit(1)

    print(f"\n[OK] Target Workflow Name  : {wf.name}")
    print(f"[OK] Target Workflow ID    : {wf.workflow_id}")
    print(f"[OK] Workflow Status       : {wf.status}")
    print(f"[OK] Step 1 Target         : {wf.steps[0].application} / {wf.steps[0].action}")

    # 4. Execute download_file LIVE via ExecutionService
    print("\nExecuting live workflow via execution_service -> IntegrationRegistry -> GmailAdapter...")
    try:
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={
                "messageId": msg_id,
                "attachmentId": att_id,
                "filename": filename,
            },
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

    # 6. Verify Step Details and Filesystem Output
    step_record = execution.step_records[0]
    print(f"\nStep 1 Status    : {step_record.status}")
    print(f"Result Summary   : {step_record.result_summary}")

    if step_record.status != ExecutionStepStatus.COMPLETED:
        print(f"[FAILED] Step 1 status is not completed: {step_record.status}")
        if step_record.error_summary:
            print(f"Error summary: {step_record.error_summary}")
        sys.exit(1)

    # Validate result summary indicates successful download
    if not step_record.result_summary or "Gmail download_file completed successfully" not in step_record.result_summary:
        print(f"[FAILED] Step 1 result summary does not indicate success: {step_record.result_summary}")
        sys.exit(1)

    # Extract the saved filename from result_summary (supports collision-safe suffixes like text_1.txt)
    import re
    match = re.search(r"downloaded '([^']+)'", step_record.result_summary)
    saved_filename = match.group(1) if match else filename

    stem = Path(filename).stem
    ext = Path(filename).suffix
    if not (saved_filename == filename or (saved_filename.startswith(stem) and saved_filename.endswith(ext))):
        print(f"[FAILED] Saved filename '{saved_filename}' does not match target filename '{filename}' in result summary: {step_record.result_summary}")
        sys.exit(1)

    # Retrieve controlled download directory via the GmailAdapter
    project_root = Path(__file__).resolve().parent.parent
    registry = get_integration_registry()
    adapter = registry.get_adapter("Gmail", "download_file")
    if adapter and hasattr(adapter, "_get_download_dir"):
        download_dir = adapter._get_download_dir().resolve()
    else:
        download_dir = (project_root / "backend" / "app" / "runtime" / "downloads").resolve()

    # Locate the downloaded file in the controlled download directory
    local_file_path = download_dir / saved_filename
    if not local_file_path.exists():
        print(f"[FAILED] Downloaded file does not exist on disk: {local_file_path}")
        sys.exit(1)

    # Validate file size
    downloaded_size = local_file_path.stat().st_size
    max_size = int(os.getenv(MAX_ATTACHMENT_SIZE_ENV_KEY, DEFAULT_MAX_ATTACHMENT_SIZE_BYTES))
    if downloaded_size > max_size:
        print(f"[FAILED] Downloaded file size ({downloaded_size} bytes) exceeds limit ({max_size} bytes).")
        sys.exit(1)

    # Validate controlled path containment
    if not local_file_path.resolve().is_relative_to(download_dir):
        print(f"[FAILED] Downloaded file path escaped controlled download directory: {local_file_path}")
        sys.exit(1)

    try:
        rel_path = local_file_path.relative_to(project_root).as_posix()
    except ValueError:
        rel_path = local_file_path.name

    import mimetypes
    content_type = mimetypes.guess_type(local_file_path.name)[0] or "application/octet-stream"

    print("\n================================================================================")
    print("Live Gmail download_file Read-Only Verification SUCCESSFUL")
    print("--------------------------------------------------------------------------------")
    print(f"- Verified Action   : {step_record.application} / {step_record.action}")
    print(f"- Target Message    : {msg_id}")
    print(f"- Saved File Path   : {rel_path}")
    print(f"- Downloaded Size   : {downloaded_size} bytes (limit: {max_size} bytes)")
    print(f"- Content Type      : {content_type}")
    print(f"- Controlled Storage: Strictly within controlled download directory (gitignored)")
    print(f"- Operation Mode    : Read-Only (NO emails sent, modified, deleted, or labeled)")
    print(f"- Execution Path    : execution_service -> IntegrationRegistry -> GmailAdapter")
    print("================================================================================")


if __name__ == "__main__":
    main()
