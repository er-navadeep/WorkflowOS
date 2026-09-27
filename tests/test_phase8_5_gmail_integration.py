"""
Phase 8.5 — Gmail Read-Only Integration Adapter Tests
=====================================================
Validates:
1. Adapter registration and capability inspection ('Gmail' / 'read_email').
2. Rejection of unsupported actions (e.g. 'send_email', 'delete_email').
3. Configuration checks (missing GOOGLE_CLIENT_ID, SECRET, REFRESH_TOKEN).
4. Input validation (missing query, invalid max_results, safe upper bound).
5. Dry-run safety (zero external API calls, pure simulated output).
6. Mocked live execution with structured outputs (message_ids, subject, sender, snippet).
7. Error handling and credential sanitization (refresh failure, API error).
8. ExecutionService integration (approved workflow path, approval guard, audit records).
9. Opt-in live test isolation.
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
from app.integrations.gmail.adapter import (
    DEFAULT_MAX_RESULTS,
    MAX_ALLOWED_RESULTS,
    GmailAdapter,
)
from app.integrations.registry import IntegrationRegistry, get_integration_registry
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


# Helper to build a minimal step execution context
def build_context(
    action: str = "read_email",
    variables: Dict[str, Any] | None = None,
    dry_run: bool = False,
    inputs: list[str] | None = None,
) -> StepExecutionContext:
    step = WorkflowStep(
        step_id="step-gmail-001",
        order=1,
        application="Gmail",
        action=action,
        description="Read customer email",
        inputs=inputs or ["query"],
        outputs=["message_ids", "messages", "subject", "sender"],
    )
    return StepExecutionContext(
        workflow_id="wf-test-gmail-001",
        execution_id="exec-test-gmail-001",
        step=step,
        variables=variables or {},
        dry_run=dry_run,
    )


# Helper to build a valid WorkflowDefinition for execution tests
def build_workflow(status: str = "approved") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=f"wf-gmail-{status}-001",
        understanding_id="und-gmail-001",
        name="Gmail Support Workflow",
        description="Read incoming email and process request",
        status=status,
        trigger=WorkflowTrigger(
            application="Gmail",
            event="incoming_email",
            description="Trigger on new support inquiry",
        ),
        steps=[
            WorkflowStep(
                step_id="step-1",
                order=1,
                application="Gmail",
                action="read_email",
                description="Read support email",
                inputs=["query"],
                outputs=["message_ids", "messages", "subject", "sender"],
            ),
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email inspection",
                required_capabilities=["read_email"],
            ),
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="request_human_intervention",
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestGmailAdapterRegistration:
    """Validate registration and action capability inspection."""

    def test_adapter_properties(self):
        adapter = GmailAdapter()
        assert adapter.application_name == "Gmail"

    def test_can_handle_read_email_case_insensitive(self):
        adapter = GmailAdapter()
        assert adapter.can_handle("read_email") is True
        assert adapter.can_handle("READ_EMAIL") is True
        assert adapter.can_handle("  read_email  ") is True

    def test_unsupported_actions_return_false(self):
        adapter = GmailAdapter()
        assert adapter.can_handle("send_email") is False
        assert adapter.can_handle("delete_email") is False
        assert adapter.can_handle("archive_email") is False
        assert adapter.can_handle("modify_email") is False
        assert adapter.can_handle("") is False

    def test_registered_in_global_registry(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "read_email")
        assert adapter is not None
        assert isinstance(adapter, GmailAdapter)
        assert adapter.application_name == "Gmail"

    def test_slack_adapter_remains_registered(self):
        """Rule: Do not break existing Slack adapter."""
        registry = get_integration_registry()
        slack = registry.get_adapter("Slack", "send_message")
        assert slack is not None
        assert slack.application_name == "Slack"


class TestGmailInputValidation:
    """Validate input contract: query required, max_results bounds, no invented values."""

    def test_missing_query_returns_validation_failure(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={})
        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "missing required 'query' input" in result.error_summary

    def test_empty_query_returns_validation_failure(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "   "})
        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "missing required 'query' input" in result.error_summary

    def test_invalid_max_results_zero_or_negative(self):
        adapter = GmailAdapter()
        for bad_val in (0, -1, -10):
            ctx = build_context(variables={"query": "is:unread", "max_results": bad_val})
            result = adapter.execute(ctx)
            assert result.success is False
            assert result.status == ExecutionStepStatus.FAILED
            assert "Invalid 'max_results'" in result.error_summary

    def test_invalid_max_results_exceeds_upper_bound(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "is:unread", "max_results": MAX_ALLOWED_RESULTS + 1})
        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert f"must be an integer between 1 and {MAX_ALLOWED_RESULTS}" in result.error_summary

    def test_invalid_max_results_non_numeric(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "is:unread", "max_results": "invalid_number"})
        result = adapter.execute(ctx)
        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "is not a valid integer" in result.error_summary


class TestGmailConfigurationCheck:
    """Validate behavior when OAuth credentials are missing from environment."""

    def test_missing_credentials_fails_safely(self, monkeypatch):
        adapter = GmailAdapter()
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        ctx = build_context(variables={"query": "label:INBOX"})
        result = adapter.execute(ctx)

        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "missing required OAuth configuration" in result.result_summary
        assert "GOOGLE_CLIENT_ID" in result.error_summary
        assert "GOOGLE_CLIENT_SECRET" in result.error_summary
        assert "GOOGLE_REFRESH_TOKEN" in result.error_summary


class TestGmailDryRunSafety:
    """Validate dry-run execution produces zero network calls."""

    def test_dry_run_makes_zero_network_calls(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "from:test@example.com"}, dry_run=True)

        with patch("googleapiclient.discovery.build") as mock_build:
            result = adapter.execute(ctx)
            assert mock_build.call_count == 0

        assert result.success is True
        assert result.status == ExecutionStepStatus.DRY_RUN
        assert "simulated" in result.result_summary.lower()
        assert result.outputs["message_count"] == 1
        assert "simulated-msg-001" in result.outputs["message_ids"]
        assert result.outputs["subject"] == "DRY RUN Simulation — Read Email"


class TestGmailMockedLiveExecution:
    """Validate live execution flow using mocked Gmail API responses."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_successful_mocked_read_email(self, mock_creds_cls, mock_build, monkeypatch):
        dummy_secret = "TEST_SECRET_VALUE_XYZ"
        dummy_refresh = "1//04_TEST_REFRESH_XYZ"

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", dummy_secret)
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", dummy_refresh)
        monkeypatch.setenv("GMAIL_USER_ID", "me")

        # Mock credentials
        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "mock-active-access-token"
        mock_creds_cls.return_value = mock_creds_inst

        # Mock service
        mock_service = MagicMock()
        mock_messages_resource = MagicMock()
        mock_service.users.return_value.messages.return_value = mock_messages_resource

        # Mock list response (2 messages)
        mock_list_req = MagicMock()
        mock_list_req.execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "th_001"}, {"id": "msg_002", "threadId": "th_002"}]
        }
        mock_messages_resource.list.return_value = mock_list_req

        # Mock get responses
        def mock_get_execute(userId, id, format, metadataHeaders):
            req = MagicMock()
            if id == "msg_001":
                req.execute.return_value = {
                    "id": "msg_001",
                    "threadId": "th_001",
                    "snippet": "First email snippet content",
                    "internalDate": "1727000000000",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Invoice #1001"},
                            {"name": "From", "value": "billing@vendor.com"},
                            {"name": "Date", "value": "Mon, 22 Sep 2026 10:00:00 GMT"},
                        ]
                    },
                }
            else:
                req.execute.return_value = {
                    "id": "msg_002",
                    "threadId": "th_002",
                    "snippet": "Second email snippet content",
                    "internalDate": "1727010000000",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Support Request"},
                            {"name": "From", "value": "client@company.com"},
                            {"name": "Date", "value": "Mon, 22 Sep 2026 12:00:00 GMT"},
                        ]
                    },
                }
            return req

        mock_messages_resource.get.side_effect = mock_get_execute
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "label:INBOX is:unread", "max_results": 2})

        result = adapter.execute(ctx)

        assert result.success is True
        assert result.status == ExecutionStepStatus.COMPLETED
        assert result.outputs["message_count"] == 2
        assert result.outputs["message_ids"] == ["msg_001", "msg_002"]
        assert result.outputs["subject"] == "Invoice #1001"
        assert result.outputs["sender"] == "billing@vendor.com"
        assert result.outputs["snippet"] == "First email snippet content"
        assert len(result.outputs["messages"]) == 2

        # Verify no mutation methods were called on messages resource
        assert mock_messages_resource.send.call_count == 0
        assert mock_messages_resource.delete.call_count == 0
        assert mock_messages_resource.trash.call_count == 0
        assert mock_messages_resource.modify.call_count == 0
        assert mock_messages_resource.batchModify.call_count == 0

    @patch("google.oauth2.credentials.Credentials")
    def test_oauth_refresh_failure_handled_safely(self, mock_creds_cls, monkeypatch):
        dummy_secret = "CONFIDENTIAL_SECRET_12345"
        dummy_refresh = "CONFIDENTIAL_REFRESH_67890"

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", dummy_secret)
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", dummy_refresh)

        mock_creds_inst = MagicMock()
        mock_creds_inst.refresh.side_effect = Exception(f"invalid_grant: bad token {dummy_secret}")
        mock_creds_cls.return_value = mock_creds_inst

        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "test query"})
        result = adapter.execute(ctx)

        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "authentication failed" in result.result_summary.lower()
        # Verify secret was redacted
        assert dummy_secret not in result.error_summary
        assert "[REDACTED_GOOGLE_CLIENT_SECRET]" in result.error_summary

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_api_error_handled_safely(self, mock_creds_cls, mock_build, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "active-token"
        mock_creds_cls.return_value = mock_creds_inst

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.side_effect = Exception("HttpError 500: Server error")
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "test query"})
        result = adapter.execute(ctx)

        assert result.success is False
        assert result.status == ExecutionStepStatus.FAILED
        assert "API request failed" in result.result_summary


