"""
Phase 8.6 — Gmail open_email Integration Tests
==============================================
Validates:
1. Adapter registration for 'open_email' in IntegrationRegistry.
2. Supported action inspection (can_handle('open_email') is True, case-insensitive).
3. Missing messageId validation failure (zero API calls).
4. Empty / malformed messageId validation failure.
5. Dry-run makes zero Gmail API calls and returns simulated output.
6. Successful mocked Gmail message retrieval with structured outputs (messageId, threadId, subject, sender, recipient, snippet).
7. Gmail 404 message not found handling.
8. Gmail 401/403 authorization error handling.
9. OAuth refresh failure handling.
10. API/network timeout and generic error handling.
11. Credential and token redaction in logs/errors.
12. Zero Gmail mutation methods called (no send, modify, delete, trash, label).
13. Execution-service integration (live approved workflow path).
14. Approved workflow hard guard (unapproved workflows blocked).
15. Existing read_email functionality remains intact and working.
16. Opt-in live test isolation.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.base import (
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.integrations.gmail.adapter import GmailAdapter
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
from app.services.execution_service import (
    WorkflowNotApprovedError,
    execute_dry_run,
    execute_live,
)


def build_open_email_context(
    variables: Dict[str, Any] | None = None,
    dry_run: bool = False,
    inputs: list[str] | None = None,
) -> StepExecutionContext:
    step = WorkflowStep(
        step_id="step-gmail-open-001",
        order=1,
        application="Gmail",
        action="open_email",
        description="Open specific email by ID",
        inputs=inputs or ["messageId"],
        outputs=["messageId", "threadId", "subject", "sender", "recipient", "snippet"],
    )
    return StepExecutionContext(
        workflow_id="wf-test-open-001",
        execution_id="exec-test-open-001",
        step=step,
        variables=variables or {},
        dry_run=dry_run,
    )


def build_open_email_workflow(status: str = "approved") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=f"wf-open-{status}-001",
        understanding_id="und-open-001",
        name="Gmail Open Email Workflow",
        description="Retrieve message details for specific ID",
        status=status,
        trigger=WorkflowTrigger(
            application="Gmail",
            event="email_selected",
            description="Trigger on specific email selection",
        ),
        steps=[
            WorkflowStep(
                step_id="step-1",
                order=1,
                application="Gmail",
                action="open_email",
                description="Open support email",
                inputs=["messageId"],
                outputs=["messageId", "threadId", "subject", "sender", "recipient", "snippet"],
            ),
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email inspection",
                required_capabilities=["open_email"],
            ),
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="stop",
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestGmailOpenEmailRegistrationAndCapabilities:
    """Requirement 1 & 2: Adapter registration and supported actions."""

    def test_adapter_registration_for_open_email(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "open_email")
        assert adapter is not None
        assert isinstance(adapter, GmailAdapter)
        assert adapter.application_name == "Gmail"

    def test_can_handle_open_email_case_insensitive(self):
        adapter = GmailAdapter()
        assert adapter.can_handle("open_email") is True
        assert adapter.can_handle("OPEN_EMAIL") is True
        assert adapter.can_handle("  open_email  ") is True

    def test_existing_read_email_remains_supported(self):
        """Requirement 15: Existing read_email functionality remains working."""
        adapter = GmailAdapter()
        assert adapter.can_handle("read_email") is True

    def test_unsupported_actions_still_rejected(self):
        adapter = GmailAdapter()
        for forbidden in ("send_email", "delete_email", "trash_email", "archive_email", "modify_email", "forward_email"):
            assert adapter.can_handle(forbidden) is False


class TestGmailOpenEmailInputValidation:
    """Requirement 3 & 4: Missing, empty, or malformed messageId validation."""

    def test_missing_message_id_returns_validation_failure(self):
        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={})
        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "missing required 'messageId' input" in result.error_summary

    def test_empty_whitespace_message_id_returns_validation_failure(self):
        adapter = GmailAdapter()
        for empty_val in ("", "   ", "\t\n"):
            ctx = build_open_email_context(variables={"messageId": empty_val})
            result = adapter.execute(ctx)
            assert result.success is False
            assert result.status == ExecutionStepStatus.FAILED
            assert "missing required 'messageId' input" in result.error_summary

    def test_malformed_message_id_with_invalid_characters(self):
        adapter = GmailAdapter()
        for bad_id in ("msg id with spaces", "id<with>brackets", "id/with/slashes", "id\nwith\nnewlines"):
            ctx = build_open_email_context(variables={"messageId": bad_id})
            result = adapter.execute(ctx)
            assert result.success is False
            assert result.status == ExecutionStepStatus.FAILED
            assert "Invalid 'messageId'" in result.error_summary

    def test_accepts_alternative_variable_names(self):
        """Supports message_id, id, msg_id conventions without inventing IDs."""
        adapter = GmailAdapter()
        for key in ("message_id", "id", "msg_id"):
            ctx = build_open_email_context(variables={key: "valid_msg_123"}, dry_run=True)
            result = adapter.execute(ctx)
            assert result.success is True
            assert result.outputs["messageId"] == "valid_msg_123"


class TestGmailOpenEmailDryRunSafety:
    """Requirement 5: Dry-run makes zero Gmail API calls and returns simulated data."""

    def test_dry_run_makes_zero_gmail_api_calls(self):
        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "msg-xyz-999"}, dry_run=True)

        with patch("googleapiclient.discovery.build") as mock_build:
            result = adapter.execute(ctx)
            assert mock_build.call_count == 0

        assert result.success is True
        assert result.status == ExecutionStepStatus.DRY_RUN
        assert "simulated" in result.result_summary.lower()
        assert result.outputs["messageId"] == "msg-xyz-999"
        assert result.outputs["dry_run"] is True
        assert "subject" in result.outputs
        assert "sender" in result.outputs
        assert "recipient" in result.outputs
        assert "snippet" in result.outputs


class TestGmailOpenEmailMockedRetrieval:
    """Requirement 6 & 12: Successful mocked message retrieval and no mutation."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_successful_mocked_message_retrieval(self, mock_creds_cls, mock_build, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_USER_ID", "me")

        # Mock credentials
        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "mock-active-access-token"
        mock_creds_cls.return_value = mock_creds_inst

        # Mock service and messages resource
        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_get_req = MagicMock()
        mock_get_req.execute.return_value = {
            "id": "18c21a3028fa2aa",
            "threadId": "18c21a3028fa2aa",
            "snippet": "Hello, thank you for reaching out regarding invoice #9948.",
            "internalDate": "1727000000000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Invoice #9948 Question"},
                    {"name": "From", "value": "Alice <alice@example.com>"},
                    {"name": "To", "value": "support@workflowos.com"},
                    {"name": "Date", "value": "Mon, 22 Sep 2026 14:00:00 GMT"},
                ]
            },
        }
        mock_messages.get.return_value = mock_get_req
        mock_service.users.return_value.messages.return_value = mock_messages
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "18c21a3028fa2aa"})

        result = adapter.execute(ctx)

        # Verify success and structured outputs
        assert result.success is True
        assert result.status == ExecutionStepStatus.COMPLETED
        assert result.outputs["messageId"] == "18c21a3028fa2aa"
        assert result.outputs["threadId"] == "18c21a3028fa2aa"
        assert result.outputs["subject"] == "Invoice #9948 Question"
        assert result.outputs["sender"] == "Alice <alice@example.com>"
        assert result.outputs["recipient"] == "support@workflowos.com"
        assert result.outputs["snippet"] == "Hello, thank you for reaching out regarding invoice #9948."
        assert "2024-09-22" in result.outputs["received_at"]

        # Verify API call parameters
        mock_messages.get.assert_called_once_with(
            userId="me",
            id="18c21a3028fa2aa",
            format="metadata",
            metadataHeaders=["Subject", "From", "To", "Date"],
        )

        # Requirement 12: Zero mutation methods called
        assert mock_messages.send.call_count == 0
        assert mock_messages.delete.call_count == 0
        assert mock_messages.trash.call_count == 0
        assert mock_messages.modify.call_count == 0
        assert mock_messages.batchModify.call_count == 0
        assert mock_messages.batchDelete.call_count == 0


