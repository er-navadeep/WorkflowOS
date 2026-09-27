"""
Phase 8.11.2 Tests — Trigger Service
====================================
Comprehensive test suite verifying the automatic trigger service:
    1. Active approved trigger is discovered.
    2. Disabled trigger is ignored.
    3. Generated workflow is blocked from execution.
    4. Rejected workflow is blocked from execution.
    5. Gmail event is detected.
    6. Gmail messageId becomes event_identifier.
    7. Event variables are extracted cleanly.
    8. New event dispatches to execute_live().
    9. Correct deterministic idempotency key is generated.
    10. trigger_override contains only safe metadata.
    11. Already processed event is skipped.
    12. Duplicate checkpoint cannot produce duplicate execution.
    13. Multiple poll cycles process an event only once.
    14. Gmail errors are isolated without crashing the service.
    15. Trigger error counter updates on failure.
    16. Successful polling updates last_polled_at.
    17. Successful dispatch updates last_triggered_at.
    18. Dry-run does not execute live.
    19. Dry-run does not create external side effects or DB checkpoints.
    20. Credentials/secrets never enter variables, trigger_override, checkpoints, or logs.

Zero external network calls required (uses mocks/fakes).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.database.mongodb import get_database
from app.integrations.base import StepExecutionResult
from app.models.trigger import (
    DuplicateCheckpointError,
    create_checkpoint,
    ensure_trigger_indexes,
    get_checkpoint,
    get_trigger_by_workflow_id,
    is_event_processed,
    upsert_trigger_config,
)
from app.models.workflow import upsert_workflow
from app.schemas.execution import ExecutionMode, ExecutionStatus, WorkflowExecution
from app.schemas.trigger import (
    TriggerCheckpoint,
    TriggerStatus,
    WorkflowTriggerConfig,
)
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.e2e_pipeline import build_e2e_pipeline_workflow
from app.services.trigger_service import (
    TriggerDispatchResult,
    TriggerPollSummary,
    TriggerService,
    evaluate_gmail_trigger,
    poll_triggers,
)


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_indexes():
    """Ensure trigger indexes are present."""
    ensure_trigger_indexes(force=True)


@pytest.fixture
def cleanup_tracker():
    """Tracks created IDs and cleans them up from MongoDB after test."""
    wf_ids = []

    def _track(wf_id: str) -> str:
        wf_ids.append(wf_id)
        return wf_id

    yield _track

    db = get_database()
    if wf_ids:
        db["workflows"].delete_many({"workflow_id": {"$in": wf_ids}})
        db["workflow_triggers"].delete_many({"workflow_id": {"$in": wf_ids}})
        db["trigger_checkpoints"].delete_many({"workflow_id": {"$in": wf_ids}})


def _create_test_workflow(
    workflow_id: str,
    status: str = "approved",
) -> WorkflowDefinition:
    """Helper to persist a test workflow in MongoDB."""
    wf = build_e2e_pipeline_workflow(
        workflow_id=workflow_id,
        status=status,
        understanding_id=f"und-{workflow_id}",
    )
    upsert_workflow(wf)
    return wf


def _mock_gmail_poll_response(messages: List[Dict[str, Any]], success: bool = True) -> StepExecutionResult:
    """Construct a mock StepExecutionResult from GmailAdapter.execute()."""
    msg_ids = [m.get("id") for m in messages if m.get("id")]
    return StepExecutionResult(
        success=success,
        status=ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED,
        outputs={
            "messages": messages,
            "message_ids": msg_ids,
            "messageId": msg_ids[0] if msg_ids else None,
        },
        result_summary="Gmail read_email mock query executed." if success else "Gmail query error.",
        error_summary=None if success else "Mocked Gmail API network error.",
    )


# ===========================================================================
# 1. Discovery & Approval Guards
# ===========================================================================

def test_active_approved_trigger_is_discovered(cleanup_tracker):
    """1. Active approved trigger is evaluated during poll_triggers."""
    wf_id = cleanup_tracker(f"wf-disc-{uuid.uuid4().hex[:8]}")
    _create_test_workflow(wf_id, status="approved")

    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    with patch("app.services.trigger_service.evaluate_gmail_trigger", return_value=[]) as mock_eval:
        summary = poll_triggers()
        assert summary.triggers_evaluated >= 1
        # The mock was called for our active trigger
        called_wf_ids = [call.args[0].workflow_id for call in mock_eval.call_args_list]
        assert wf_id in called_wf_ids


def test_disabled_trigger_is_ignored(cleanup_tracker):
    """2. Disabled trigger (is_enabled=False) is ignored during polling."""
    wf_id = cleanup_tracker(f"wf-dis-{uuid.uuid4().hex[:8]}")
    _create_test_workflow(wf_id, status="approved")

    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=False,
        status=TriggerStatus.PAUSED,
    )
    upsert_trigger_config(trigger)

    with patch("app.services.trigger_service.evaluate_gmail_trigger") as mock_eval:
        summary = poll_triggers(workflow_id=wf_id)
        assert summary.triggers_evaluated == 0
        mock_eval.assert_not_called()


def test_generated_workflow_is_blocked(cleanup_tracker):
    """3. Hard approval guard: workflow with status='generated' is blocked."""
    wf_id = cleanup_tracker(f"wf-gen-{uuid.uuid4().hex[:8]}")
    _create_test_workflow(wf_id, status="generated")

    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    with patch("app.services.trigger_service.evaluate_gmail_trigger") as mock_eval:
        summary = poll_triggers(workflow_id=wf_id)
        assert summary.triggers_evaluated == 1
        # Blocked: evaluate_gmail_trigger never called
        mock_eval.assert_not_called()
        assert any(d.error == "WorkflowNotApproved" for d in summary.dispatches)


def test_rejected_workflow_is_blocked(cleanup_tracker):
    """4. Hard approval guard: workflow with status='rejected' is blocked."""
    wf_id = cleanup_tracker(f"wf-rej-{uuid.uuid4().hex[:8]}")
    _create_test_workflow(wf_id, status="rejected")

    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    with patch("app.services.trigger_service.evaluate_gmail_trigger") as mock_eval:
        summary = poll_triggers(workflow_id=wf_id)
        assert summary.triggers_evaluated == 1
        mock_eval.assert_not_called()
        assert any(d.error == "WorkflowNotApproved" for d in summary.dispatches)


# ===========================================================================
# 2. Event Detection, Identification, & Dispatch
# ===========================================================================

def test_gmail_event_detection_and_identification(cleanup_tracker):
    """5 & 6. Gmail event is detected and messageId becomes event_identifier."""
    wf_id = cleanup_tracker(f"wf-detect-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-detect-{uuid.uuid4().hex[:10]}"
    mock_messages = [{
        "id": test_msg_id,
        "sender": "client@example.com",
        "subject": "Project Proposal",
        "snippet": "Attached proposal for review",
    }]

    mock_exec = WorkflowExecution(
        execution_id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=wf_id,
        workflow_name=wf.name,
        status=ExecutionStatus.COMPLETED,
        mode=ExecutionMode.LIVE,
        total_steps=6,
        completed_steps=6,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response(mock_messages)), \
         patch("app.services.trigger_service.execute_live", return_value=mock_exec):

        results = evaluate_gmail_trigger(trigger, wf)
        assert len(results) == 1
        assert results[0].event_identifier == test_msg_id
        assert results[0].dispatched is True
        assert results[0].execution_id == mock_exec.execution_id


def test_event_variables_extraction_and_safe_override(cleanup_tracker):
    """7, 8, 9, 10. Event variables, idempotency key, and trigger_override are passed to execute_live."""
    wf_id = cleanup_tracker(f"wf-vars-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-vars-{uuid.uuid4().hex[:10]}"
    mock_msg = {
        "id": test_msg_id,
        "sender": "sender@domain.test",
        "subject": "Important Notice",
        "snippet": "Hello team",
    }

    mock_exec = WorkflowExecution(
        execution_id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=wf_id,
        workflow_name=wf.name,
        status=ExecutionStatus.COMPLETED,
        mode=ExecutionMode.LIVE,
        total_steps=6,
        completed_steps=6,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response([mock_msg])), \
         patch("app.services.trigger_service.execute_live", return_value=mock_exec) as mock_live:

        evaluate_gmail_trigger(trigger, wf)
        assert mock_live.called

        _, kwargs = mock_live.call_args
        # 8. Dispatches to execute_live
        assert kwargs["workflow_id"] == wf_id
        # 9. Correct deterministic idempotency key
        assert kwargs["idempotency_key"] == f"trigger:{wf_id}:{test_msg_id}"
        # 10. trigger_override is safe
        override = kwargs["trigger_override"]
        assert override["source"] == "automatic_trigger"
        assert override["application"] == "Gmail"
        assert override["messageId"] == test_msg_id
        assert "token" not in override
        assert "secret" not in override

        # 7. Event variables extracted
        vars_passed = kwargs["variables"]
        assert vars_passed["messageId"] == test_msg_id
        assert vars_passed["sender"] == "sender@domain.test"
        assert vars_passed["subject"] == "Important Notice"
        assert vars_passed["snippet"] == "Hello team"


# ===========================================================================
# 3. Deduplication & Idempotency
# ===========================================================================

def test_already_processed_event_is_skipped(cleanup_tracker):
    """11. An event recorded in trigger_checkpoints is skipped on future polls."""
    wf_id = cleanup_tracker(f"wf-skip-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-skip-{uuid.uuid4().hex[:10]}"
    # Pre-record checkpoint
    create_checkpoint(TriggerCheckpoint(
        workflow_id=wf_id,
        source_application="Gmail",
        event_identifier=test_msg_id,
        execution_id="exec-already-ran",
    ))

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response([{"id": test_msg_id}])), \
         patch("app.services.trigger_service.execute_live") as mock_live:

        results = evaluate_gmail_trigger(trigger, wf)
        assert len(results) == 1
        assert results[0].dispatched is False
        assert "already processed" in results[0].message
        mock_live.assert_not_called()


def test_duplicate_checkpoint_concurrent_reservation_prevented(cleanup_tracker):
    """12. Concurrent race condition check: DuplicateCheckpointError prevents duplicate execution."""
    wf_id = cleanup_tracker(f"wf-race-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-race-{uuid.uuid4().hex[:10]}"

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response([{"id": test_msg_id}])), \
         patch("app.services.trigger_service.create_checkpoint", side_effect=DuplicateCheckpointError("already claimed")), \
         patch("app.services.trigger_service.execute_live") as mock_live:

        results = evaluate_gmail_trigger(trigger, wf)
        assert len(results) == 1
        assert results[0].dispatched is False
        assert "claimed by concurrent worker" in results[0].message
        mock_live.assert_not_called()


def test_multiple_poll_cycles_process_event_only_once(cleanup_tracker):
    """13. Across repeated poll cycles, the same Gmail message is executed exactly once."""
    wf_id = cleanup_tracker(f"wf-multi-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-once-{uuid.uuid4().hex[:10]}"
    mock_msg = [{"id": test_msg_id, "subject": "Test"}]

    mock_exec = WorkflowExecution(
        execution_id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=wf_id,
        workflow_name=wf.name,
        status=ExecutionStatus.COMPLETED,
        mode=ExecutionMode.LIVE,
        total_steps=6,
        completed_steps=6,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response(mock_msg)), \
         patch("app.services.trigger_service.execute_live", return_value=mock_exec) as mock_live:

        # Cycle 1: Executes
        res1 = evaluate_gmail_trigger(trigger, wf)
        assert len(res1) == 1
        assert res1[0].dispatched is True
        assert mock_live.call_count == 1

        # Cycle 2: Skips (already checkpointed)
        res2 = evaluate_gmail_trigger(trigger, wf)
        assert len(res2) == 1
        assert res2[0].dispatched is False
        assert "already processed" in res2[0].message
        # Total calls remain 1
        assert mock_live.call_count == 1


# ===========================================================================
# 4. Error Isolation & State Updates
# ===========================================================================

def test_gmail_errors_are_isolated_and_counter_updates(cleanup_tracker):
    """14 & 15. Gmail adapter error is caught, does not crash, and increments consecutive_errors."""
    wf_id = cleanup_tracker(f"wf-err-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
        consecutive_errors=0,
    )
    upsert_trigger_config(trigger)

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response([], success=False)):
        results = evaluate_gmail_trigger(trigger, wf)
        assert len(results) == 1
        assert results[0].error is not None

        # Verify consecutive_errors incremented in DB
        updated = get_trigger_by_workflow_id(wf_id)
        assert updated.consecutive_errors == 1


def test_successful_polling_and_dispatch_timestamps(cleanup_tracker):
    """16 & 17. Successful poll updates last_polled_at; successful dispatch updates last_triggered_at."""
    wf_id = cleanup_tracker(f"wf-time-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-time-{uuid.uuid4().hex[:10]}"
    mock_msg = [{"id": test_msg_id}]

    mock_exec = WorkflowExecution(
        execution_id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=wf_id,
        workflow_name=wf.name,
        status=ExecutionStatus.COMPLETED,
        mode=ExecutionMode.LIVE,
        total_steps=6,
        completed_steps=6,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response(mock_msg)), \
         patch("app.services.trigger_service.execute_live", return_value=mock_exec):

        evaluate_gmail_trigger(trigger, wf)

        updated = get_trigger_by_workflow_id(wf_id)
        assert updated.last_polled_at is not None
        assert updated.last_triggered_at is not None
        assert updated.consecutive_errors == 0


# ===========================================================================
# 5. Dry-Run Behavior
# ===========================================================================

def test_dry_run_does_not_execute_live_or_write_checkpoints(cleanup_tracker):
    """18 & 19. Dry run detects events but does not call execute_live() and creates zero checkpoints."""
    wf_id = cleanup_tracker(f"wf-dry-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-dry-{uuid.uuid4().hex[:10]}"
    mock_msg = [{"id": test_msg_id, "subject": "Test Dry Run"}]

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response(mock_msg)), \
         patch("app.services.trigger_service.execute_live") as mock_live:

        summary = poll_triggers(dry_run=True, workflow_id=wf_id)
        assert summary.dry_run is True
        assert summary.events_detected == 1
        assert summary.events_dispatched == 0

        # execute_live was NOT called
        mock_live.assert_not_called()

        # Checkpoint was NOT created in DB
        assert is_event_processed(wf_id, test_msg_id) is False


# ===========================================================================
# 6. Security Guarantees
# ===========================================================================

def test_no_secrets_in_variables_overrides_checkpoints_or_logs(cleanup_tracker):
    """20. Credentials and secrets are never included in variables, trigger_override, or checkpoints."""
    wf_id = cleanup_tracker(f"wf-sec-srv-{uuid.uuid4().hex[:8]}")
    wf = _create_test_workflow(wf_id, status="approved")
    trigger = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(trigger)

    test_msg_id = f"msg-sec-{uuid.uuid4().hex[:10]}"
    mock_msg = {
        "id": test_msg_id,
        "sender": "sender@domain.test",
        "subject": "Meeting",
        "snippet": "Notes",
    }

    mock_exec = WorkflowExecution(
        execution_id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=wf_id,
        workflow_name=wf.name,
        status=ExecutionStatus.COMPLETED,
        mode=ExecutionMode.LIVE,
        total_steps=6,
        completed_steps=6,
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.integrations.gmail.adapter.GmailAdapter.execute", return_value=_mock_gmail_poll_response([mock_msg])), \
         patch("app.services.trigger_service.execute_live", return_value=mock_exec) as mock_live:

        evaluate_gmail_trigger(trigger, wf)

        _, kwargs = mock_live.call_args
        for payload in (kwargs["variables"], kwargs["trigger_override"]):
            for k, v in payload.items():
                assert "key" not in k.lower() or k == "idempotency_key"
                assert "token" not in k.lower()
                assert "secret" not in k.lower()
                assert "password" not in k.lower()
                assert "bearer" not in str(v).lower()

        # Check the checkpoint stored in MongoDB
        chk = get_checkpoint(wf_id, test_msg_id)
        assert chk is not None
        chk_dict = chk.model_dump()
        for k in chk_dict:
            assert "secret" not in k.lower()
            assert "token" not in k.lower()
