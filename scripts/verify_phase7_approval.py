"""
Phase 7 Live Verification Script
=================================
Performs the required end-to-end verification against real MongoDB and FastAPI app.

Rules:
    - Never log or display GEMINI_API_KEY or .env secrets.
    - No real Gmail, Slack, CRM, or browser automation is called.
    - Verifies atomic status transitions:
        generated -> approved (and blocks re-approval / rejection with 409)
        generated -> rejected (and blocks re-rejection / approval with 409)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.models.workflow import upsert_workflow, get_workflow_by_id
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.workflow_approval_service import (
    WorkflowApprovalError,
    approve_workflow,
    reject_workflow,
    get_pending_workflows,
)


def _create_live_test_workflow(wf_id: str, und_id: str) -> WorkflowDefinition:
    wf = WorkflowDefinition(
        workflow_id=wf_id,
        understanding_id=und_id,
        name=f"Live Verification Workflow {wf_id}",
        description="Phase 7 live verification test definition",
        status="generated",
        trigger=WorkflowTrigger(
            application="Gmail",
            event="New incoming customer email",
            description="Triggered when customer email arrives",
        ),
        steps=[
            WorkflowStep(
                order=1,
                application="Gmail",
                action="read_email",
                description="Read incoming email",
            ),
            WorkflowStep(
                order=2,
                application="Slack",
                action="post_notification",
                description="Post notification to Slack",
            ),
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email trigger",
                required_capabilities=["read_email"],
            ),
            WorkflowIntegration(
                application="Slack",
                purpose="Notifications",
                required_capabilities=["post_notification"],
            ),
        ],
        error_handling=WorkflowErrorHandling(),
        created_at=datetime.now(timezone.utc),
    )
    upsert_workflow(wf)
    return wf


def main() -> None:
    print("=== WorkFlowOS Phase 7: Live End-to-End Verification ===\n")

    client = TestClient(app)

    # -----------------------------------------------------------------------
    # Verification 1: generated -> approved lifecycle & guards
    # -----------------------------------------------------------------------
    print("--- Test Case 1: Approval Lifecycle & Transition Guards ---")
    wf1_id = f"wf-verify-app-{uuid.uuid4().hex[:8]}"
    und1_id = f"und-verify-app-{uuid.uuid4().hex[:8]}"

    wf1 = _create_live_test_workflow(wf1_id, und1_id)
    stored1 = get_workflow_by_id(wf1_id)
    assert stored1 is not None, "Workflow 1 must exist in MongoDB"
    print(f"1. Created workflow '{wf1_id}' in MongoDB.")
    print(f"2. Confirmed initial status = '{stored1.status}'.")
    assert stored1.status == "generated"

    # Verify pending queue sees it
    pending_before = get_pending_workflows()
    assert any(w.workflow_id == wf1_id for w in pending_before), "Must appear in pending list"
    print(f"   Workflow '{wf1_id}' found in GET pending list (count={len(pending_before)}).")

    # 3. Approve it using a test reviewer_id
    reviewer1 = "reviewer_sarah_connor"
    notes1 = "Workflow verified against security checklist."
    resp1 = approve_workflow(wf1_id, reviewer1, notes1)
    print(f"3. Approved via service with reviewer_id='{reviewer1}'.")

    # 4. Confirm status = approved
    assert resp1.new_status == "approved"
    assert resp1.previous_status == "generated"
    stored_approved = get_workflow_by_id(wf1_id)
    assert stored_approved is not None
    assert stored_approved.status == "approved"
    print(f"4. Confirmed status in DB = '{stored_approved.status}'.")

    # 5. Confirm approved_at exists
    assert stored_approved.approved_at is not None
    assert stored_approved.approved_at.tzinfo is not None
    print(f"5. Confirmed approved_at = {stored_approved.approved_at.isoformat()}.")

    # 6. Confirm reviewed_by exists
    assert stored_approved.reviewed_by == reviewer1
    assert stored_approved.reviewer_notes == notes1
    print(f"6. Confirmed reviewed_by = '{stored_approved.reviewed_by}', notes='{stored_approved.reviewer_notes}'.")

    # 7. Confirm workflow_id remains unchanged
    assert stored_approved.workflow_id == wf1_id
    assert stored_approved.understanding_id == und1_id
    print(f"7. Confirmed workflow_id remains unchanged: '{stored_approved.workflow_id}'.")

    # 8. Attempt to approve again -> must return 409
    try:
        approve_workflow(wf1_id, reviewer1)
        raise AssertionError("Double approval should have raised 409!")
    except WorkflowApprovalError as exc:
        assert exc.status_code == 409
        print(f"8. Attempted double approval -> Correctly caught 409: {exc.message}")

    # 9. Attempt to reject it -> must return 409
    try:
        reject_workflow(wf1_id, reviewer1, "Attempting reject after approval")
        raise AssertionError("Rejecting approved workflow should have raised 409!")
    except WorkflowApprovalError as exc:
        assert exc.status_code == 409
        print(f"9. Attempted reject of approved workflow -> Correctly caught 409: {exc.message}")

    print("Test Case 1 Passed!\n")

    # -----------------------------------------------------------------------
    # Verification 2: generated -> rejected lifecycle & guards
    # -----------------------------------------------------------------------
    print("--- Test Case 2: Rejection Lifecycle & Transition Guards ---")
    wf2_id = f"wf-verify-rej-{uuid.uuid4().hex[:8]}"
    und2_id = f"und-verify-rej-{uuid.uuid4().hex[:8]}"

    wf2 = _create_live_test_workflow(wf2_id, und2_id)
    stored2 = get_workflow_by_id(wf2_id)
    assert stored2 is not None
    print(f"1. Created workflow '{wf2_id}' in MongoDB.")
    print(f"   Confirmed initial status = '{stored2.status}'.")
    assert stored2.status == "generated"

    # 2. Reject it with rejection_reason
    reviewer2 = "reviewer_john_anderton"
    reason2 = "Redundant workflow: duplicate of support routing policy v2."
    resp2 = reject_workflow(wf2_id, reviewer2, reason2)
    print(f"2. Rejected via service with reason='{reason2}'.")

    # 3. Confirm status = rejected
    assert resp2.new_status == "rejected"
    stored_rejected = get_workflow_by_id(wf2_id)
    assert stored_rejected is not None
    assert stored_rejected.status == "rejected"
    print(f"3. Confirmed status in DB = '{stored_rejected.status}'.")

    # 4. Confirm rejected_at exists
    assert stored_rejected.rejected_at is not None
    assert stored_rejected.rejected_at.tzinfo is not None
    print(f"4. Confirmed rejected_at = {stored_rejected.rejected_at.isoformat()}.")

    # 5. Confirm rejection_reason exists
    assert stored_rejected.rejection_reason == reason2
    assert stored_rejected.reviewed_by == reviewer2
    print(f"5. Confirmed rejection_reason = '{stored_rejected.rejection_reason}'.")

    # 6. Attempt to approve it -> must return 409
    try:
        approve_workflow(wf2_id, reviewer2)
        raise AssertionError("Approving rejected workflow should have raised 409!")
    except WorkflowApprovalError as exc:
        assert exc.status_code == 409
        print(f"6. Attempted approve of rejected workflow -> Correctly caught 409: {exc.message}")

    # 7. Attempt to reject again -> must return 409
    try:
        reject_workflow(wf2_id, reviewer2, "Second rejection attempt")
        raise AssertionError("Double rejection should have raised 409!")
    except WorkflowApprovalError as exc:
        assert exc.status_code == 409
        print(f"7. Attempted double reject -> Correctly caught 409: {exc.message}")

    print("Test Case 2 Passed!\n")

    # -----------------------------------------------------------------------
    # Verification 3: FastAPI HTTP Endpoints End-to-End
    # -----------------------------------------------------------------------
    print("--- Test Case 3: FastAPI End-to-End HTTP Tests ---")
    wf3_id = f"wf-verify-http-{uuid.uuid4().hex[:8]}"
    und3_id = f"und-verify-http-{uuid.uuid4().hex[:8]}"
    _create_live_test_workflow(wf3_id, und3_id)

    # Test GET /api/v1/workflows/pending (ensuring /pending is not matched as /{workflow_id})
    resp_pend = client.get("/api/v1/workflows/pending")
    assert resp_pend.status_code == 200
    pend_items = resp_pend.json()
    assert isinstance(pend_items, list)
    assert any(item["workflow_id"] == wf3_id for item in pend_items)
    print("1. GET /api/v1/workflows/pending -> 200 OK (route order correct, no path collision).")

    # Test POST /api/v1/workflows/{id}/approve
    resp_app = client.post(
        f"/api/v1/workflows/{wf3_id}/approve",
        json={"reviewer_id": "api_user_99", "reviewer_notes": "Approved over HTTP"},
    )
    assert resp_app.status_code == 200
    data_app = resp_app.json()
    assert data_app["success"] is True
    assert data_app["new_status"] == "approved"
    assert data_app["reviewed_by"] == "api_user_99"
    print("2. POST /api/v1/workflows/{id}/approve -> 200 OK.")

    # Test 409 on second approve over HTTP
    resp_app2 = client.post(
        f"/api/v1/workflows/{wf3_id}/approve",
        json={"reviewer_id": "api_user_99"},
    )
    assert resp_app2.status_code == 409
    print("3. Double POST approve over HTTP -> 409 Conflict.")

    # Test 409 on reject of approved workflow over HTTP
    resp_rej_app = client.post(
        f"/api/v1/workflows/{wf3_id}/reject",
        json={"reviewer_id": "api_user_99", "rejection_reason": "Not allowed"},
    )
    assert resp_rej_app.status_code == 409
    print("4. POST reject of approved workflow over HTTP -> 409 Conflict.")

    # Test 404 on nonexistent workflow
    resp_404 = client.post(
        "/api/v1/workflows/wf-nonexistent-99999/approve",
        json={"reviewer_id": "api_user_99"},
    )
    assert resp_404.status_code == 404
    print("5. POST approve on nonexistent workflow -> 404 Not Found.")

    # Test 422 on empty reviewer_id
    resp_422 = client.post(
        f"/api/v1/workflows/{wf3_id}/approve",
        json={"reviewer_id": "   "},
    )
    assert resp_422.status_code == 422
    print("6. POST approve with empty reviewer_id -> 422 Unprocessable Entity.")

    print("\nAll Live Verification Tests PASSED with 100% Success!")


if __name__ == "__main__":
    main()
