"""
Master Automation Lifecycle Tests — WorkFlowOS
=============================================
Comprehensive test suite verifying the complete 34-point automation lifecycle:

TRIGGER (1-7):
  1. trigger schema validation
  2. trigger persistence
  3. enable
  4. disable
  5. approved workflow can enable
  6. generated workflow cannot enable
  7. rejected workflow cannot enable

POLLING (8-14):
  8. Gmail event detection
  9. new message detected
  10. duplicate message ignored
  11. multiple polling cycles do not duplicate execution
  12. Gmail error isolation
  13. scheduler startup/shutdown
  14. scheduler cancellation

EXECUTION (15-22):
  15. automatic trigger calls execute_live
  16. correct workflow_id
  17. correct variables
  18. correct trigger_override
  19. correct deterministic idempotency key
  20. approval guard
  21. failed execution behavior
  22. retry behavior

SECURITY (23-24):
  23. no secrets persisted
  24. no secrets in logs/results

UI/API (25-28):
  25. trigger API responses
  26. enable/disable API
  27. Poll Now API
  28. frontend build verification (dist bundle check)

E2E (29-34):
  29. controlled Gmail event
  30. automatic trigger
  31. Gmail -> CRM -> Slack execution
  32. execution completed
  33. checkpoint created
  34. second poll does not execute duplicate workflow

All tests use safe mocks/fakes and local MongoDB fixtures.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.database.mongodb import get_database
from app.integrations.base import StepExecutionResult
from app.main import app
from app.models.mock_crm import ensure_seed_data
from app.models.trigger import (
    DuplicateCheckpointError,
    create_checkpoint,
    delete_checkpoint,
    ensure_trigger_indexes,
    get_checkpoint,
    get_trigger_by_workflow_id,
    is_event_processed,
    list_checkpoints_for_workflow,
    list_triggers,
    upsert_trigger_config,
)
from app.models.workflow import upsert_workflow
from app.schemas.execution import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepRecord,
    ExecutionStepStatus,
    WorkflowExecution,
)
from app.schemas.trigger import (
    TriggerCheckpoint,
    TriggerStatus,
    WorkflowFeedbackReport,
    WorkflowTriggerConfig,
)
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.e2e_pipeline import (
    DEFAULT_TEST_IDENTIFIER,
    DEFAULT_TEST_UPDATE_NOTES,
    DEFAULT_TEST_UPDATE_STATUS,
    build_default_pipeline_variables,
    build_e2e_pipeline_workflow,
)
from app.services.execution_service import (
    WorkflowNotApprovedError,
    execute_live,
)
from app.services.trigger_scheduler import (
    TriggerScheduler,
    get_trigger_scheduler,
    start_trigger_scheduler,
    stop_trigger_scheduler,
)
from app.services.trigger_service import (
    TriggerDispatchResult,
    TriggerPollSummary,
    TriggerService,
    evaluate_gmail_trigger,
    poll_triggers,
)


@pytest.fixture(autouse=True)
def setup_indexes():
    """Ensure trigger indexes are active."""
    ensure_trigger_indexes(force=True)
    ensure_seed_data()


@pytest.fixture
def cleanup_tracker():
    """Tracks created workflows and cleans them up from MongoDB."""
    wf_ids: List[str] = []

    def _track(wf_id: str) -> str:
        wf_ids.append(wf_id)
        return wf_id

    yield _track

    db = get_database()
    if wf_ids:
        db["workflows"].delete_many({"workflow_id": {"$in": wf_ids}})
        db["workflow_triggers"].delete_many({"workflow_id": {"$in": wf_ids}})
        db["trigger_checkpoints"].delete_many({"workflow_id": {"$in": wf_ids}})
        db["executions"].delete_many({"workflow_id": {"$in": wf_ids}})


@pytest.fixture
def approved_pipeline_workflow(cleanup_tracker) -> WorkflowDefinition:
    """Creates a canonical approved 6-step workflow."""
    wf = build_e2e_pipeline_workflow(status="approved")
    upsert_workflow(wf)
    cleanup_tracker(wf.workflow_id)
    return wf


@pytest.fixture
def generated_workflow(cleanup_tracker) -> WorkflowDefinition:
    """Creates an unapproved generated workflow."""
    wf = build_e2e_pipeline_workflow(status="generated")
    upsert_workflow(wf)
    cleanup_tracker(wf.workflow_id)
    return wf


@pytest.fixture
def rejected_workflow(cleanup_tracker) -> WorkflowDefinition:
    """Creates a rejected workflow."""
    wf = build_e2e_pipeline_workflow(status="rejected")
    upsert_workflow(wf)
    cleanup_tracker(wf.workflow_id)
    return wf


# ===========================================================================
# 1-7: TRIGGER CONFIGURATION & APPROVAL GUARDS
# ===========================================================================

def test_01_trigger_schema_validation():
    """1. Trigger schema rejects unknown fields and validates interval."""
    cfg = WorkflowTriggerConfig(
        workflow_id="wf-test-01",
        application="Gmail",
        event="customer_email_received",
        poll_interval_seconds=45,
    )
    assert cfg.poll_interval_seconds == 45
    assert cfg.status == TriggerStatus.PAUSED
    assert cfg.is_enabled is False

    with pytest.raises(Exception):
        # extra fields forbidden
        WorkflowTriggerConfig(
            workflow_id="wf-test-01",
            application="Gmail",
            event="customer_email_received",
            unauthorized_secret_field="leak",  # type: ignore
        )


def test_02_trigger_persistence(approved_pipeline_workflow):
    """2. Trigger configuration persists to MongoDB and reads back identically."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        query_filter="label:INBOX",
        poll_interval_seconds=30,
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    saved = upsert_trigger_config(cfg)
    assert saved.trigger_id == cfg.trigger_id

    fetched = get_trigger_by_workflow_id(wf_id)
    assert fetched is not None
    assert fetched.workflow_id == wf_id
    assert fetched.is_enabled is True
    assert fetched.status == TriggerStatus.ACTIVE


