"""
WorkFlowOS - Phase 8.8: Local Mock CRM find_customer Verification Script
=========================================================================
Performs a controlled live verification of the CRM find_customer integration:
    execution_service -> IntegrationRegistry -> CRMAdapter -> MockCRM (MongoDB)

Verification Flow:
1. Ensures deterministic seed data exists in the mock_crm_customers collection.
2. Creates or reuses an approved CRM find_customer verification workflow.
3. Executes find_customer LIVE with a known synthetic customer identifier.
4. Verifies execution completed, step completed, customerFound=True.
5. Verifies the expected synthetic customer ID is returned.
6. Executes find_customer LIVE with an unknown identifier.
7. Verifies execution completes safely with customerFound=False.

Security Constraints:
- Local mock CRM ONLY. No external CRM connections.
- No real credentials, API keys, or OAuth tokens required.
- Only synthetic .test-domain identifiers used.
- No real personal information printed.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.database.mongodb import get_database
from app.models.mock_crm import ensure_seed_data, SEED_CUSTOMERS
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
# Known test identifiers
# ---------------------------------------------------------------------------
KNOWN_IDENTIFIER = "nav@example.test"      # CUST-1004 - Test Customer
EXPECTED_CUSTOMER_ID = "CUST-1004"
UNKNOWN_IDENTIFIER = "nobody@nosuchplace.test"


def find_or_create_approved_crm_workflow() -> WorkflowDefinition:
    """
    Find an existing approved CRM find_customer workflow or create one.
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
                and wf.steps[0].action.strip().lower() == "find_customer"
            ):
                return wf
        except Exception:
            continue

    # Create and approve a new workflow
    wf_id = f"wf-crm-fc-{uuid.uuid4().hex[:8]}"
    wf = WorkflowDefinition(
        workflow_id=wf_id,
        understanding_id=f"und-{wf_id}",
        name="CRM Find Customer Verification Workflow",
        description="Phase 8.8 live verification workflow for CRM find_customer",
        status="approved",
        reviewed_by="developer_verification",
        reviewer_notes="Approved for Phase 8.8 live CRM find_customer read-only verification",
        approved_at=datetime.now(timezone.utc),
        trigger=WorkflowTrigger(
            application="CRM",
            event="customer_lookup_requested",
            description="Triggered to look up a customer record by identifier",
        ),
        steps=[
            WorkflowStep(
                step_id=f"step-{uuid.uuid4().hex[:8]}",
                order=1,
                application="CRM",
                action="find_customer",
                description="Find customer by identifier in local mock CRM",
                inputs=["customerIdentifier"],
                outputs=["customerFound", "customerId", "customerIdentifier", "name", "company", "status"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="CRM",
                purpose="Customer lookup",
                required_capabilities=["find_customer"],
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


def verify_known_customer(wf: WorkflowDefinition) -> bool:
    """
    Execute find_customer with a KNOWN identifier and verify the result.
    Returns True if verification passed.
    """
    print(f"\n[TEST 1] Executing CRM find_customer with KNOWN identifier: '{KNOWN_IDENTIFIER}'")

    try:
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": KNOWN_IDENTIFIER},
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

    # Verify result_summary contains expected customer ID
    if EXPECTED_CUSTOMER_ID not in step_rec.result_summary:
        print(f"[FAILED] Expected customer ID '{EXPECTED_CUSTOMER_ID}' not in result summary.")
        return False

    print(f"[PASS] Known customer '{EXPECTED_CUSTOMER_ID}' found and verified in result.")
    return True


def verify_unknown_customer(wf: WorkflowDefinition) -> bool:
    """
    Execute find_customer with an UNKNOWN identifier and verify safe not-found response.
    Returns True if verification passed.
    """
    print(f"\n[TEST 2] Executing CRM find_customer with UNKNOWN identifier: '{UNKNOWN_IDENTIFIER}'")

    try:
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": UNKNOWN_IDENTIFIER},
        )
    except Exception as exc:
        print(f"[FAILED] Live execution raised exception: {exc}")
        return False

    print(f"  Execution ID     : {execution.execution_id}")
    print(f"  Execution Status : {execution.status}")
    print(f"  Completed Steps  : {execution.completed_steps} / {len(execution.step_records)}")

    if execution.status != ExecutionStatus.COMPLETED:
        print(f"[FAILED] Execution did not complete. Status: {execution.status}")
        return False

    step_rec = execution.step_records[0]
    print(f"  Step Status      : {step_rec.status}")
    print(f"  Result Summary   : {step_rec.result_summary}")

    if step_rec.status != ExecutionStepStatus.COMPLETED:
        print(f"[FAILED] Step did not complete for unknown identifier. Status: {step_rec.status}")
        return False

    if "no customer found" not in step_rec.result_summary.lower():
        print(f"[FAILED] Expected 'no customer found' in result summary for unknown identifier.")
        return False

    print("[PASS] Unknown identifier handled safely with 'no customer found' response.")
    return True


def main() -> None:
    print("=" * 80)
    print("WorkFlowOS Phase 8.8: Local Mock CRM find_customer Verification")
    print("=" * 80)

    # 1. Ensure seed data
    print("\n[STEP 1] Seeding mock CRM deterministic test customers...")
    try:
        upserted = ensure_seed_data()
        print(f"[OK] Mock CRM seed: {upserted} new record(s) inserted ({len(SEED_CUSTOMERS)} total seed customers).")
    except Exception as exc:
        print(f"[FAILED] Could not seed mock CRM: {exc}")
        sys.exit(1)

    # 2. Workflow setup
    print("\n[STEP 2] Preparing approved CRM find_customer workflow...")
    try:
        wf = find_or_create_approved_crm_workflow()
    except Exception as exc:
        print(f"[FAILED] Could not create/find workflow: {exc}")
        sys.exit(1)

    print(f"[OK] Workflow Name   : {wf.name}")
    print(f"[OK] Workflow ID     : {wf.workflow_id}")
    print(f"[OK] Workflow Status : {wf.status}")
    print(f"[OK] Step 1 Target   : {wf.steps[0].application} / {wf.steps[0].action}")

    # 3. Test 1 - Known customer
    test1_passed = verify_known_customer(wf)

    # 4. Test 2 - Unknown customer
    test2_passed = verify_unknown_customer(wf)

    # 5. Summary
    print("\n" + "=" * 80)
    if test1_passed and test2_passed:
        print("Phase 8.8 CRM find_customer Live Verification: SUCCESSFUL")
        print("-" * 80)
        print(f"- Integration     : execution_service -> IntegrationRegistry -> CRMAdapter")
        print(f"- CRM Type        : Local Mock CRM (no external CRM connection)")
        print(f"- Known Customer  : {KNOWN_IDENTIFIER} -> {EXPECTED_CUSTOMER_ID} [FOUND]")
        print(f"- Unknown Customer: {UNKNOWN_IDENTIFIER} -> [NOT FOUND - safe]")
        print(f"- Seed Customers  : {len(SEED_CUSTOMERS)} deterministic records")
        print(f"- No credentials  : No API keys, OAuth tokens, or secrets required")
        print("=" * 80)
    else:
        failures = []
        if not test1_passed:
            failures.append("Test 1 (known customer lookup) FAILED")
        if not test2_passed:
            failures.append("Test 2 (unknown customer lookup) FAILED")
        print("Phase 8.8 CRM find_customer Live Verification: FAILED")
        for f in failures:
            print(f"  - {f}")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