class TestGmailOpenEmailErrorHandlingAndSecurity:
    """Requirement 7, 8, 9, 10, 11: Error handling, status codes, and secret sanitization."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_gmail_404_message_not_found(self, mock_creds_cls, mock_build, monkeypatch):
        from googleapiclient.errors import HttpError
        import httplib2

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        # Simulate 404 HttpError
        resp = httplib2.Response({"status": "404"})
        resp.status = 404
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.side_effect = (
            HttpError(resp, b'{"error": {"code": 404, "message": "Not Found"}}')
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "missing-id-404"})

        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "not found" in result.result_summary.lower()
        assert "404" in result.error_summary

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_gmail_401_403_authorization_error(self, mock_creds_cls, mock_build, monkeypatch):
        from googleapiclient.errors import HttpError
        import httplib2

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        resp = httplib2.Response({"status": "403"})
        resp.status = 403
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.side_effect = (
            HttpError(resp, b'{"error": {"code": 403, "message": "Forbidden"}}')
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "msg-id-123"})

        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "authorization error" in result.result_summary.lower()

    @patch("google.oauth2.credentials.Credentials")
    def test_oauth_refresh_failure_and_redaction(self, mock_creds_cls, monkeypatch):
        dummy_secret = "ULTRA_CONFIDENTIAL_SECRET_XYZ"
        dummy_refresh = "ULTRA_CONFIDENTIAL_REFRESH_ABC"

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", dummy_secret)
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", dummy_refresh)

        mock_creds_inst = MagicMock()
        mock_creds_inst.refresh.side_effect = Exception(f"invalid_grant with secret {dummy_secret}")
        mock_creds_cls.return_value = mock_creds_inst

        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "msg-id-123"})

        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED

        # Requirement 11: Secret and refresh token strictly redacted
        assert dummy_secret not in result.error_summary
        assert dummy_refresh not in result.error_summary
        assert "[REDACTED_GOOGLE_CLIENT_SECRET]" in result.error_summary

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_network_timeout_error(self, mock_creds_cls, mock_build, monkeypatch):
        import socket

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.get.return_value.execute.side_effect = (
            socket.timeout("Socket timed out")
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_open_email_context(variables={"messageId": "msg-id-123"})

        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "timed out" in result.result_summary.lower()


class TestExecutionServiceGmailOpenEmailIntegration:
    """Requirement 13 & 14: Execution-service integration and hard approval guard."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_execute_live_approved_workflow_with_open_email_step(self, mock_creds_cls, mock_build, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_get_req = MagicMock()
        mock_get_req.execute.return_value = {
            "id": "open_msg_999",
            "threadId": "th_999",
            "snippet": "Opening verified email",
            "internalDate": "1727000000000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Service Alert"},
                    {"name": "From", "value": "alerts@system.com"},
                    {"name": "To", "value": "admin@system.com"},
                    {"name": "Date", "value": "Mon, 22 Sep 2026 10:00:00 GMT"},
                ]
            },
        }
        mock_messages.get.return_value = mock_get_req
        mock_service.users.return_value.messages.return_value = mock_messages
        mock_build.return_value = mock_service

        wf = build_open_email_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"messageId": "open_msg_999"},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_steps == 1
        assert len(execution.step_records) == 1

        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.application == "Gmail"
        assert step_rec.action == "open_email"
        assert "Gmail open_email completed successfully" in step_rec.result_summary

    def test_execute_live_fails_if_workflow_not_approved(self):
        """Hard approval guard prevents execution of unapproved open_email workflows."""
        for status in ("generated", "rejected"):
            wf = build_open_email_workflow(status=status)
            wf.workflow_id = f"wf-open-guard-{status}"
            upsert_workflow(wf)

            with pytest.raises(WorkflowNotApprovedError) as exc_info:
                execute_live(wf.workflow_id, variables={"messageId": "msg_001"})

            assert exc_info.value.status_code == 409
            assert f"current status is '{status}'" in exc_info.value.message