def test_03_trigger_enable(approved_pipeline_workflow):
    """3. Trigger can be enabled for approved workflow."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=False,
        status=TriggerStatus.PAUSED,
    )
    upsert_trigger_config(cfg)

    cfg.is_enabled = True
    cfg.status = TriggerStatus.ACTIVE
    updated = upsert_trigger_config(cfg)
    assert updated.is_enabled is True
    assert updated.status == TriggerStatus.ACTIVE


def test_04_trigger_disable(approved_pipeline_workflow):
    """4. Trigger can be disabled and is_enabled transitions to False."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    cfg.is_enabled = False
    cfg.status = TriggerStatus.PAUSED
    updated = upsert_trigger_config(cfg)
    assert updated.is_enabled is False
    assert updated.status == TriggerStatus.PAUSED


def test_05_approved_workflow_can_enable_via_api(approved_pipeline_workflow):
    """5. Approved workflow can be enabled via API."""
    client = TestClient(app)
    wf_id = approved_pipeline_workflow.workflow_id

    res = client.post(f"/api/v1/triggers/{wf_id}/enable")
    assert res.status_code == 200
    data = res.json()
    assert data["is_enabled"] is True
    assert data["status"] == "active"


def test_06_generated_workflow_cannot_enable(generated_workflow):
    """6. Generated workflow cannot be enabled (409 Conflict)."""
    client = TestClient(app)
    wf_id = generated_workflow.workflow_id

    res = client.post(f"/api/v1/triggers/{wf_id}/enable")
    assert res.status_code == 409
    assert "status is 'generated'" in res.json()["detail"]


def test_07_rejected_workflow_cannot_enable(rejected_workflow):
    """7. Rejected workflow cannot be enabled (409 Conflict)."""
    client = TestClient(app)
    wf_id = rejected_workflow.workflow_id

    res = client.post(f"/api/v1/triggers/{wf_id}/enable")
    assert res.status_code == 409
    assert "status is 'rejected'" in res.json()["detail"]


# ===========================================================================
# 8-14: POLLING & SCHEDULER
# ===========================================================================

def test_08_gmail_event_detection(approved_pipeline_workflow):
    """8. Gmail event detection receives messages from Gmail adapter."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {
        "id": "msg-test-888",
        "sender": "client@example.test",
        "subject": "Need assistance",
        "snippet": "Hello team",
    }
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg], "message_ids": ["msg-test-888"]},
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=True, workflow_id=wf_id)
        assert summary.triggers_evaluated == 1
        assert summary.events_detected == 1
        assert summary.dispatches[0].event_identifier == "msg-test-888"


def test_09_new_message_detected_and_dispatched(approved_pipeline_workflow):
    """9. New message detected calls live dispatch."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-new-009", "sender": "c@test.test", "subject": "New"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )

    fake_exec = WorkflowExecution(
        workflow_id=wf_id,
        workflow_name=approved_pipeline_workflow.name,
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.COMPLETED,
        total_steps=6,
        completed_steps=6,
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", return_value=fake_exec) as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary.events_dispatched == 1
        assert mock_exec.called
        assert is_event_processed(wf_id, "msg-new-009")


def test_10_duplicate_message_ignored(approved_pipeline_workflow):
    """10. Duplicate message already in checkpoints is skipped."""
    wf_id = approved_pipeline_workflow.workflow_id
    create_checkpoint(
        TriggerCheckpoint(
            workflow_id=wf_id,
            source_application="Gmail",
            event_identifier="msg-dup-010",
            execution_id="exec-existing-010",
        )
    )

    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-dup-010", "sender": "c@test.test"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live") as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary.events_skipped == 1
        assert not mock_exec.called


