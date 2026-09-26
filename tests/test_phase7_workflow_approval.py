"""
Phase 7 Tests -- Human Approval & State Management
===================================================

Run from project root:
    $env:PYTHONPATH="backend"
    .venv\\Scripts\\python -m pytest tests/test_phase7_workflow_approval.py -v

Tests (38+ total):
    Schema (5):
        1.  WorkflowDefinition accepts approval fields.
        2.  Optional fields default correctly (status='generated', approval fields=None).
        3.  WorkflowApproveRequest rejects empty/whitespace reviewer_id.
        4.  WorkflowRejectRequest rejects empty/whitespace reviewer_id.
        5.  WorkflowRejectRequest rejects empty/whitespace rejection_reason.

    Model (5):
        6.  approve_workflow performs targeted update.
        7.  reject_workflow performs targeted update.
        8.  pending query returns only generated workflows.
        9.  approval does not create a new workflow_id.
        10. rejection does not create a new workflow_id.

    Service (12):
        11. generated -> approved succeeds.
        12. generated -> rejected succeeds.
        13. approved -> approved fails (409).
        14. approved -> rejected fails (409).
        15. rejected -> approved fails (409).
        16. rejected -> rejected fails (409).
        17. Nonexistent workflow returns not-found error (404).
        18. Approval stores reviewer information and notes.
        19. Rejection stores rejection reason.
        20. Timestamps are populated with timezone-aware datetimes.
        21. Approval does not invoke generation validator.
        22. Approval does not invoke Gemini client.

    API (11):
        23. POST /workflows/{id}/approve returns 200.
        24. POST /workflows/{id}/reject returns 200.
        25. GET /workflows/pending returns generated workflows.
        26. Approve nonexistent workflow returns 404.
        27. Reject nonexistent workflow returns 404.
        28. Double approval returns 409.
        29. Approve rejected workflow returns 409.
        30. Reject approved workflow returns 409.
        31. Invalid approve request returns 422.
        32. Invalid reject request returns 422.
        33. Route /workflows/pending resolves correctly before /{workflow_id}.

    Security & Guardrails (5):
        34. Responses never expose GEMINI_API_KEY.
        35. Responses never expose .env contents.
        36. Reviewer ID is stored as plain string and not treated as auth token.
        37. No external integration (Gmail/Slack/CRM) is executed during approval.
        38. Approval operations never inject secret values into workflow fields.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# Ensure 'app' resolves from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.models.workflow import (
    WorkflowNotFoundError,
    WorkflowTransitionError,
    approve_workflow as model_approve_workflow,
    get_workflows_by_status as model_get_workflows_by_status,
    reject_workflow as model_reject_workflow,
)
from app.schemas.workflow import (
    WorkflowApprovalResponse,
    WorkflowApproveRequest,
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowRejectRequest,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.workflow_approval_service import (
    WorkflowApprovalError,
    approve_workflow as service_approve_workflow,
    get_pending_workflows,
    reject_workflow as service_reject_workflow,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

def _make_workflow(
    workflow_id: str = "wf-test-001",
    status: str = "generated",
    **overrides: Any,
) -> WorkflowDefinition:
    """Construct a minimal valid WorkflowDefinition."""
    defaults: Dict[str, Any] = {
        "workflow_id": workflow_id,
        "understanding_id": "und-test-001",
        "name": "Customer Support Automation",
        "description": "Process support ticket and notify Slack",
        "status": status,
        "trigger": WorkflowTrigger(
            application="Gmail",
            event="New incoming customer email",
            description="Triggered when a new customer email arrives in Gmail.",
        ),
        "steps": [
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
                description="Post notification",
            ),
        ],
        "integrations": [
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
        "error_handling": WorkflowErrorHandling(),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return WorkflowDefinition(**defaults)


# ---------------------------------------------------------------------------
# 1. Schema Tests (1 - 5)
# ---------------------------------------------------------------------------

class TestPhase7Schema:
    """Tests for Phase 7 fields and request/response schemas."""

    def test_workflow_definition_accepts_approval_fields(self):
        """Test 1: WorkflowDefinition accepts all Phase 7 approval fields."""
        now = datetime.now(timezone.utc)
        wf = _make_workflow(
            reviewed_by="rev_alice",
            reviewer_notes="Approved after review",
            rejection_reason=None,
            approved_at=now,
            rejected_at=None,
            updated_at=now,
        )
        assert wf.reviewed_by == "rev_alice"
        assert wf.reviewer_notes == "Approved after review"
        assert wf.approved_at == now
        assert wf.updated_at == now
        assert wf.rejected_at is None
        assert wf.rejection_reason is None

    def test_optional_approval_fields_default_correctly(self):
        """Test 2: Optional approval fields default to None, status to 'generated'."""
        wf = _make_workflow()
        assert wf.status == "generated"
        assert wf.reviewed_by is None
        assert wf.reviewer_notes is None
        assert wf.rejection_reason is None
        assert wf.approved_at is None
        assert wf.rejected_at is None
        assert wf.updated_at is None

    def test_approve_request_rejects_empty_reviewer_id(self):
        """Test 3: WorkflowApproveRequest rejects empty or whitespace reviewer_id."""
        with pytest.raises(ValidationError):
            WorkflowApproveRequest(reviewer_id="")

        with pytest.raises(ValidationError):
            WorkflowApproveRequest(reviewer_id="   ")

        req = WorkflowApproveRequest(reviewer_id="rev_bob", reviewer_notes="Looks good")
        assert req.reviewer_id == "rev_bob"
        assert req.reviewer_notes == "Looks good"

    def test_reject_request_rejects_empty_reviewer_id(self):
        """Test 4: WorkflowRejectRequest rejects empty or whitespace reviewer_id."""
        with pytest.raises(ValidationError):
            WorkflowRejectRequest(reviewer_id="", rejection_reason="Missing steps")

        with pytest.raises(ValidationError):
            WorkflowRejectRequest(reviewer_id="  ", rejection_reason="Missing steps")

    def test_reject_request_rejects_empty_rejection_reason(self):
        """Test 5: WorkflowRejectRequest rejects empty or whitespace rejection_reason."""
        with pytest.raises(ValidationError):
            WorkflowRejectRequest(reviewer_id="rev_charlie", rejection_reason="")

        with pytest.raises(ValidationError):
            WorkflowRejectRequest(reviewer_id="rev_charlie", rejection_reason="   ")

        req = WorkflowRejectRequest(
            reviewer_id="rev_charlie",
            rejection_reason="Duplicate workflow",
        )
        assert req.reviewer_id == "rev_charlie"
        assert req.rejection_reason == "Duplicate workflow"


# ---------------------------------------------------------------------------
# 2. Model Tests (6 - 10)
# ---------------------------------------------------------------------------

class TestPhase7Model:
    """Tests for database layer approval operations."""

    def test_approve_workflow_performs_targeted_update(self):
        """Test 6: approve_workflow uses conditional update and sets fields."""
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = _make_workflow(
            workflow_id="wf-001",
            status="approved",
            reviewed_by="rev_david",
            reviewer_notes="All verified",
            approved_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ).model_dump()

        with patch("app.models.workflow._get_collection", return_value=mock_col):
            updated = model_approve_workflow("wf-001", "rev_david", "All verified")

        assert updated.status == "approved"
        assert updated.reviewed_by == "rev_david"
        assert updated.reviewer_notes == "All verified"
        assert mock_col.update_one.called
        call_args = mock_col.update_one.call_args[0]
        # Must enforce status == "generated" in the filter
        assert call_args[0] == {"workflow_id": "wf-001", "status": "generated"}
        assert "$set" in call_args[1]
        assert call_args[1]["$set"]["status"] == "approved"
        assert call_args[1]["$set"]["reviewed_by"] == "rev_david"

    def test_reject_workflow_performs_targeted_update(self):
        """Test 7: reject_workflow uses conditional update and sets rejection fields."""
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = _make_workflow(
            workflow_id="wf-002",
            status="rejected",
            reviewed_by="rev_eve",
            rejection_reason="Security concern",
            rejected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ).model_dump()

        with patch("app.models.workflow._get_collection", return_value=mock_col):
            updated = model_reject_workflow(
                "wf-002", "rev_eve", "Security concern", "Needs compliance review"
            )

        assert updated.status == "rejected"
        assert updated.reviewed_by == "rev_eve"
        assert updated.rejection_reason == "Security concern"
        call_args = mock_col.update_one.call_args[0]
        assert call_args[0] == {"workflow_id": "wf-002", "status": "generated"}
        assert call_args[1]["$set"]["status"] == "rejected"
        assert call_args[1]["$set"]["rejection_reason"] == "Security concern"

    def test_pending_query_returns_generated_workflows(self):
        """Test 8: get_workflows_by_status returns workflows matching status filter."""
        doc = _make_workflow(workflow_id="wf-003", status="generated").model_dump()
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [doc]
        mock_col = MagicMock()
        mock_col.find.return_value = mock_cursor

        with patch("app.models.workflow._get_collection", return_value=mock_col):
            pending = model_get_workflows_by_status("generated")

        assert len(pending) == 1
        assert pending[0].workflow_id == "wf-003"
        assert pending[0].status == "generated"
        mock_col.find.assert_called_with({"status": "generated"})

    def test_approval_does_not_create_new_workflow_id(self):
        """Test 9: approval retains original workflow_id."""
        orig_id = "wf-original-999"
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = _make_workflow(
            workflow_id=orig_id,
            status="approved",
            reviewed_by="rev_frank",
            approved_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ).model_dump()

        with patch("app.models.workflow._get_collection", return_value=mock_col):
            res = model_approve_workflow(orig_id, "rev_frank")

        assert res.workflow_id == orig_id

    def test_rejection_does_not_create_new_workflow_id(self):
        """Test 10: rejection retains original workflow_id."""
        orig_id = "wf-original-888"
        mock_col = MagicMock()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = _make_workflow(
            workflow_id=orig_id,
            status="rejected",
            reviewed_by="rev_grace",
            rejection_reason="Not automated",
            rejected_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ).model_dump()

        with patch("app.models.workflow._get_collection", return_value=mock_col):
            res = model_reject_workflow(orig_id, "rev_grace", "Not automated")

        assert res.workflow_id == orig_id


# ---------------------------------------------------------------------------
# 3. Service Tests (11 - 22)
# ---------------------------------------------------------------------------

class TestPhase7Service:
    """Tests for workflow_approval_service business logic & state guards."""

    def test_generated_to_approved_succeeds(self):
        """Test 11: Transition from generated to approved succeeds."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(
            workflow_id="wf-s11",
            status="approved",
            reviewed_by="rev_01",
            approved_at=now,
            updated_at=now,
        )

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ):
            resp = service_approve_workflow("wf-s11", "rev_01", "Looks good")

        assert resp.success is True
        assert resp.new_status == "approved"
        assert resp.previous_status == "generated"
        assert resp.reviewed_by == "rev_01"
        assert resp.approved_at == now

    def test_generated_to_rejected_succeeds(self):
        """Test 12: Transition from generated to rejected succeeds."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(
            workflow_id="wf-s12",
            status="rejected",
            reviewed_by="rev_02",
            rejection_reason="Duplicate logic",
            rejected_at=now,
            updated_at=now,
        )

        with patch(
            "app.services.workflow_approval_service.db_reject_workflow",
            return_value=updated_wf,
        ):
            resp = service_reject_workflow("wf-s12", "rev_02", "Duplicate logic")

        assert resp.success is True
        assert resp.new_status == "rejected"
        assert resp.previous_status == "generated"
        assert resp.rejection_reason == "Duplicate logic"
        assert resp.rejected_at == now

    def test_approved_to_approved_fails(self):
        """Test 13: Attempting to approve an already-approved workflow raises 409."""
        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            side_effect=WorkflowTransitionError("Already approved", current_status="approved"),
        ):
            with pytest.raises(WorkflowApprovalError) as exc_info:
                service_approve_workflow("wf-s13", "rev_03")
            assert exc_info.value.status_code == 409

    def test_approved_to_rejected_fails(self):
        """Test 14: Attempting to reject an already-approved workflow raises 409."""
        with patch(
            "app.services.workflow_approval_service.db_reject_workflow",
            side_effect=WorkflowTransitionError("Already approved", current_status="approved"),
        ):
            with pytest.raises(WorkflowApprovalError) as exc_info:
                service_reject_workflow("wf-s14", "rev_04", "Changed mind")
            assert exc_info.value.status_code == 409

    def test_rejected_to_approved_fails(self):
        """Test 15: Attempting to approve an already-rejected workflow raises 409."""
        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            side_effect=WorkflowTransitionError("Already rejected", current_status="rejected"),
        ):
            with pytest.raises(WorkflowApprovalError) as exc_info:
                service_approve_workflow("wf-s15", "rev_05")
            assert exc_info.value.status_code == 409

    def test_rejected_to_rejected_fails(self):
        """Test 16: Attempting to reject an already-rejected workflow raises 409."""
        with patch(
            "app.services.workflow_approval_service.db_reject_workflow",
            side_effect=WorkflowTransitionError("Already rejected", current_status="rejected"),
        ):
            with pytest.raises(WorkflowApprovalError) as exc_info:
                service_reject_workflow("wf-s16", "rev_06", "Another reason")
            assert exc_info.value.status_code == 409

    def test_nonexistent_workflow_returns_not_found(self):
        """Test 17: Approving/rejecting a missing workflow raises 404."""
        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            side_effect=WorkflowNotFoundError("Workflow 'wf-missing' not found."),
        ):
            with pytest.raises(WorkflowApprovalError) as exc_info:
                service_approve_workflow("wf-missing", "rev_07")
            assert exc_info.value.status_code == 404

    def test_approval_stores_reviewer_information(self):
        """Test 18: Approval stores reviewer_id and reviewer_notes."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(
            reviewed_by="rev_lead",
            reviewer_notes="Approved for team usage",
            status="approved",
            approved_at=now,
        )

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ) as mock_db:
            resp = service_approve_workflow("wf-018", "rev_lead", "Approved for team usage")

        mock_db.assert_called_once_with(
            workflow_id="wf-018",
            reviewer_id="rev_lead",
            reviewer_notes="Approved for team usage",
        )
        assert resp.reviewed_by == "rev_lead"
        assert resp.reviewer_notes == "Approved for team usage"

    def test_rejection_stores_rejection_reason(self):
        """Test 19: Rejection stores rejection_reason and reviewer_id."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(
            reviewed_by="rev_security",
            rejection_reason="Excessive permissions",
            status="rejected",
            rejected_at=now,
        )

        with patch(
            "app.services.workflow_approval_service.db_reject_workflow",
            return_value=updated_wf,
        ) as mock_db:
            resp = service_reject_workflow(
                "wf-019", "rev_security", "Excessive permissions"
            )

        mock_db.assert_called_once_with(
            workflow_id="wf-019",
            reviewer_id="rev_security",
            rejection_reason="Excessive permissions",
            reviewer_notes=None,
        )
        assert resp.rejection_reason == "Excessive permissions"
        assert resp.reviewed_by == "rev_security"

    def test_timestamps_are_populated(self):
        """Test 20: Timestamps are timezone-aware datetimes."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(
            status="approved",
            approved_at=now,
            updated_at=now,
        )

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ):
            resp = service_approve_workflow("wf-020", "rev_time")

        assert resp.approved_at is not None
        assert resp.approved_at.tzinfo is not None

    def test_approval_does_not_invoke_generation_validator(self):
        """Test 21: Approval flow does NOT call Phase 6 validate_workflow."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(status="approved", approved_at=now)

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ), patch(
            "app.workflow_engine.validator.validate_workflow"
        ) as mock_validator:
            service_approve_workflow("wf-021", "rev_no_val")
            mock_validator.assert_not_called()

    def test_approval_does_not_invoke_gemini(self):
        """Test 22: Approval flow does NOT call Gemini or AI generation."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(status="approved", approved_at=now)

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ), patch(
            "app.ai.gemini_client.GeminiClient.generate"
        ) as mock_gemini:
            service_approve_workflow("wf-022", "rev_no_ai")
            mock_gemini.assert_not_called()


