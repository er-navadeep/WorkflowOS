"""
Phase 8.1 Tests — Safe Execution Foundation & Audit Records
===========================================================
Comprehensive unit and integration tests covering all requirements A through M:

    A. Create execution for approved workflow
    B. Generated workflow cannot execute
    C. Rejected workflow cannot execute
    D. Missing workflow fails safely
    E. Invalid workflow fails safely
    F. Execution record persists
    G. Execution status transitions work
    H. Step status updates work
    I. Dry run does not call external services
    J. Dry run records simulated steps
    K. GET execution works
    L. Secrets are not exposed
    M. Approved workflow passes execution guard

Run with:
    .venv\\Scripts\\python -m pytest tests/test_phase8_execution_foundation.py -v
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure 'app' resolves from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.api.executions import router as executions_router
from app.models.execution import (
    ExecutionConflictError as DbExecutionConflictError,
    ExecutionNotFoundError as DbExecutionNotFoundError,
    ExecutionStorageError,
    get_execution_by_id,
    get_execution_by_idempotency_key,
    insert_execution,
    list_executions,
    save_execution,
    update_execution_status,
)
from app.schemas.execution import (
    DryRunExecutionRequest,
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepRecord,
    ExecutionStepStatus,
    WorkflowExecution,
    WorkflowExecutionResponse,
)
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.execution_service import (
    ExecutionConflictError,
    ExecutionNotFoundError,
    ExecutionServiceError,
    WorkflowInvalidError,
    WorkflowNotApprovedError,
    WorkflowNotFoundError,
    create_execution_record,
    execute_dry_run,
    get_execution,
    list_executions_for_workflow,
    update_status,
    validate_workflow_for_execution,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

def _make_workflow(
    workflow_id: str = "wf-exec-test-001",
    status: str = "approved",
    **overrides: Any,
) -> WorkflowDefinition:
    """Construct a minimal valid WorkflowDefinition."""
    defaults: Dict[str, Any] = {
        "workflow_id": workflow_id,
        "understanding_id": "und-exec-001",
        "name": "Customer Support Automation",
        "description": "Process incoming support ticket and notify Slack",
        "status": status,
        "trigger": WorkflowTrigger(
            application="Gmail",
            event="New incoming customer email",
            description="Triggered when a new customer email arrives in Gmail.",
        ),
        "steps": [
            WorkflowStep(
                step_id="step-001",
                order=1,
                application="Gmail",
                action="read_email",
                description="Read incoming email",
            ),
            WorkflowStep(
                step_id="step-002",
                order=2,
                application="CRM",
                action="find_customer",
                description="Look up customer record",
            ),
            WorkflowStep(
                step_id="step-003",
                order=3,
                application="Slack",
                action="post_notification",
                description="Notify support channel",
            ),
        ],
        "integrations": [
            WorkflowIntegration(
                application="Gmail",
                purpose="Email trigger and reading",
                required_capabilities=["read_email"],
            ),
            WorkflowIntegration(
                application="CRM",
                purpose="Customer lookup",
                required_capabilities=["find_customer"],
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
# 1. Approval Guard & Validation Tests (Requirements A, B, C, D, E, M)
# ---------------------------------------------------------------------------

class TestApprovalGuardAndValidation:
    """Tests for critical execution approval guards and structural validation."""

    def test_approved_workflow_passes_execution_guard(self):
        """Requirements A & M: Approved workflow passes guard successfully."""
        wf = _make_workflow(status="approved")
        validated = validate_workflow_for_execution(wf, wf.workflow_id)
        assert validated.workflow_id == wf.workflow_id
        assert validated.status == "approved"

    def test_generated_workflow_cannot_execute(self):
        """Requirement B: Workflow with status 'generated' cannot execute (raises 409)."""
        wf = _make_workflow(status="generated")
        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 409
        assert "current status is 'generated'" in exc_info.value.message
        assert "Only 'approved' workflows may be executed" in exc_info.value.message

    def test_rejected_workflow_cannot_execute(self):
        """Requirement C: Workflow with status 'rejected' cannot execute (raises 409)."""
        wf = _make_workflow(status="rejected")
        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 409
        assert "current status is 'rejected'" in exc_info.value.message
        assert "Only 'approved' workflows may be executed" in exc_info.value.message

    def test_missing_workflow_fails_safely(self):
        """Requirement D: Missing workflow (None) fails safely (raises 404)."""
        with pytest.raises(WorkflowNotFoundError) as exc_info:
            validate_workflow_for_execution(None, "wf-non-existent")
        assert exc_info.value.status_code == 404
        assert "Workflow 'wf-non-existent' not found." in exc_info.value.message

    def test_invalid_workflow_empty_workflow_id(self):
        """Requirement E: Empty or blank workflow_id fails safely (raises 422)."""
        wf = _make_workflow(workflow_id="   ")
        with pytest.raises(WorkflowInvalidError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 422
        assert "empty or invalid workflow_id" in exc_info.value.message

    def test_invalid_workflow_no_steps(self):
        """Requirement E: Workflow with empty steps list fails safely (raises 422)."""
        wf = _make_workflow(steps=[])
        with pytest.raises(WorkflowInvalidError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 422
        assert "has no steps to execute" in exc_info.value.message

    def test_invalid_workflow_non_contiguous_step_ordering(self):
        """Requirement E: Workflow with non-contiguous step orders (e.g. 1, 3) fails safely (raises 422)."""
        steps = [
            WorkflowStep(step_id="s1", order=1, application="Gmail", action="read_email", description="d1"),
            WorkflowStep(step_id="s2", order=3, application="Slack", action="post_notification", description="d2"),
        ]
        wf = _make_workflow(steps=steps)
        with pytest.raises(WorkflowInvalidError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 422
        assert "invalid step ordering" in exc_info.value.message

    def test_invalid_workflow_missing_step_identifiers(self):
        """Requirement E: Steps missing application or action fail safely (raises 422)."""
        steps = [
            WorkflowStep(step_id="s1", order=1, application="", action="read_email", description="d1"),
        ]
        wf = _make_workflow(steps=steps)
        with pytest.raises(WorkflowInvalidError) as exc_info:
            validate_workflow_for_execution(wf, wf.workflow_id)
        assert exc_info.value.status_code == 422
        assert "missing application declaration" in exc_info.value.message


# ---------------------------------------------------------------------------
# 2. Execution Record Model & Persistence (Requirements F, G, H)
# ---------------------------------------------------------------------------

class TestExecutionModelAndPersistence:
    """Tests for execution persistence, status updates, and step records."""

    def test_create_and_insert_execution_record(self):
        """Requirements A & F: Create execution record and persist to storage."""
        wf = _make_workflow(status="approved")
        now = datetime.now(timezone.utc)
        exec_record = WorkflowExecution(
            workflow_id=wf.workflow_id,
            workflow_name=wf.name,
            status=ExecutionStatus.PENDING,
            mode=ExecutionMode.DRY_RUN,
            total_steps=len(wf.steps),
            completed_steps=0,
            created_at=now,
        )

        with patch("app.models.execution._get_collection") as mock_col_fn:
            mock_col = MagicMock()
            mock_col_fn.return_value = mock_col
            inserted_id = insert_execution(exec_record)

            assert inserted_id == exec_record.execution_id
            mock_col.insert_one.assert_called_once()
            call_arg = mock_col.insert_one.call_args[0][0]
            assert call_arg["execution_id"] == exec_record.execution_id
            assert call_arg["workflow_id"] == wf.workflow_id
            assert call_arg["status"] == "pending"

    def test_execution_status_transitions(self):
        """Requirement G: Execution status transitions work properly."""
        exec_id = "exec-test-status-001"
        now = datetime.now(timezone.utc)

        with patch("app.models.execution._get_collection") as mock_col_fn:
            mock_col = MagicMock()
            mock_col_fn.return_value = mock_col
            mock_col.update_one.return_value.matched_count = 1
            mock_col.find_one.return_value = {
                "execution_id": exec_id,
                "workflow_id": "wf-001",
                "status": "running",
                "mode": "dry_run",
                "current_step": 1,
                "total_steps": 3,
                "completed_steps": 0,
                "started_at": now,
                "created_at": now,
            }

            updated = update_execution_status(
                execution_id=exec_id,
                status=ExecutionStatus.RUNNING,
                current_step=1,
                started_at=now,
            )

            assert updated.status == ExecutionStatus.RUNNING
            assert updated.current_step == 1
            assert updated.started_at == now

    def test_step_status_updates(self):
        """Requirement H: Step status updates and step records work as expected."""
        now = datetime.now(timezone.utc)
        step_rec = ExecutionStepRecord(
            step_id="step-001",
            order=1,
            application="Gmail",
            action="read_email",
            status=ExecutionStepStatus.DRY_RUN,
            started_at=now,
            completed_at=now,
            result_summary="DRY RUN — Simulating Gmail / read_email. No external action performed.",
        )

        assert step_rec.status == ExecutionStepStatus.DRY_RUN
        assert step_rec.order == 1
        assert "No external action performed" in step_rec.result_summary

    def test_save_execution_updates_timestamp(self):
        """Requirement F: save_execution updates updated_at and persists."""
        wf = _make_workflow(status="approved")
        exec_record = WorkflowExecution(
            workflow_id=wf.workflow_id,
            status=ExecutionStatus.RUNNING,
        )

        with patch("app.models.execution._get_collection") as mock_col_fn:
            mock_col = MagicMock()
            mock_col_fn.return_value = mock_col
            mock_col.replace_one.return_value.matched_count = 1

            saved = save_execution(exec_record)
            assert saved.updated_at is not None
            mock_col.replace_one.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Dry-Run Engine Tests (Requirements I, J)
# ---------------------------------------------------------------------------

class TestDryRunEngine:
    """Tests for safe dry-run simulation engine."""

    def test_dry_run_does_not_call_external_services(self):
        """Requirement I: Dry run does NOT call Gmail, Slack, CRM, or any external service."""
        wf = _make_workflow(status="approved")

        # Mock database calls
        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x), \
             patch("urllib.request.urlopen") as mock_urlopen, \
             patch("smtplib.SMTP") as mock_smtp:

            result = execute_dry_run(wf.workflow_id)

            # Assert no network / mail calls
            mock_urlopen.assert_not_called()
            mock_smtp.assert_not_called()
            assert result.status == ExecutionStatus.COMPLETED

    def test_dry_run_records_simulated_steps(self):
        """Requirement J: Dry run records simulated step records for every workflow step."""
        wf = _make_workflow(status="approved")

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x):

            result = execute_dry_run(wf.workflow_id)

            assert result.status == ExecutionStatus.COMPLETED
            assert result.completed_steps == len(wf.steps)
            assert result.total_steps == len(wf.steps)
            assert result.current_step is None
            assert result.completed_at is not None
            assert len(result.step_records) == 3

            # Verify step 1
            s1 = result.step_records[0]
            assert s1.order == 1
            assert s1.application == "Gmail"
            assert s1.action == "read_email"
            assert s1.status == ExecutionStepStatus.DRY_RUN
            assert "DRY RUN — Simulating Gmail / read_email" in s1.result_summary

            # Verify step 2
            s2 = result.step_records[1]
            assert s2.order == 2
            assert s2.application == "CRM"
            assert s2.action == "find_customer"
            assert s2.status == ExecutionStepStatus.DRY_RUN
            assert "DRY RUN — Simulating CRM / find_customer" in s2.result_summary

            # Verify step 3
            s3 = result.step_records[2]
            assert s3.order == 3
            assert s3.application == "Slack"
            assert s3.action == "post_notification"
            assert s3.status == ExecutionStepStatus.DRY_RUN
            assert "DRY RUN — Simulating Slack / post_notification" in s3.result_summary

    def test_dry_run_idempotency(self):
        """Requirement J & Idempotency: Duplicate call with idempotency_key returns cached record."""
        wf = _make_workflow(status="approved")
        existing_exec = WorkflowExecution(
            execution_id="exec-existing-001",
            workflow_id=wf.workflow_id,
            status=ExecutionStatus.COMPLETED,
            idempotency_key="idem-key-123",
        )

        with patch(
            "app.services.execution_service.db_get_execution_by_idempotency_key",
            return_value=existing_exec,
        ), patch(
            "app.services.execution_service.db_get_workflow_by_id"
        ) as mock_get_wf:

            result = execute_dry_run(
                workflow_id=wf.workflow_id,
                idempotency_key="idem-key-123",
            )

            assert result.execution_id == "exec-existing-001"
            # Did not even need to re-query workflow
            mock_get_wf.assert_not_called()


# ---------------------------------------------------------------------------
# 4. API Endpoint Tests (Requirements K, L, M)
# ---------------------------------------------------------------------------

class TestExecutionAPI:
    """Tests for FastAPI execution endpoints."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        test_app = FastAPI()
        test_app.include_router(executions_router, prefix="/api/v1")
        self.client = TestClient(test_app, raise_server_exceptions=False)

    def test_dry_run_endpoint_approved_workflow_returns_200(self):
        """Requirement A & M: POST /dry-run/{workflow_id} succeeds for approved workflow."""
        wf = _make_workflow(status="approved")
        mock_exec = WorkflowExecution(
            execution_id="exec-api-001",
            workflow_id=wf.workflow_id,
            status=ExecutionStatus.COMPLETED,
            mode=ExecutionMode.DRY_RUN,
            total_steps=len(wf.steps),
            completed_steps=len(wf.steps),
        )

        with patch("app.api.executions.execute_dry_run", return_value=mock_exec):
            resp = self.client.post(f"/api/v1/executions/dry-run/{wf.workflow_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["execution_id"] == "exec-api-001"
        assert data["status"] == "completed"
        assert data["execution"]["workflow_id"] == wf.workflow_id

    def test_dry_run_endpoint_generated_workflow_returns_409(self):
        """Requirement B: POST /dry-run/{workflow_id} returns 409 for 'generated' workflow."""
        with patch(
            "app.api.executions.execute_dry_run",
            side_effect=WorkflowNotApprovedError("wf-gen", "generated"),
        ):
            resp = self.client.post("/api/v1/executions/dry-run/wf-gen")

        assert resp.status_code == 409
        data = resp.json()
        assert data["detail"]["error"] == "invalid_execution_state"
        assert "generated" in data["detail"]["message"]

    def test_dry_run_endpoint_rejected_workflow_returns_409(self):
        """Requirement C: POST /dry-run/{workflow_id} returns 409 for 'rejected' workflow."""
        with patch(
            "app.api.executions.execute_dry_run",
            side_effect=WorkflowNotApprovedError("wf-rej", "rejected"),
        ):
            resp = self.client.post("/api/v1/executions/dry-run/wf-rej")

        assert resp.status_code == 409
        data = resp.json()
        assert data["detail"]["error"] == "invalid_execution_state"
        assert "rejected" in data["detail"]["message"]

    def test_dry_run_endpoint_missing_workflow_returns_404(self):
        """Requirement D: POST /dry-run/{workflow_id} returns 404 for missing workflow."""
        with patch(
            "app.api.executions.execute_dry_run",
            side_effect=WorkflowNotFoundError("wf-missing"),
        ):
            resp = self.client.post("/api/v1/executions/dry-run/wf-missing")

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"] == "not_found"

    def test_dry_run_endpoint_invalid_workflow_returns_422(self):
        """Requirement E: POST /dry-run/{workflow_id} returns 422 for structurally invalid workflow."""
        with patch(
            "app.api.executions.execute_dry_run",
            side_effect=WorkflowInvalidError("Workflow has no steps"),
        ):
            resp = self.client.post("/api/v1/executions/dry-run/wf-nosteps")

        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["error"] == "validation_error"

    def test_get_execution_returns_200(self):
        """Requirement K: GET /executions/{execution_id} returns persisted execution."""
        mock_exec = WorkflowExecution(
            execution_id="exec-get-001",
            workflow_id="wf-001",
            status=ExecutionStatus.COMPLETED,
            mode=ExecutionMode.DRY_RUN,
        )

        with patch("app.api.executions.get_execution", return_value=mock_exec):
            resp = self.client.get("/api/v1/executions/exec-get-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_id"] == "exec-get-001"
        assert data["status"] == "completed"

    def test_get_execution_missing_returns_404(self):
        """Requirement K: GET /executions/{execution_id} returns 404 if not found."""
        with patch(
            "app.api.executions.get_execution",
            side_effect=ExecutionNotFoundError("exec-not-found"),
        ):
            resp = self.client.get("/api/v1/executions/exec-not-found")

        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"] == "not_found"

    def test_list_executions_returns_200(self):
        """GET /executions returns list of executions."""
        mock_execs = [
            WorkflowExecution(execution_id="exec-1", workflow_id="wf-1", status=ExecutionStatus.COMPLETED),
            WorkflowExecution(execution_id="exec-2", workflow_id="wf-1", status=ExecutionStatus.RUNNING),
        ]

        with patch("app.api.executions.list_executions_for_workflow", return_value=mock_execs):
            resp = self.client.get("/api/v1/executions?workflow_id=wf-1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["execution_id"] == "exec-1"
        assert data[1]["execution_id"] == "exec-2"


# ---------------------------------------------------------------------------
# 5. Security Tests (Requirement L)
# ---------------------------------------------------------------------------

class TestSecurityProtections:
    """Requirement L: Verify no secrets, credentials, or tokens are exposed."""

    def test_execution_schemas_never_contain_secrets(self):
        """Requirement L: Schemas do not have token, password, or secret fields."""
        exec_fields = WorkflowExecution.model_fields.keys()
        step_fields = ExecutionStepRecord.model_fields.keys()

        prohibited = ["password", "token", "secret", "api_key", "auth", "credential", "cookie"]
        for field in exec_fields:
            for bad in prohibited:
                assert bad not in field.lower(), f"Prohibited word '{bad}' found in field '{field}'"

        for field in step_fields:
            for bad in prohibited:
                assert bad not in field.lower(), f"Prohibited word '{bad}' found in step field '{field}'"

    def test_execution_api_response_does_not_leak_environment_secrets(self):
        """Requirement L: API response text contains no env variables or secrets."""
        test_app = FastAPI()
        test_app.include_router(executions_router, prefix="/api/v1")
        client = TestClient(test_app, raise_server_exceptions=False)

        wf = _make_workflow(status="approved")
        mock_exec = WorkflowExecution(
            execution_id="exec-sec-001",
            workflow_id=wf.workflow_id,
            status=ExecutionStatus.COMPLETED,
            mode=ExecutionMode.DRY_RUN,
            step_records=[
                ExecutionStepRecord(
                    step_id="step-1",
                    order=1,
                    application="Gmail",
                    action="read_email",
                    status=ExecutionStepStatus.DRY_RUN,
                    result_summary="DRY RUN — Simulating Gmail / read_email. No external action performed.",
                )
            ]
        )

        with patch("app.api.executions.execute_dry_run", return_value=mock_exec):
            resp = client.post(f"/api/v1/executions/dry-run/{wf.workflow_id}")

        text = resp.text
        # Ensure common sensitive env keys/patterns are absent
        for key in ["MONGODB_URI", "GEMINI_API_KEY", "SECRET_KEY", "PRIVATE_KEY"]:
            assert key not in text