class TestOptInLiveGmailOpenEmailAPI:
    """
    Opt-in live integration test.
    Only runs when RUN_LIVE_GMAIL_TESTS=1 is set.
    """

    @pytest.mark.skipif(
        not os.getenv("RUN_LIVE_GMAIL_TESTS"),
        reason="Opt-in only. Set RUN_LIVE_GMAIL_TESTS=1 to run against live Gmail API.",
    )
    def test_live_gmail_open_email_call(self):
        adapter = GmailAdapter()
        # First read 1 message to get an active message ID safely
        read_ctx = StepExecutionContext(
            workflow_id="wf-live-open-test",
            execution_id="exec-live-open-test",
            step=WorkflowStep(
                step_id="step-1",
                order=1,
                application="Gmail",
                action="read_email",
                description="Fetch message ID",
            ),
            variables={"query": "label:INBOX", "max_results": 1},
        )
        read_res = adapter.execute(read_ctx)
        assert read_res.success is True
        msg_ids = read_res.outputs.get("message_ids", [])
        if not msg_ids:
            pytest.skip("No messages in INBOX to open.")

        target_id = msg_ids[0]
        open_ctx = build_open_email_context(variables={"messageId": target_id})
        open_res = adapter.execute(open_ctx)
        assert open_res.success is True
        assert open_res.status == ExecutionStepStatus.COMPLETED
        assert open_res.outputs["messageId"] == target_id
        assert "subject" in open_res.outputs
        assert "sender" in open_res.outputs
