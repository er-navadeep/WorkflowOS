"""
WorkFlowOS - Phase 8.9: Local Mock CRM update_customer Verification Script
===========================================================================
Performs a controlled live verification of the CRM update_customer integration:
    execution_service -> IntegrationRegistry -> CRMAdapter -> MockCRM (MongoDB)

Verification Flow:
1. Ensures deterministic seed data exists in mock_crm_customers collection.
2. Records the current state of the test customer (nav@example.test / CUST-1004).
3. Creates or reuses an approved CRM update_customer verification workflow.
4. Executes CRM / update_customer LIVE with controlled updates.
5. Verifies execution completed, step completed, customerFound=True, updated=True.
6. Verifies the updated fields (status, notes) are reflected in the result.
7. Verifies unrelated fields (name, company, customer_identifier) were NOT changed.
8. Restores the test customer to its original seed state.
9. Verifies the restoration was successful.

Security Constraints:
- Local mock CRM ONLY. No external CRM connections.
- No real credentials, API keys, or OAuth tokens required.
- Only synthetic .test-domain identifiers used.
- Test data is restored after verification.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.database.mongodb import get_database
from app.models.mock_crm import (
    ensure_seed_data,
    find_customer_by_identifier,
    restore_customer_to_seed,
    SEED_CUSTOMERS,
    ALLOWED_UPDATE_FIELDS,
    ALLOWED_STATUS_VALUES,
)
from app.models.workflow import upsert_workflow
from app.schemas.execution import ExecutionStatus, ExecutionStepStatus
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.execution_service import execute_live


# ---------------------------------------------------------------------------
# Verification target
# ---------------------------------------------------------------------------
TEST_IDENTIFIER = "nav@example.test"
TEST_CUSTOMER_ID = "CUST-1004"
TEST_UPDATE_STATUS = "processed"
TEST_UPDATE_NOTES = "WorkFlowOS Phase 8.9 verification"

# Fields that must NOT change during the update
IMMUTABLE_FIELDS = ("customer_id", "customer_identifier", "email", "name", "company")


def find_or_create_approved_update_workflow() -> WorkflowDefinition:
    """
    Find an existing approved CRM update_customer workflow or create one.
    """
    db = get_database()
    col = db["workflows"]

    cursor = col.find({"status": "approved"}).sort("created_at", -1)
    for doc in cursor:
        doc.pop("_id", None)
        try:
            wf = WorkflowDefinition.model_validate(doc)
            if (
                len(wf.steps) == 1
                and wf.steps[0].application.strip().lower() == "crm"
                and wf.steps[0].action.strip().lower() == "update_customer"
            ):
                return wf
        except Exception:
            continue

    wf_id = f"wf-crm-uc-{uuid.uuid4().hex[:8]}"
    wf = WorkflowDefinition(
        workflow_id=wf_id,
        understanding_id=f"und-{wf_id}",
        name="CRM Update Customer Verification Workflow",
        description="Phase 8.9 live verification workflow for CRM update_customer",
        status="approved",
        reviewed_by="developer_verification",
        reviewer_notes="Approved for Phase 8.9 live CRM update_customer read-write verification",
        approved_at=datetime.now(timezone.utc),
        trigger=WorkflowTrigger(
            application="CRM",
            event="customer_update_requested",
            description="Triggered to update a customer record by identifier",
        ),
        steps=[
            WorkflowStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                order=1,
                application="CRM",
                action="update_customer",
                description="Update customer by identifier in local mock CRM",
                inputs=["customerIdentifier", "updates"],
                outputs=["customerFound", "updated", "customerId", "updatedFields", "customer"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="CRM",
                purpose="Customer update",
                required_capabilities=["update_customer"],
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


def run_update_test(wf: WorkflowDefinition, before_state: dict) -> bool:
    """Execute the live update and verify the result."""
    print(f"\n[TEST] Executing CRM update_customer for '{TEST_IDENTIFIER}'")
    print(f"  Updates : status='{TEST_UPDATE_STATUS}', notes='{TEST_UPDATE_NOTES}'")

    try:
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={
                "customerIdentifier": TEST_IDENTIFIER,
                "updates": {
                    "status": TEST_UPDATE_STATUS,
                    "notes": TEST_UPDATE_NOTES,
                },
            },
        )
    except Exception as exc:
        print(f"[FAILED] Live execution raised exception: {exc}")
        return False

    print(f"  Execution ID     : {execution.execution_id}")
    print(f"  Execution Status : {execution.status}")
    print(f"  Completed Steps  : {execution.completed_steps} / {len(execution.step_records)}")

    if execution.status != ExecutionStatus.COMPLETED:
        print(f"[FAILED] Execution did not complete. Status: {execution.status}")
        if execution.error_information:
            print(f"  Error: {execution.error_information}")
        return False

    step_rec = execution.step_records[0]
    print(f"  Step Status      : {step_rec.status}")
    print(f"  Result Summary   : {step_rec.result_summary}")

    if step_rec.status != ExecutionStepStatus.COMPLETED:
        print(f"[FAILED] Step did not complete. Status: {step_rec.status}")
        return False

    # Check result summary mentions customer ID
    if TEST_CUSTOMER_ID not in step_rec.result_summary:
        print(f"[FAILED] Expected '{TEST_CUSTOMER_ID}' in result summary.")
        return False

    print(f"[PASS] Execution verified - customer '{TEST_CUSTOMER_ID}' updated.")

    # Verify the actual DB record was changed
    after_state = find_customer_by_identifier(TEST_IDENTIFIER)
    if after_state is None:
        print(f"[FAILED] Customer '{TEST_IDENTIFIER}' no longer findable after update!")
        return False

    print("\n[CHECK] Verifying updated fields in database...")
    if after_state.get("status") != TEST_UPDATE_STATUS:
        print(f"[FAILED] status not updated. Expected '{TEST_UPDATE_STATUS}', got '{after_state.get('status')}'")
        return False
    print(f"  [OK] status   : '{after_state.get('status')}' (expected '{TEST_UPDATE_STATUS}')")

    if after_state.get("notes") != TEST_UPDATE_NOTES:
        print(f"[FAILED] notes not updated. Expected '{TEST_UPDATE_NOTES}', got '{after_state.get('notes')}'")
        return False
    print(f"  [OK] notes    : '{after_state.get('notes')}' (expected)")

    # Verify immutable fields were NOT changed
    print("\n[CHECK] Verifying immutable fields unchanged...")
    all_immutable_ok = True
    for field in IMMUTABLE_FIELDS:
        before_val = before_state.get(field)
        after_val = after_state.get(field)
        if before_val != after_val:
            print(f"  [FAILED] '{field}' changed from '{before_val}' to '{after_val}'!")
            all_immutable_ok = False
        else:
            print(f"  [OK] '{field}' unchanged: '{after_val}'")

    if not all_immutable_ok:
        return False

    print("[PASS] All immutable fields unchanged.")
    return True


def run_restore_test() -> bool:
    """Restore the test customer and verify the restoration."""
    print(f"\n[RESTORE] Restoring '{TEST_CUSTOMER_ID}' to seed state...")

    success = restore_customer_to_seed(TEST_CUSTOMER_ID)
    if not success:
        print(f"[FAILED] restore_customer_to_seed returned False for '{TEST_CUSTOMER_ID}'")
        return False

    restored = find_customer_by_identifier(TEST_IDENTIFIER)
    if restored is None:
        print("[FAILED] Customer not found after restoration!")
        return False

    seed = next((s for s in SEED_CUSTOMERS if s["customer_id"] == TEST_CUSTOMER_ID), None)
    if seed is None:
        print("[FAILED] Seed record not found!")
        return False

    if restored.get("status") != seed.get("status"):
        print(f"[FAILED] Status not restored. Got '{restored.get('status')}', expected '{seed.get('status')}'")
        return False

    if "notes" in restored and restored["notes"] is not None:
        print(f"[FAILED] Notes field still present after restoration: '{restored.get('notes')}'")
        return False

    print(f"  [OK] status restored to '{restored.get('status')}'")
    print(f"  [OK] notes field cleared (not present or None)")
    print("[PASS] Customer successfully restored to seed state.")
    return True


def main() -> None:
    print("=" * 80)
    print("WorkFlowOS Phase 8.9: Local Mock CRM update_customer Verification")
    print("=" * 80)

    # 1. Seed
    print(f"\n[STEP 1] Seeding mock CRM...")
    try:
        upserted = ensure_seed_data()
        print(f"[OK] Seed: {upserted} new record(s) inserted ({len(SEED_CUSTOMERS)} total).")
    except Exception as exc:
        print(f"[FAILED] Could not seed mock CRM: {exc}")
        sys.exit(1)

    # 2. Record before-state
    print(f"\n[STEP 2] Recording before-state for '{TEST_IDENTIFIER}'...")
    before_state = find_customer_by_identifier(TEST_IDENTIFIER)
    if before_state is None:
        print(f"[FAILED] Test customer '{TEST_IDENTIFIER}' not found in mock CRM!")
        sys.exit(1)
    print(f"  Customer ID     : {before_state.get('customer_id')}")
    print(f"  Name            : {before_state.get('name')}")
    print(f"  Status (before) : {before_state.get('status')}")
    print(f"  Notes (before)  : {before_state.get('notes', None)}")

    # 3. Workflow
    print(f"\n[STEP 3] Preparing approved CRM update_customer workflow...")
    try:
        wf = find_or_create_approved_update_workflow()
    except Exception as exc:
        print(f"[FAILED] Could not create/find workflow: {exc}")
        sys.exit(1)
    print(f"[OK] Workflow: {wf.name}")
    print(f"[OK] Step Target: {wf.steps[0].application} / {wf.steps[0].action}")

    # 4. Test
    update_passed = run_update_test(wf, before_state)

    # 5. Restore
    restore_passed = run_restore_test()

    # 6. Summary
    print("\n" + "=" * 80)
    if update_passed and restore_passed:
        print("Phase 8.9 CRM update_customer Live Verification: SUCCESSFUL")
        print("-" * 80)
        print(f"- Integration    : execution_service -> IntegrationRegistry -> CRMAdapter")
        print(f"- CRM Type       : Local Mock CRM (no external CRM connection)")
        print(f"- Test Customer  : {TEST_IDENTIFIER} ({TEST_CUSTOMER_ID})")
        print(f"- Fields Updated : status, notes")
        print(f"- Allowed Fields : {sorted(ALLOWED_UPDATE_FIELDS)}")
        print(f"- Immutable OK   : customer_id, customer_identifier, email, name, company")
        print(f"- Test Restored  : YES - customer returned to seed state")
        print(f"- No credentials : No API keys, OAuth tokens, or secrets required")
        print("=" * 80)
    else:
        failures = []
        if not update_passed:
            failures.append("Update test FAILED")
        if not restore_passed:
            failures.append("Restore test FAILED")
        print("Phase 8.9 CRM update_customer Live Verification: FAILED")
        for f in failures:
            print(f"  - {f}")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