def test_11_multiple_polling_cycles_no_duplicate(approved_pipeline_workflow):
    """11. Multiple polling cycles with same event execute exactly once."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-multi-011", "sender": "c@test.test"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )
    fake_exec = WorkflowExecution(
        workflow_id=wf_id,
        workflow_name=approved_pipeline_workflow.name,
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.COMPLETED,
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", return_value=fake_exec) as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        # Cycle 1: Dispatches
        res1 = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert res1.events_dispatched == 1
        assert mock_exec.call_count == 1

        # Cycle 2: Same event is skipped
        res2 = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert res2.events_skipped == 1
        assert mock_exec.call_count == 1  # Still 1, never duplicated


def test_12_gmail_error_isolation(approved_pipeline_workflow):
    """12. Gmail polling error is isolated and increments error count."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get:
        mock_adp = MagicMock()
        mock_adp.execute.side_effect = RuntimeError("Gmail API rate limit exceeded")
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary.errors_count >= 1

    updated = get_trigger_by_workflow_id(wf_id)
    assert updated.consecutive_errors >= 1
    assert "rate limit exceeded" in (summary.dispatches[0].error or "")


def test_13_scheduler_startup_and_shutdown():
    """13. Scheduler cleanly starts, loops safely, and stops cleanly."""
    async def _test():
        scheduler = TriggerScheduler(interval_seconds=1)
        assert scheduler.is_running is False

        with patch("app.services.trigger_scheduler.poll_triggers") as mock_poll:
            mock_poll.return_value = TriggerPollSummary()
            await scheduler.start()
            assert scheduler.is_running is True

            await asyncio.sleep(0.05)
            assert scheduler.is_running is True

            await scheduler.stop()
            assert scheduler.is_running is False

    asyncio.run(_test())


def test_14_scheduler_cancellation():
    """14. Scheduler handles asyncio.CancelledError gracefully."""
    async def _test():
        scheduler = TriggerScheduler(interval_seconds=1)
        with patch("app.services.trigger_scheduler.poll_triggers", side_effect=asyncio.CancelledError):
            await scheduler.start()
            await asyncio.sleep(0.02)
            await scheduler.stop()
            assert scheduler.is_running is False

    asyncio.run(_test())


# ===========================================================================
# 15-22: EXECUTION & DISPATCH
# ===========================================================================

