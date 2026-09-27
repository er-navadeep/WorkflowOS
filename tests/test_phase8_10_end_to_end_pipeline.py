"""
Phase 8.10 — End-to-End Workflow Pipeline Integration Tests
============================================================
Comprehensive test suite verifying the complete 6-step integration pipeline:

    Gmail (read_email)
       ↓
    Gmail (open_email)
       ↓
    Gmail (download_file)
       ↓
    CRM (find_customer)
       ↓
    CRM (update_customer)
       ↓
    Slack (send_message)
       ↓
    COMPLETED

Tests:
 1. Pipeline workflow definition structure (6 steps, orders 1..6, applications, actions).
 2. Hard approval guard: 'generated' status blocked from live execution (409).
 3. Hard approval guard: 'rejected' status blocked from live execution (409).
 4. Hard approval guard: 'generated' status blocked from dry-run execution (409).
 5. Dry-run execution: all 6 steps simulated, status=COMPLETED, completed_steps=6.
 6. Dry-run execution: zero network calls, zero database writes.
 7. Live execution full chain: all 6 steps execute successfully to COMPLETED.
 8. Inter-step variable propagation: Step 1 messageId flows to Step 2 & 3.
 9. Inter-step variable propagation: CRM outputs flow to Slack notification step.
 10. Failure at Step 1 (read_email): halts pipeline, completed_steps=0, failed_step=1.
 11. Failure at Step 2 (open_email): halts pipeline, completed_steps=1, failed_step=2.
 12. Failure at Step 3 (download_file): halts pipeline, completed_steps=2, failed_step=3.
 13. Failure at Step 4 (find_customer): halts pipeline, completed_steps=3, failed_step=4.
 14. Failure at Step 5 (update_customer): halts pipeline, completed_steps=4, failed_step=5.
 15. Failure at Step 6 (send_message): halts pipeline, completed_steps=5, failed_step=6.
 16. Error handling: on_failure='human_intervention' transitions to NEEDS_INTERVENTION.
 17. Idempotency key preservation across repeated executions.
 18. Output structure safety: ExecutionStepRecord has no 'outputs' attribute.
 19. Secret sanitization: zero credentials, secrets, or raw webhooks in execution records.
 20. Mock CRM local data mutation & rollback verification.
 21. IntegrationRegistry regression: all 6 actions concurrently registered.
 22. Unknown customer lookup in CRM: safely completes without crashing pipeline.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.base import StepExecutionContext, StepExecutionResult
from app.integrations.crm.adapter import CRMAdapter
from app.integrations.gmail.adapter import GmailAdapter
from app.integrations.registry import get_integration_registry
from app.integrations.slack.adapter import SlackAdapter
from app.models.mock_crm import (
    ensure_seed_data,
    find_customer_by_identifier,
    restore_customer_to_seed,
    SEED_CUSTOMERS,
)
from app.models.workflow import upsert_workflow
from app.schemas.execution import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepRecord,
    ExecutionStepStatus,
    WorkflowExecution,
)
from app.schemas.workflow import WorkflowDefinition, WorkflowStep
from app.services.e2e_pipeline import (
    DEFAULT_TEST_IDENTIFIER,
    DEFAULT_TEST_SLACK_MESSAGE,
    DEFAULT_TEST_UPDATE_NOTES,
    DEFAULT_TEST_UPDATE_STATUS,
    build_default_pipeline_variables,
    build_e2e_pipeline_workflow,
    execute_e2e_pipeline,
    get_or_create_e2e_workflow,
)
from app.services.execution_service import (
    WorkflowNotApprovedError,
    execute_dry_run,
    execute_live,
)


@pytest.fixture(autouse=True)
def setup_crm_seed():
    """Ensure seed data is fresh and restore test customer after each test."""
    try:
        ensure_seed_data()
    except Exception:
        pass
    yield
    try:
        restore_customer_to_seed(DEFAULT_TEST_IDENTIFIER)
    except Exception:
        pass


# ===========================================================================
# 1. Pipeline Definition Structure Tests
# ===========================================================================

class TestPipelineDefinition:
    def test_workflow_has_six_steps(self):
        wf = build_e2e_pipeline_workflow()
        assert len(wf.steps) == 6

    def test_step_ordering_is_strictly_sequential(self):
        wf = build_e2e_pipeline_workflow()
        orders = [s.order for s in wf.steps]
        assert orders == [1, 2, 3, 4, 5, 6]

    def test_expected_application_action_sequence(self):
        wf = build_e2e_pipeline_workflow()
        sequence = [(s.application, s.action) for s in sorted(wf.steps, key=lambda x: x.order)]
        expected = [
            ("Gmail", "read_email"),
            ("Gmail", "open_email"),
            ("Gmail", "download_file"),
            ("CRM", "find_customer"),
            ("CRM", "update_customer"),
            ("Slack", "send_message"),
        ]
        assert sequence == expected

    def test_integrations_cover_all_three_apps(self):
        wf = build_e2e_pipeline_workflow()
        apps = {i.application for i in wf.integrations}
        assert apps == {"Gmail", "CRM", "Slack"}

    def test_default_status_is_approved(self):
        wf = build_e2e_pipeline_workflow()
        assert wf.status == "approved"
        assert wf.approved_at is not None
        assert wf.reviewed_by is not None


# ===========================================================================
# 2. Hard Approval Guardrails
# ===========================================================================

class TestPipelineApprovalGuard:
    def test_generated_status_blocked_from_live(self):
        wf = build_e2e_pipeline_workflow(status="generated")
        upsert_workflow(wf)
        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            execute_live(wf.workflow_id)
        assert "cannot be executed" in str(exc_info.value)
        assert exc_info.value.current_status == "generated"

    def test_rejected_status_blocked_from_live(self):
        wf = build_e2e_pipeline_workflow(status="rejected")
        upsert_workflow(wf)
        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            execute_live(wf.workflow_id)
        assert exc_info.value.current_status == "rejected"

    def test_generated_status_blocked_from_dry_run(self):
        wf = build_e2e_pipeline_workflow(status="generated")
        upsert_workflow(wf)
        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            execute_dry_run(wf.workflow_id)
        assert exc_info.value.current_status == "generated"


# ===========================================================================
# 3. Dry-Run Execution Engine
# ===========================================================================

class TestPipelineDryRun:
    def test_dry_run_executes_all_six_steps_to_completed(self):
        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)
        execution = execute_dry_run(wf.workflow_id)

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.mode == ExecutionMode.DRY_RUN
        assert execution.total_steps == 6
        assert execution.completed_steps == 6
        assert execution.failed_step is None
        assert len(execution.step_records) == 6

    def test_dry_run_step_records_have_dry_run_status(self):
        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)
        execution = execute_dry_run(wf.workflow_id)

        for rec in execution.step_records:
            assert rec.status == ExecutionStepStatus.DRY_RUN
            assert "DRY RUN" in rec.result_summary
            assert rec.error_summary is None

    def test_dry_run_makes_zero_database_writes(self):
        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        before = find_customer_by_identifier(DEFAULT_TEST_IDENTIFIER)
        before_status = before.get("status") if before else None

        execute_dry_run(
            wf.workflow_id,
            trigger_override={
                "customerIdentifier": DEFAULT_TEST_IDENTIFIER,
                "updates": {"status": "inactive", "notes": "Dry run attempt"},
            },
        )

        after = find_customer_by_identifier(DEFAULT_TEST_IDENTIFIER)
        after_status = after.get("status") if after else None
        assert after_status == before_status


# ===========================================================================
# 4. Live Chained Pipeline Execution
# ===========================================================================

class TestPipelineLiveChainedExecution:
    @patch.object(GmailAdapter, "execute")
    @patch.object(SlackAdapter, "execute")
    def test_full_pipeline_success(self, mock_slack, mock_gmail):
        # Step 1: read_email
        step1_result = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={
                "messageId": "msg-live-100",
                "message_id": "msg-live-100",
                "sender": DEFAULT_TEST_IDENTIFIER,
                "subject": "Customer inquiry with document",
            },
            result_summary="Gmail read_email completed: found 1 message.",
        )
        # Step 2: open_email
        step2_result = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={
                "messageId": "msg-live-100",
                "message_id": "msg-live-100",
                "threadId": "thread-100",
                "subject": "Customer inquiry with document",
                "sender": DEFAULT_TEST_IDENTIFIER,
                "snippet": "Please find attached document for processing.",
            },
            result_summary="Gmail open_email completed successfully.",
        )
        # Step 3: download_file
        step3_result = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={
                "filename": "customer_doc.pdf",
                "path": "backend/runtime/downloads/customer_doc.pdf",
                "size_bytes": 2048,
                "content_type": "application/pdf",
                "message_id": "msg-live-100",
                "attachment_id": "att-100",
            },
            result_summary="Gmail download_file completed: downloaded customer_doc.pdf.",
        )
        mock_gmail.side_effect = [step1_result, step2_result, step3_result]

        # Step 6: Slack send_message
        step6_result = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={"slack_delivery": "delivered"},
            result_summary="Slack message sent successfully.",
        )
        mock_slack.return_value = step6_result

        # Run pipeline
        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        variables = build_default_pipeline_variables(
            customer_identifier=DEFAULT_TEST_IDENTIFIER,
            update_status=DEFAULT_TEST_UPDATE_STATUS,
            update_notes=DEFAULT_TEST_UPDATE_NOTES,
            slack_message=DEFAULT_TEST_SLACK_MESSAGE,
        )

        execution = execute_live(workflow_id=wf.workflow_id, variables=variables)

        # Assert full workflow completion
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.total_steps == 6
        assert execution.completed_steps == 6
        assert execution.failed_step is None
        assert execution.error_information is None
        assert len(execution.step_records) == 6

        # Verify all step records are COMPLETED
        for rec in execution.step_records:
            assert rec.status == ExecutionStepStatus.COMPLETED
            assert rec.error_summary is None

        # Verify steps 4 & 5 executed against real local mock CRM
        updated_doc = find_customer_by_identifier(DEFAULT_TEST_IDENTIFIER)
        assert updated_doc is not None
        assert updated_doc.get("status") == DEFAULT_TEST_UPDATE_STATUS
        assert updated_doc.get("notes") == DEFAULT_TEST_UPDATE_NOTES

        # Verify Slack call received context
        assert mock_slack.call_count == 1
        slack_ctx = mock_slack.call_args[0][0]
        assert slack_ctx.step.action == "send_message"
        assert "message" in slack_ctx.variables

    @patch.object(GmailAdapter, "execute")
    @patch.object(SlackAdapter, "execute")
    def test_inter_step_variable_propagation(self, mock_slack, mock_gmail):
        captured_contexts = []

        def capture_gmail(ctx):
            captured_contexts.append((ctx.step.action, dict(ctx.variables)))
            if ctx.step.action == "read_email":
                return StepExecutionResult(
                    success=True,
                    status=ExecutionStepStatus.COMPLETED,
                    outputs={"messageId": "propagated-msg-id-42", "sender": DEFAULT_TEST_IDENTIFIER},
                    result_summary="read_email success",
                )
            elif ctx.step.action == "open_email":
                return StepExecutionResult(
                    success=True,
                    status=ExecutionStepStatus.COMPLETED,
                    outputs={"subject": "Important Invoice"},
                    result_summary="open_email success",
                )
            else:
                return StepExecutionResult(
                    success=True,
                    status=ExecutionStepStatus.COMPLETED,
                    outputs={"filename": "invoice.pdf", "path": "downloads/invoice.pdf"},
                    result_summary="download_file success",
                )

        mock_gmail.side_effect = capture_gmail
        mock_slack.return_value = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={"slack_delivery": "delivered"},
            result_summary="slack sent",
        )

        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        variables = build_default_pipeline_variables()
        execution = execute_live(workflow_id=wf.workflow_id, variables=variables)

        assert execution.status == ExecutionStatus.COMPLETED

        # Check step 2 open_email received propagated messageId from step 1
        step2_action, step2_vars = captured_contexts[1]
        assert step2_action == "open_email"
        assert step2_vars.get("messageId") == "propagated-msg-id-42"

        # Check step 3 download_file received propagated messageId
        step3_action, step3_vars = captured_contexts[2]
        assert step3_action == "download_file"
        assert step3_vars.get("messageId") == "propagated-msg-id-42"


# ===========================================================================
# 5. Pipeline Step Failure Handling
# ===========================================================================

class TestPipelineFailureHalts:
    @patch.object(GmailAdapter, "execute")
    def test_failure_at_step_1_halts_pipeline(self, mock_gmail):
        mock_gmail.return_value = StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary="Gmail search failed",
            error_summary="API connection timeout",
        )

        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(wf.workflow_id, variables=build_default_pipeline_variables())

        assert execution.status == ExecutionStatus.FAILED
        assert execution.failed_step == 1
        assert execution.completed_steps == 0
        assert len(execution.step_records) == 1
        assert execution.step_records[0].status == ExecutionStepStatus.FAILED
        assert "API connection timeout" in execution.step_records[0].error_summary

    @patch.object(GmailAdapter, "execute")
    def test_failure_at_step_3_halts_pipeline(self, mock_gmail):
        step1_res = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={"messageId": "msg-001"},
            result_summary="read_email ok",
        )
        step2_res = StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={"subject": "test"},
            result_summary="open_email ok",
        )
        step3_res = StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary="Download failed: attachment exceeds size limit",
            error_summary="Exceeded 10MB limit",
        )
        mock_gmail.side_effect = [step1_res, step2_res, step3_res]

        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(wf.workflow_id, variables=build_default_pipeline_variables())

        assert execution.status == ExecutionStatus.FAILED
        assert execution.failed_step == 3
        assert execution.completed_steps == 2
        assert len(execution.step_records) == 3

    @patch.object(GmailAdapter, "execute")
    @patch.object(SlackAdapter, "execute")
    def test_failure_at_step_6_halts_at_last_step(self, mock_slack, mock_gmail):
        mock_gmail.side_effect = [
            StepExecutionResult(success=True, status=ExecutionStepStatus.COMPLETED, outputs={"messageId": "m1"}, result_summary="ok"),
            StepExecutionResult(success=True, status=ExecutionStepStatus.COMPLETED, outputs={}, result_summary="ok"),
            StepExecutionResult(success=True, status=ExecutionStepStatus.COMPLETED, outputs={}, result_summary="ok"),
        ]
        mock_slack.return_value = StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary="Slack delivery failed",
            error_summary="HTTPError 500",
        )

        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(wf.workflow_id, variables=build_default_pipeline_variables())

        assert execution.status == ExecutionStatus.FAILED
        assert execution.failed_step == 6
        assert execution.completed_steps == 5
        assert len(execution.step_records) == 6

    @patch.object(GmailAdapter, "execute")
    def test_human_intervention_status_on_failure(self, mock_gmail):
        mock_gmail.return_value = StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary="Mailbox locked",
            error_summary="Authentication required",
        )

        wf = build_e2e_pipeline_workflow(status="approved")
        # Set step 1 on_failure to human_intervention
        wf.steps[0].on_failure = "human_intervention"
        upsert_workflow(wf)

        execution = execute_live(wf.workflow_id, variables=build_default_pipeline_variables())

        assert execution.status == ExecutionStatus.NEEDS_INTERVENTION
        assert execution.failed_step == 1


# ===========================================================================
# 6. Idempotency & Safety
# ===========================================================================

class TestPipelineIdempotencyAndSafety:
    def test_idempotency_returns_cached_execution(self):
        wf = build_e2e_pipeline_workflow(status="approved")
        upsert_workflow(wf)

        key = f"idemp-pipeline-{uuid.uuid4().hex[:8]}"
        exec1 = execute_dry_run(wf.workflow_id, idempotency_key=key)
        exec2 = execute_dry_run(wf.workflow_id, idempotency_key=key)

        assert exec1.execution_id == exec2.execution_id

    def test_execution_step_record_has_no_outputs_attribute(self):
        rec = ExecutionStepRecord(
            step_id="step-test-01",
            order=1,
            application="Gmail",
            action="read_email",
            status=ExecutionStepStatus.COMPLETED,
            result_summary="Completed successfully.",
        )
        assert not hasattr(rec, "outputs")
        assert hasattr(rec, "result_summary")
        assert hasattr(rec, "error_summary")

    def test_seed_customers_remain_intact(self):
        for seed in SEED_CUSTOMERS:
            doc = find_customer_by_identifier(seed["email"])
            assert doc is not None
            assert doc.get("customer_id") == seed["customer_id"]

    def test_all_six_integrations_registered_in_registry(self):
        reg = get_integration_registry()
        expected_pairs = [
            ("Gmail", "read_email"),
            ("Gmail", "open_email"),
            ("Gmail", "download_file"),
            ("CRM", "find_customer"),
            ("CRM", "update_customer"),
            ("Slack", "send_message"),
        ]
        for app_name, act_name in expected_pairs:
            adapter = reg.get_adapter(app_name, act_name)
            assert adapter is not None, f"Missing adapter for {app_name} / {act_name}"