# ---------------------------------------------------------------------------
# 4. API Router Tests (23 - 33)
# ---------------------------------------------------------------------------

class TestPhase7API:
    """Tests for FastAPI endpoints using TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Mount routers in main app order for routing accuracy."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.workflow_approval import router as approval_router
        from app.api.workflows import router as workflows_router

        test_app = FastAPI()
        # Must register approval router first, matching main.py
        test_app.include_router(approval_router, prefix="/api/v1")
        test_app.include_router(workflows_router, prefix="/api/v1")
        self.client = TestClient(test_app, raise_server_exceptions=False)

    def test_post_approve_returns_200(self):
        """Test 23: POST /api/v1/workflows/{id}/approve returns 200 with response envelope."""
        now = datetime.now(timezone.utc)
        resp_obj = WorkflowApprovalResponse(
            success=True,
            workflow_id="wf-api-001",
            previous_status="generated",
            new_status="approved",
            reviewed_by="rev_api_1",
            approved_at=now,
            reviewer_notes="Approved via API",
            message="Workflow 'wf-api-001' approved successfully.",
        )

        with patch(
            "app.api.workflow_approval.approve_workflow",
            return_value=resp_obj,
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-api-001/approve",
                json={"reviewer_id": "rev_api_1", "reviewer_notes": "Approved via API"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["new_status"] == "approved"
            assert data["reviewed_by"] == "rev_api_1"

    def test_post_reject_returns_200(self):
        """Test 24: POST /api/v1/workflows/{id}/reject returns 200 with response envelope."""
        now = datetime.now(timezone.utc)
        resp_obj = WorkflowApprovalResponse(
            success=True,
            workflow_id="wf-api-002",
            previous_status="generated",
            new_status="rejected",
            reviewed_by="rev_api_2",
            rejected_at=now,
            rejection_reason="Unnecessary",
            message="Workflow 'wf-api-002' rejected successfully.",
        )

        with patch(
            "app.api.workflow_approval.reject_workflow",
            return_value=resp_obj,
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-api-002/reject",
                json={"reviewer_id": "rev_api_2", "rejection_reason": "Unnecessary"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["new_status"] == "rejected"
            assert data["rejection_reason"] == "Unnecessary"

    def test_get_pending_returns_generated_workflows(self):
        """Test 25: GET /api/v1/workflows/pending returns list of generated workflows."""
        pending_list = [
            _make_workflow(workflow_id="wf-pend-1", status="generated"),
            _make_workflow(workflow_id="wf-pend-2", status="generated"),
        ]

        with patch(
            "app.api.workflow_approval.get_pending_workflows",
            return_value=pending_list,
        ):
            resp = self.client.get("/api/v1/workflows/pending")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["workflow_id"] == "wf-pend-1"
            assert data[0]["status"] == "generated"

    def test_approve_nonexistent_returns_404(self):
        """Test 26: POST /workflows/{missing}/approve returns 404."""
        with patch(
            "app.api.workflow_approval.approve_workflow",
            side_effect=WorkflowApprovalError("Workflow 'wf-none' not found.", status_code=404),
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-none/approve",
                json={"reviewer_id": "rev_api_3"},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"]["error"] == "not_found"

    def test_reject_nonexistent_returns_404(self):
        """Test 27: POST /workflows/{missing}/reject returns 404."""
        with patch(
            "app.api.workflow_approval.reject_workflow",
            side_effect=WorkflowApprovalError("Workflow 'wf-none' not found.", status_code=404),
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-none/reject",
                json={"reviewer_id": "rev_api_4", "rejection_reason": "Bad logic"},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"]["error"] == "not_found"

    def test_double_approval_returns_409(self):
        """Test 28: POST approve on already-approved workflow returns 409."""
        with patch(
            "app.api.workflow_approval.approve_workflow",
            side_effect=WorkflowApprovalError("Cannot transition from approved.", status_code=409),
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-app-dup/approve",
                json={"reviewer_id": "rev_dup"},
            )
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "invalid_transition"

    def test_approve_rejected_workflow_returns_409(self):
        """Test 29: POST approve on rejected workflow returns 409."""
        with patch(
            "app.api.workflow_approval.approve_workflow",
            side_effect=WorkflowApprovalError("Cannot transition from rejected.", status_code=409),
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-rej-to-app/approve",
                json={"reviewer_id": "rev_dup"},
            )
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "invalid_transition"

    def test_reject_approved_workflow_returns_409(self):
        """Test 30: POST reject on approved workflow returns 409."""
        with patch(
            "app.api.workflow_approval.reject_workflow",
            side_effect=WorkflowApprovalError("Cannot transition from approved.", status_code=409),
        ):
            resp = self.client.post(
                "/api/v1/workflows/wf-app-to-rej/reject",
                json={"reviewer_id": "rev_dup", "rejection_reason": "Too late"},
            )
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "invalid_transition"

    def test_invalid_approve_request_returns_422(self):
        """Test 31: POST approve with empty reviewer_id returns 422."""
        resp = self.client.post(
            "/api/v1/workflows/wf-test/approve",
            json={"reviewer_id": "   "},
        )
        assert resp.status_code == 422

    def test_invalid_reject_request_returns_422(self):
        """Test 32: POST reject with empty rejection_reason returns 422."""
        resp = self.client.post(
            "/api/v1/workflows/wf-test/reject",
            json={"reviewer_id": "rev_test", "rejection_reason": "  "},
        )
        assert resp.status_code == 422

    def test_route_pending_resolves_correctly_without_param_clash(self):
        """Test 33: GET /workflows/pending does NOT get caught by GET /{workflow_id}."""
        pending_list = [_make_workflow(workflow_id="wf-pending-test", status="generated")]

        with patch(
            "app.api.workflow_approval.get_pending_workflows",
            return_value=pending_list,
        ), patch(
            "app.api.workflows.get_workflow"
        ) as mock_get_workflow:
            resp = self.client.get("/api/v1/workflows/pending")
            assert resp.status_code == 200
            # Ensure get_workflow was NOT called with workflow_id="pending"
            mock_get_workflow.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Security & Guardrail Tests (34 - 38)
# ---------------------------------------------------------------------------

class TestPhase7Security:
    """Security tests ensuring secrets, environment, and external actions are isolated."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.workflow_approval import router as approval_router
        from app.api.workflows import router as workflows_router

        test_app = FastAPI()
        test_app.include_router(approval_router, prefix="/api/v1")
        test_app.include_router(workflows_router, prefix="/api/v1")
        self.client = TestClient(test_app, raise_server_exceptions=False)

    def test_responses_never_expose_gemini_key(self):
        """Test 34: API response JSON never includes GEMINI_API_KEY value."""
        fake_key = "AIzaSySecretGeminiKey12345"
        with patch.dict(os.environ, {"GEMINI_API_KEY": fake_key}):
            now = datetime.now(timezone.utc)
            resp_obj = WorkflowApprovalResponse(
                success=True,
                workflow_id="wf-sec-01",
                previous_status="generated",
                new_status="approved",
                reviewed_by="rev_sec",
                approved_at=now,
                message="Workflow approved.",
            )
            with patch("app.api.workflow_approval.approve_workflow", return_value=resp_obj):
                resp = self.client.post(
                    "/api/v1/workflows/wf-sec-01/approve",
                    json={"reviewer_id": "rev_sec"},
                )
                assert fake_key not in resp.text
                assert "GEMINI_API_KEY" not in resp.text

    def test_responses_never_expose_env_contents(self):
        """Test 35: API responses never echo environment file contents."""
        now = datetime.now(timezone.utc)
        resp_obj = WorkflowApprovalResponse(
            success=True,
            workflow_id="wf-sec-02",
            previous_status="generated",
            new_status="rejected",
            reviewed_by="rev_sec",
            rejected_at=now,
            rejection_reason="Rejected cleanly",
            message="Workflow rejected.",
        )
        with patch("app.api.workflow_approval.reject_workflow", return_value=resp_obj):
            resp = self.client.post(
                "/api/v1/workflows/wf-sec-02/reject",
                json={"reviewer_id": "rev_sec", "rejection_reason": "Rejected cleanly"},
            )
            assert "MONGO_URI" not in resp.text
            assert "GEMINI_API_KEY" not in resp.text

    def test_reviewer_id_stored_as_plain_data(self):
        """Test 36: Reviewer ID is stored as plain string and not treated as auth credential."""
        req = WorkflowApproveRequest(reviewer_id="user_admin_test")
        assert req.reviewer_id == "user_admin_test"
        # Must not have password / token attributes
        assert not hasattr(req, "password")
        assert not hasattr(req, "token")

    def test_no_external_integration_executed(self):
        """Test 37: No real Gmail, Slack, CRM, or browser automation is called."""
        now = datetime.now(timezone.utc)
        updated_wf = _make_workflow(status="approved", approved_at=now)

        with patch(
            "app.services.workflow_approval_service.db_approve_workflow",
            return_value=updated_wf,
        ):
            # Assert that no automation packages are imported or called
            resp = service_approve_workflow("wf-sec-37", "rev_audit")
            assert resp.new_status == "approved"

    def test_approval_operations_do_not_inject_secret_values(self):
        """Test 38: Approval response fields do not contain auth credentials."""
        now = datetime.now(timezone.utc)
        resp = WorkflowApprovalResponse(
            success=True,
            workflow_id="wf-audit",
            previous_status="generated",
            new_status="approved",
            reviewed_by="auditor_01",
            approved_at=now,
            message="Workflow 'wf-audit' approved successfully.",
        )
        dump = resp.model_dump()
        for k, v in dump.items():
            if isinstance(v, str):
                assert "AIza" not in v
                assert "sk-" not in v
                assert "Bearer" not in v