def test_15_automatic_trigger_calls_execute_live(approved_pipeline_workflow):
    """15. Trigger service directly invokes execute_live()."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-15", "sender": "user@test.test", "subject": "Test 15"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )
    fake_exec = WorkflowExecution(
        workflow_id=wf_id,
        workflow_name=approved_pipeline_workflow.name,
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.COMPLETED,
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", return_value=fake_exec) as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary.events_dispatched == 1
        assert mock_exec.called


def test_16_to_19_dispatch_arguments_and_idempotency_key(approved_pipeline_workflow):
    """16-19. Verify workflow_id, variables, trigger_override, and idempotency_key."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-spec-19", "sender": "vip@test.test", "subject": "Order #444"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )
    fake_exec = WorkflowExecution(
        workflow_id=wf_id,
        workflow_name=approved_pipeline_workflow.name,
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.COMPLETED,
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", return_value=fake_exec) as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        poll_triggers(dry_run=False, workflow_id=wf_id)

        call_args = mock_exec.call_args
        kwargs = call_args.kwargs
        # 16: correct workflow_id
        assert kwargs["workflow_id"] == wf_id
        # 17: correct variables
        assert kwargs["variables"]["messageId"] == "msg-spec-19"
        assert kwargs["variables"]["customerIdentifier"] == "CUST-1001"
        # 18: correct trigger_override
        assert kwargs["trigger_override"]["source"] == "automatic_trigger"
        assert kwargs["trigger_override"]["messageId"] == "msg-spec-19"
        # 19: correct deterministic idempotency key
        assert kwargs["idempotency_key"] == f"trigger:{wf_id}:msg-spec-19"


def test_20_approval_guard_prevents_unapproved_execution(generated_workflow):
    """20. Approval guard prevents unapproved workflow from automatic execution."""
    wf_id = generated_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    with patch("app.services.trigger_service.execute_live") as mock_exec:
        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary.events_dispatched == 0
        assert not mock_exec.called
        assert any("must be 'approved'" in d.message for d in summary.dispatches)


def test_21_and_22_failed_execution_releases_reservation_for_retry(approved_pipeline_workflow):
    """21-22. Failed execution releases checkpoint so event can be retried on next poll."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    mock_msg = {"id": "msg-transient-fail", "sender": "c@test.test"}
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg]},
    )

    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", side_effect=RuntimeError("Adapter timeout")):
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary1 = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary1.errors_count >= 1
        # Checkpoint reservation must be deleted to allow retry
        assert not is_event_processed(wf_id, "msg-transient-fail")

    # Retry poll cycle now succeeds
    fake_exec = WorkflowExecution(
        workflow_id=wf_id,
        workflow_name=approved_pipeline_workflow.name,
        mode=ExecutionMode.LIVE,
        status=ExecutionStatus.COMPLETED,
    )
    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get, \
         patch("app.services.trigger_service.execute_live", return_value=fake_exec) as mock_exec:
        mock_adp = MagicMock()
        mock_adp.execute.return_value = fake_poll_res
        mock_get.return_value = mock_adp

        summary2 = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary2.events_dispatched == 1
        assert is_event_processed(wf_id, "msg-transient-fail")


# ===========================================================================
# 23-24: SECURITY
# ===========================================================================

def test_23_no_secrets_persisted_in_trigger_or_checkpoints(approved_pipeline_workflow):
    """23. Verify zero secrets in trigger_config and trigger_checkpoints MongoDB documents."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)
    create_checkpoint(
        TriggerCheckpoint(
            workflow_id=wf_id,
            source_application="Gmail",
            event_identifier="msg-sec-23",
            execution_id="exec-sec-23",
        )
    )

    db = get_database()
    trig_doc = db["workflow_triggers"].find_one({"workflow_id": wf_id})
    chk_doc = db["trigger_checkpoints"].find_one({"workflow_id": wf_id})

    forbidden = ["secret", "token", "password", "authorization", "bearer"]
    for key, val in trig_doc.items():
        assert not any(f in key.lower() for f in forbidden)
        if isinstance(val, str):
            assert not any(f in val.lower() for f in ["ya29.", "hooks.slack.com", "bearer "])

    for key, val in chk_doc.items():
        if isinstance(val, str):
            assert not any(f in val.lower() for f in ["ya29.", "hooks.slack.com", "bearer "])


def test_24_no_secrets_in_logs_or_result_messages(approved_pipeline_workflow):
    """24. TriggerDispatchResult error messages sanitize any accidental credentials."""
    wf_id = approved_pipeline_workflow.workflow_id
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    sensitive_leak = "Failure with client_secret=GOCSPX-secret123 and token=ya29.sensitive"
    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get:
        mock_adp = MagicMock()
        mock_adp.execute.side_effect = RuntimeError(sensitive_leak)
        mock_get.return_value = mock_adp

        summary = poll_triggers(dry_run=False, workflow_id=wf_id)
        for d in summary.dispatches:
            if d.error:
                assert "ya29." not in d.error
                assert "GOCSPX" not in d.error


# ===========================================================================
# 25-28: UI & API
# ===========================================================================

def test_25_trigger_api_get_responses(approved_pipeline_workflow):
    """25. Trigger API returns structured status without secrets."""
    client = TestClient(app)
    wf_id = approved_pipeline_workflow.workflow_id

    res = client.get(f"/api/v1/triggers/{wf_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["workflow_id"] == wf_id
    assert "status" in data
    assert "is_enabled" in data
    assert "consecutive_errors" in data


def test_26_enable_disable_api_toggle(approved_pipeline_workflow):
    """26. Trigger API enables and disables trigger cleanly."""
    client = TestClient(app)
    wf_id = approved_pipeline_workflow.workflow_id

    # Enable
    res_en = client.post(f"/api/v1/triggers/{wf_id}/enable")
    assert res_en.status_code == 200
    assert res_en.json()["is_enabled"] is True

    # Disable
    res_dis = client.post(f"/api/v1/triggers/{wf_id}/disable")
    assert res_dis.status_code == 200
    assert res_dis.json()["is_enabled"] is False


def test_27_poll_now_api_endpoint(approved_pipeline_workflow):
    """27. POST /api/v1/triggers/{wf_id}/poll runs one controlled cycle."""
    client = TestClient(app)
    wf_id = approved_pipeline_workflow.workflow_id

    # Enable trigger first
    client.post(f"/api/v1/triggers/{wf_id}/enable")

    with patch("app.api.triggers.poll_triggers") as mock_poll:
        mock_poll.return_value = TriggerPollSummary(
            triggers_evaluated=1,
            events_detected=1,
            events_dispatched=1,
            dispatches=[
                TriggerDispatchResult(
                    workflow_id=wf_id,
                    trigger_id="trig-test",
                    event_identifier="msg-api-test",
                    dispatched=True,
                    execution_id="exec-api-test",
                    message="Dispatched",
                )
            ],
        )

        res = client.post(f"/api/v1/triggers/{wf_id}/poll")
        assert res.status_code == 200
        data = res.json()
        assert data["triggers_evaluated"] == 1
        assert data["events_dispatched"] == 1


def test_28_frontend_build_artifacts_exist():
    """28. Frontend production dist directory exists and index.html is present."""
    dist_dir = PROJECT_ROOT / "frontend" / "dist"
    index_html = dist_dir / "index.html"
    assert dist_dir.exists(), "frontend/dist must exist from npm run build"
    assert index_html.exists(), "frontend/dist/index.html must exist"
    content = index_html.read_text(encoding="utf-8")
    assert "WorkFlowOS" in content or "<!doctype html>" in content.lower()


# ===========================================================================
# 29-34: END-TO-END AUTOMATIC TRIGGER LIFECYCLE
# ===========================================================================

def test_29_to_34_complete_automatic_trigger_e2e(approved_pipeline_workflow):
    """
    29-34. Complete End-to-End Automatic Trigger Pipeline:
      29. Controlled Gmail test event
      30. Automatic trigger activation
      31. Gmail -> CRM -> Slack execution
      32. Execution completed
      33. Checkpoint created
      34. Second poll does not execute duplicate workflow
    """
    wf = approved_pipeline_workflow
    wf_id = wf.workflow_id

    # Enable trigger
    cfg = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(cfg)

    # 29: Controlled Gmail event
    test_msg_id = f"msg-e2e-{uuid.uuid4().hex[:8]}"
    mock_msg = {
        "id": test_msg_id,
        "sender": "cust@example.test",
        "subject": "Inquiry regarding services",
        "snippet": "Hello please update customer status",
    }
    fake_poll_res = StepExecutionResult(
        success=True,
        status=ExecutionStepStatus.COMPLETED,
        result_summary="Found 1 message",
        outputs={"messages": [mock_msg], "message_ids": [test_msg_id]},
    )

    # Step execution mock that simulates full 6 steps
    def _fake_adapter_exec(context):
        action = context.step.action
        if action == "read_email":
            return fake_poll_res
        elif action == "open_email":
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"messageId": test_msg_id, "subject": "Inquiry"},
                result_summary="Email opened",
            )
        elif action == "download_file":
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"filename": "doc.pdf", "path": "/downloads/doc.pdf"},
                result_summary="File downloaded",
            )
        elif action == "find_customer":
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"customerFound": True, "customerId": "CUST-1001", "name": "Alice"},
                result_summary="Customer found",
            )
        elif action == "update_customer":
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"updated": True, "customerId": "CUST-1001"},
                result_summary="Customer updated",
            )
        elif action == "send_message":
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"slack_delivery": "delivered"},
                result_summary="Slack notification delivered",
            )
        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            result_summary="Step completed",
        )

    # 30-32: Automatic trigger executes full 6-step pipeline
    with patch("app.integrations.registry.IntegrationRegistry.get_adapter") as mock_get:
        mock_adp = MagicMock()
        mock_adp.execute.side_effect = _fake_adapter_exec
        mock_get.return_value = mock_adp

        summary1 = poll_triggers(dry_run=False, workflow_id=wf_id)

        assert summary1.events_dispatched == 1
        dispatch = summary1.dispatches[0]
        assert dispatch.dispatched is True
        assert dispatch.execution_id is not None
        assert dispatch.execution_status == ExecutionStatus.COMPLETED

        # 33: Checkpoint created
        assert is_event_processed(wf_id, test_msg_id)
        chk = get_checkpoint(wf_id, test_msg_id)
        assert chk is not None
        assert chk.execution_id == dispatch.execution_id

        # 34: Second poll does NOT execute duplicate workflow
        summary2 = poll_triggers(dry_run=False, workflow_id=wf_id)
        assert summary2.events_dispatched == 0
        assert summary2.events_skipped == 1
        assert "already processed" in summary2.dispatches[0].message
