"""
Phase 8.3 Tests — Slack Integration & Live Execution
=====================================================
Tests for SlackAdapter, IntegrationRegistry, Live Execution Engine,
Approval Guardrails, Secret Sanitization, and Idempotency.

All external HTTP calls to Slack are mocked; NO real network calls are made.
"""

from __future__ import annotations

import io
import os
import sys
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure 'app' resolves from backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.integrations.base import (
    BaseIntegrationAdapter,
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.integrations.registry import IntegrationRegistry, get_integration_registry
from app.integrations.slack.adapter import SlackAdapter
from app.main import app
from app.models.workflow import upsert_workflow
from app.schemas.execution import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepRecord,
    ExecutionStepStatus,
    LiveExecutionRequest,
    WorkflowExecution,
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
    WorkflowInvalidError,
    WorkflowNotApprovedError,
    WorkflowNotFoundError,
    execute_dry_run,
    execute_live,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

def _make_slack_workflow(
    workflow_id: str = "wf-slack-test-001",
    status: str = "approved",
    action: str = "send_message",
    application: str = "Slack",
    inputs: Optional[list] = None,
    on_failure: str = "stop",
    **overrides: Any,
) -> WorkflowDefinition:
    """Construct a minimal valid workflow with a Slack step."""
    defaults: Dict[str, Any] = {
        "workflow_id": workflow_id,
        "understanding_id": f"und-{workflow_id}",
        "name": "Slack Notification Workflow",
        "description": "Post alert to Slack channel",
        "status": status,
        "trigger": WorkflowTrigger(
            application="Slack",
            event="New customer notification",
            description="Triggered when customer notification is ready.",
        ),
        "steps": [
            WorkflowStep(
                step_id="step-001",
                order=1,
                application=application,
                action=action,
                description="Send notification message to Slack",
                inputs=inputs if inputs is not None else ["requestNotificationText"],
                on_failure=on_failure,
            ),
        ],
        "integrations": [
            WorkflowIntegration(
                application="Slack",
                purpose="Team alerts",
                required_capabilities=["send_message"],
            ),
        ],
        "error_handling": WorkflowErrorHandling(),
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return WorkflowDefinition(**defaults)


def _mock_slack_response(body: bytes = b"ok", status_code: int = 200) -> MagicMock:
    """Helper to create a mock HTTP response context manager."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.status = status_code
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


# ---------------------------------------------------------------------------
# 1. Slack Adapter Instantiation & Capabilities (Reqs 1, 3, 4)
# ---------------------------------------------------------------------------

class TestSlackAdapterBasics:
    """Tests for basic adapter contract and action handling."""

    def test_slack_adapter_can_be_instantiated(self):
        """Req 1: Slack adapter can be instantiated and exposes correct application_name."""
        adapter = SlackAdapter()
        assert isinstance(adapter, BaseIntegrationAdapter)
        assert adapter.application_name == "Slack"

    def test_slack_adapter_recognizes_send_message(self):
        """Req 3: Slack adapter recognizes 'send_message' action (case-insensitive)."""
        adapter = SlackAdapter()
        assert adapter.can_handle("send_message") is True
        assert adapter.can_handle("  send_message  ") is True
        assert adapter.can_handle("SEND_MESSAGE") is True

    def test_unsupported_slack_action_is_rejected(self):
        """Req 4: Unsupported Slack action is rejected by can_handle and execute."""
        adapter = SlackAdapter()
        assert adapter.can_handle("delete_channel") is False
        assert adapter.can_handle("post_notification") is False
        assert adapter.can_handle("read_channel") is False
        assert adapter.can_handle("") is False

        wf = _make_slack_workflow(action="unsupported_op")
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-001",
            step=wf.steps[0],
            variables={"message": "hello"},
            dry_run=False,
        )
        result = adapter.execute(context)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "unsupported action" in result.error_summary.lower()


# ---------------------------------------------------------------------------
# 2. Configuration & Dry-Run Safety (Reqs 2, 5, 6)
# ---------------------------------------------------------------------------

class TestSlackAdapterConfigAndDryRun:
    """Tests for configuration handling and dry-run execution safety."""

    def test_missing_webhook_configuration_fails_safely(self, monkeypatch):
        """Req 2: Missing webhook configuration fails safely without throwing unhandled errors."""
        monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-002",
            step=wf.steps[0],
            variables={"requestNotificationText": "Test alert"},
            dry_run=False,
        )

        result = adapter.execute(context)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "Missing SLACK_WEBHOOK_URL" in result.error_summary

    def test_dry_run_does_not_make_network_request(self, monkeypatch):
        """Req 5: Dry-run does not make any network request even with webhook configured."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-003",
            step=wf.steps[0],
            variables={"requestNotificationText": "Test alert"},
            dry_run=True,
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = adapter.execute(context)
            mock_urlopen.assert_not_called()

    def test_dry_run_returns_safe_simulated_result(self):
        """Req 6: Dry-run returns safe simulated result and status."""
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-004",
            step=wf.steps[0],
            variables={"requestNotificationText": "Test alert"},
            dry_run=True,
        )

        result = adapter.execute(context)
        assert result.success is True
        assert result.status == ExecutionStepStatus.DRY_RUN
        assert "simulated" in result.result_summary.lower()
        assert result.error_summary is None


# ---------------------------------------------------------------------------
# 3. Live Request Mocking & HTTP Handling (Reqs 7, 8, 9)
# ---------------------------------------------------------------------------

class TestSlackAdapterExecutionHandling:
    """Tests for mocked HTTP requests and response/error handling."""

    def test_live_slack_request_can_be_mocked(self, monkeypatch):
        """Req 7: Live Slack request can be mocked cleanly via urllib.request."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-005",
            step=wf.steps[0],
            variables={"requestNotificationText": "System operational"},
            dry_run=False,
        )

        with patch("urllib.request.urlopen", return_value=_mock_slack_response(b"ok")) as mock_urlopen:
            result = adapter.execute(context)
            assert mock_urlopen.called
            assert result.success is True

    def test_mocked_successful_slack_response_handled_correctly(self, monkeypatch):
        """Req 8: Mocked successful Slack response ('ok') is handled correctly."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-006",
            step=wf.steps[0],
            variables={"requestNotificationText": "Deployment complete"},
            dry_run=False,
        )

        with patch("urllib.request.urlopen", return_value=_mock_slack_response(b"ok")):
            result = adapter.execute(context)

        assert result.success is True
        assert result.status == ExecutionStepStatus.COMPLETED
        assert "successfully" in result.result_summary.lower()
        assert result.outputs.get("slack_delivery") == "delivered"
        assert result.error_summary is None

    def test_mocked_slack_failure_handled_correctly(self, monkeypatch):
        """Req 9: Mocked Slack HTTP error is handled correctly with safe summary."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        adapter = SlackAdapter()
        wf = _make_slack_workflow()
        context = StepExecutionContext(
            workflow_id=wf.workflow_id,
            execution_id="exec-007",
            step=wf.steps[0],
            variables={"requestNotificationText": "Alert"},
            dry_run=False,
        )

        http_err = urllib.error.HTTPError(
            url="https://hooks.slack.com/services/T00/B00/SECRET123",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(b"invalid_payload"),
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            result = adapter.execute(context)

        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "400" in result.error_summary
        assert "failed" in result.result_summary.lower()


# ---------------------------------------------------------------------------
# 4. Approval Guardrails on Live Execution (Reqs 10, 11, 12, 13)
# ---------------------------------------------------------------------------

class TestLiveExecutionApprovalGuard:
    """Tests verifying hard approval guards strictly protect live execution."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_workflow_with_status_generated_cannot_execute_live(self):
        """Req 10: Workflow with status 'generated' cannot execute live (raises 409)."""
        wf = _make_slack_workflow(workflow_id="wf-gen-001", status="generated")
        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf):
            with pytest.raises(WorkflowNotApprovedError) as exc_info:
                execute_live("wf-gen-001")
            assert exc_info.value.status_code == 409
            assert "cannot be executed" in exc_info.value.message

            # Also verify API endpoint returns 409
            resp = self.client.post("/api/v1/executions/live/wf-gen-001")
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "invalid_execution_state"

    def test_workflow_with_status_rejected_cannot_execute_live(self):
        """Req 11: Workflow with status 'rejected' cannot execute live (raises 409)."""
        wf = _make_slack_workflow(workflow_id="wf-rej-001", status="rejected")
        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf):
            with pytest.raises(WorkflowNotApprovedError) as exc_info:
                execute_live("wf-rej-001")
            assert exc_info.value.status_code == 409

            resp = self.client.post("/api/v1/executions/live/wf-rej-001")
            assert resp.status_code == 409
            assert resp.json()["detail"]["error"] == "invalid_execution_state"

    def test_workflow_with_status_approved_can_execute_live(self, monkeypatch):
        """Req 12: Workflow with status 'approved' can execute live successfully."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        wf = _make_slack_workflow(workflow_id="wf-app-001", status="approved")

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution", return_value="exec-008"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x), \
             patch("urllib.request.urlopen", return_value=_mock_slack_response(b"ok")):

            exec_record = execute_live(
                "wf-app-001",
                variables={"requestNotificationText": "Approved run"},
            )

            assert exec_record.status == ExecutionStatus.COMPLETED
            assert exec_record.mode == ExecutionMode.LIVE
            assert exec_record.completed_steps == 1
            assert exec_record.step_records[0].status == ExecutionStepStatus.COMPLETED

    def test_missing_workflow_is_rejected_safely(self):
        """Req 13: Missing workflow raises WorkflowNotFoundError (404)."""
        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=None):
            with pytest.raises(WorkflowNotFoundError):
                execute_live("wf-nonexistent-999")

            resp = self.client.post("/api/v1/executions/live/wf-nonexistent-999")
            assert resp.status_code == 404
            assert resp.json()["detail"]["error"] == "not_found"


# ---------------------------------------------------------------------------
# 5. Unsupported Integrations & Failure Modes (Req 14)
# ---------------------------------------------------------------------------

class TestUnsupportedActionsAndFailureModes:
    """Tests ensuring unsupported actions fail safely without crashing."""

    def test_unsupported_application_action_fails_safely(self):
        """Req 14: Unsupported application/action fails safely with status FAILED.
        Note: update_customer is now supported (Phase 8.9); using delete_customer instead.
        """
        wf = _make_slack_workflow(
            workflow_id="wf-crm-001",
            status="approved",
            application="CRM",
            action="delete_customer",
        )

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution", return_value="exec-009"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x):

            exec_record = execute_live("wf-crm-001")
            assert exec_record.status == ExecutionStatus.FAILED
            assert exec_record.failed_step == 1
            assert len(exec_record.step_records) == 1
            assert exec_record.step_records[0].status == ExecutionStepStatus.FAILED
            assert "unsupported integration action" in exec_record.step_records[0].error_summary.lower()

    def test_missing_input_message_fails_safely_without_inventing_data(self, monkeypatch):
        """Req 4 (Input Handling): Step fails safely if message cannot be resolved."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        wf = _make_slack_workflow(workflow_id="wf-noinput-001", inputs=["unprovidedVariable"])

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution", return_value="exec-010"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x):

            exec_record = execute_live("wf-noinput-001", variables={})
            assert exec_record.status == ExecutionStatus.FAILED
            assert "missing input text" in exec_record.step_records[0].result_summary.lower()