class TestExecutionServiceGmailIntegration:
    """Validate end-to-end execution service orchestration for Gmail steps."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_execute_live_approved_workflow_with_gmail_step(self, mock_creds_cls, mock_build, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        # Mock credentials
        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        # Mock service
        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_list_req = MagicMock()
        mock_list_req.execute.return_value = {"messages": [{"id": "live_msg_001", "threadId": "th_001"}]}
        mock_messages.list.return_value = mock_list_req

        mock_get_req = MagicMock()
        mock_get_req.execute.return_value = {
            "id": "live_msg_001",
            "threadId": "th_001",
            "snippet": "Live email body snippet",
            "internalDate": "1727000000000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Customer Inquiry"},
                    {"name": "From", "value": "customer@acme.com"},
                    {"name": "Date", "value": "Mon, 22 Sep 2026 10:00:00 GMT"},
                ]
            },
        }
        mock_messages.get.return_value = mock_get_req
        mock_service.users.return_value.messages.return_value = mock_messages
        mock_build.return_value = mock_service

        # Create approved workflow in DB
        wf = build_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"query": "is:unread label:INBOX"},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_steps == 1
        assert len(execution.step_records) == 1

        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.application == "Gmail"
        assert step_rec.action == "read_email"
        assert "Gmail read_email completed successfully" in step_rec.result_summary

    def test_execute_live_fails_if_workflow_not_approved(self):
        """Rule: Hard approval guard blocks execution of non-approved workflows."""
        for status in ("generated", "rejected"):
            wf = build_workflow(status=status)
            wf.workflow_id = f"wf-gmail-guard-{status}"
            upsert_workflow(wf)

            with pytest.raises(WorkflowNotApprovedError) as exc_info:
                execute_live(wf.workflow_id)

            assert exc_info.value.status_code == 409
            assert f"current status is '{status}'" in exc_info.value.message


class TestOptInLiveGmailAPI:
    """
    Opt-in live integration test.
    Never runs in normal test suite unless RUN_LIVE_GMAIL_TESTS=1 is explicitly set.
    """

    @pytest.mark.skipif(
        not os.getenv("RUN_LIVE_GMAIL_TESTS"),
        reason="Opt-in only. Set RUN_LIVE_GMAIL_TESTS=1 to run against live Gmail API.",
    )
    def test_live_gmail_read_only_call(self):
        adapter = GmailAdapter()
        ctx = build_context(variables={"query": "label:INBOX", "max_results": 1})
        result = adapter.execute(ctx)
        assert result.success is True
        assert result.status == ExecutionStepStatus.COMPLETED
        assert "message_count" in result.outputs