# ---------------------------------------------------------------------------
# 6. Secret Sanitization & Security (Reqs 15, 16)
# ---------------------------------------------------------------------------

class TestSecretSanitization:
    """Tests guaranteeing secrets never leak into execution records or logs."""

    def test_webhook_secret_never_appears_in_execution_record(self, monkeypatch):
        """Req 15: Webhook secret never appears anywhere in the execution record."""
        secret_token = "SECRET_TOKEN_XYZ_987"
        secret_url = f"https://hooks.slack.com/services/T999/B888/{secret_token}"
        monkeypatch.setenv("SLACK_WEBHOOK_URL", secret_url)

        wf = _make_slack_workflow(workflow_id="wf-sec-001", status="approved")

        http_err = urllib.error.HTTPError(
            url=secret_url,
            code=500,
            msg=f"Internal Server Error on {secret_url}",
            hdrs={},
            fp=io.BytesIO(f"server crash: {secret_url}".encode()),
        )

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution", return_value="exec-011"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x), \
             patch("urllib.request.urlopen", side_effect=http_err):

            exec_record = execute_live(
                "wf-sec-001",
                variables={"requestNotificationText": "Secure message"},
            )

            # Dump whole execution record to string to assert no secret leakage
            dumped_str = exec_record.model_dump_json()
            assert secret_token not in dumped_str
            assert secret_url not in dumped_str
            assert "[REDACTED_WEBHOOK_URL]" in dumped_str

    def test_webhook_secret_never_appears_in_error_summary(self, monkeypatch):
        """Req 16: Webhook secret never appears in error_summary."""
        secret_token = "ULTRA_CONFIDENTIAL_TOKEN_123"
        secret_url = f"https://hooks.slack.com/services/T11/B22/{secret_token}"
        monkeypatch.setenv("SLACK_WEBHOOK_URL", secret_url)

        raw_err = f"Failed to POST to {secret_url} with Authorization: Bearer {secret_token}"
        sanitized = sanitize_text(raw_err)
        assert secret_token not in sanitized
        assert "Bearer [REDACTED]" in sanitized
        assert "[REDACTED_WEBHOOK_URL]" in sanitized


# ---------------------------------------------------------------------------
# 7. Idempotency & Phase 8.1 Preservation (Reqs 17, 18)
# ---------------------------------------------------------------------------

class TestIdempotencyAndRegression:
    """Tests for idempotency retention and Phase 8.1 backward compatibility."""

    def test_existing_idempotency_behavior_is_preserved(self, monkeypatch):
        """Req 17: Existing idempotency behavior returns existing execution without re-execution."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/SECRET123")
        wf = _make_slack_workflow(workflow_id="wf-idem-001", status="approved")

        existing_record = WorkflowExecution(
            execution_id="exec-existing-001",
            workflow_id="wf-idem-001",
            status=ExecutionStatus.COMPLETED,
            mode=ExecutionMode.LIVE,
            idempotency_key="idemp-key-999",
            created_at=datetime.now(timezone.utc),
        )

        with patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=existing_record), \
             patch("urllib.request.urlopen") as mock_urlopen:

            res = execute_live("wf-idem-001", idempotency_key="idemp-key-999")
            assert res.execution_id == "exec-existing-001"
            mock_urlopen.assert_not_called()

    def test_existing_phase8_1_dry_run_continues_passing(self):
        """Req 18: Existing Phase 8.1 dry-run execution continues to simulate all steps safely."""
        wf = _make_slack_workflow(workflow_id="wf-regress-001", status="approved")

        with patch("app.services.execution_service.db_get_workflow_by_id", return_value=wf), \
             patch("app.services.execution_service.db_get_execution_by_idempotency_key", return_value=None), \
             patch("app.services.execution_service.db_insert_execution", return_value="exec-012"), \
             patch("app.services.execution_service.db_save_execution", side_effect=lambda x: x):

            dry_run_exec = execute_dry_run("wf-regress-001")
            assert dry_run_exec.mode == ExecutionMode.DRY_RUN
            assert dry_run_exec.status == ExecutionStatus.COMPLETED
            assert dry_run_exec.completed_steps == 1
            assert dry_run_exec.step_records[0].status == ExecutionStepStatus.DRY_RUN
