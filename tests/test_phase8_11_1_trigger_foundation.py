"""
Phase 8.11.1 Tests — Trigger Foundation
=======================================
Unit and integration tests for:
    1. Trigger schema validation (required fields, non-empty validation).
    2. Default values (UUID, poll interval, defaults).
    3. Invalid poll interval rejection (safe minimum enforced).
    4. Trigger persistence (upsert in workflow_triggers collection).
    5. Trigger retrieval (by workflow_id, by trigger_id, list with filters).
    6. Trigger update (field mutation and timestamp refresh).
    7. Enable/disable behavior (status and is_enabled transitions).
    8. Checkpoint persistence (create, check, get, list).
    9. Duplicate checkpoint protection (atomic deduplication guard).
    10. Compound uniqueness (workflow_id + event_identifier).
    11. Zero secrets allowed / persisted (extra="forbid" schema guard).
    12. Idempotent index initialization (repeated calls safe).

Guarantees:
    - Zero network calls to Gmail, Slack, or external APIs.
    - Uses local MongoDB test collections with cleanup.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.database.mongodb import get_database
from app.models.trigger import (
    DuplicateCheckpointError,
    TriggerNotFoundError,
    TriggerStorageError,
    _get_checkpoints_collection,
    _get_triggers_collection,
    create_checkpoint,
    ensure_trigger_indexes,
    get_checkpoint,
    get_trigger_by_id,
    get_trigger_by_workflow_id,
    is_event_processed,
    list_checkpoints_for_workflow,
    list_triggers,
    set_trigger_enabled,
    update_trigger,
    upsert_trigger_config,
)
from app.schemas.trigger import (
    MIN_POLL_INTERVAL_SECONDS,
    TriggerCheckpoint,
    TriggerStatus,
    WorkflowTriggerConfig,
)


# ---------------------------------------------------------------------------
# Fixtures & Cleanup Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_indexes():
    """Ensure trigger and checkpoint indexes are created before each test."""
    ensure_trigger_indexes(force=True)


@pytest.fixture
def unique_workflow_id() -> str:
    """Generate a clean unique workflow ID for test isolation."""
    return f"wf-test-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def cleanup_collections():
    """Cleanup test documents after tests run."""
    created_wf_ids = []

    def _track(wf_id: str) -> str:
        created_wf_ids.append(wf_id)
        return wf_id

    yield _track

    # Post-test cleanup
    db = get_database()
    if created_wf_ids:
        db["workflow_triggers"].delete_many({"workflow_id": {"$in": created_wf_ids}})
        db["trigger_checkpoints"].delete_many({"workflow_id": {"$in": created_wf_ids}})


# ---------------------------------------------------------------------------
# 1. Trigger Schema Validation
# ---------------------------------------------------------------------------

def test_trigger_schema_valid():
    """Test valid trigger configuration passes schema validation."""
    config = WorkflowTriggerConfig(
        workflow_id="wf-001",
        application="Gmail",
        event="customer_email_received",
        query_filter="label:INBOX is:unread",
        poll_interval_seconds=30,
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    assert config.workflow_id == "wf-001"
    assert config.application == "Gmail"
    assert config.event == "customer_email_received"
    assert config.query_filter == "label:INBOX is:unread"
    assert config.poll_interval_seconds == 30
    assert config.is_enabled is True
    assert config.status == TriggerStatus.ACTIVE


def test_trigger_schema_empty_fields_rejected():
    """Empty or whitespace-only required fields must raise ValidationError."""
    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(workflow_id="", application="Gmail", event="email")

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(workflow_id="  ", application="Gmail", event="email")

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(workflow_id="wf-1", application="", event="email")

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(workflow_id="wf-1", application="Gmail", event="")


# ---------------------------------------------------------------------------
# 2. Default Values
# ---------------------------------------------------------------------------

def test_trigger_schema_defaults():
    """Test default values are properly populated on creation."""
    config = WorkflowTriggerConfig(
        workflow_id="wf-defaults",
        application="Gmail",
        event="customer_email_received",
    )
    assert config.trigger_id is not None
    assert len(config.trigger_id) > 10
    assert config.poll_interval_seconds == 30
    assert config.is_enabled is False
    assert config.status == TriggerStatus.PAUSED
    assert config.consecutive_errors == 0
    assert config.last_polled_at is None
    assert config.last_triggered_at is None
    assert isinstance(config.created_at, datetime)
    assert isinstance(config.updated_at, datetime)


# ---------------------------------------------------------------------------
# 3. Invalid Poll Interval Rejection
# ---------------------------------------------------------------------------

def test_trigger_invalid_poll_interval_rejected():
    """Poll interval lower than safe minimum (5s) must be rejected."""
    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(
            workflow_id="wf-fast",
            application="Gmail",
            event="test",
            poll_interval_seconds=0,
        )

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(
            workflow_id="wf-fast",
            application="Gmail",
            event="test",
            poll_interval_seconds=MIN_POLL_INTERVAL_SECONDS - 1,
        )

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(
            workflow_id="wf-fast",
            application="Gmail",
            event="test",
            poll_interval_seconds=-10,
        )

    # Safe minimum boundary value succeeds
    valid_boundary = WorkflowTriggerConfig(
        workflow_id="wf-fast",
        application="Gmail",
        event="test",
        poll_interval_seconds=MIN_POLL_INTERVAL_SECONDS,
    )
    assert valid_boundary.poll_interval_seconds == MIN_POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# 4. Trigger Persistence (Upsert)
# ---------------------------------------------------------------------------

def test_trigger_persistence_upsert(cleanup_collections):
    """Test upserting a trigger config to MongoDB."""
    wf_id = cleanup_collections(f"wf-persist-{uuid.uuid4().hex[:8]}")
    config = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        query_filter="is:unread",
        poll_interval_seconds=45,
    )

    saved = upsert_trigger_config(config)
    assert saved.workflow_id == wf_id
    assert saved.poll_interval_seconds == 45

    # Verify directly in MongoDB collection
    col = _get_triggers_collection()
    raw = col.find_one({"workflow_id": wf_id})
    assert raw is not None
    assert raw["application"] == "Gmail"
    assert raw["poll_interval_seconds"] == 45


# ---------------------------------------------------------------------------
# 5. Trigger Retrieval
# ---------------------------------------------------------------------------

def test_trigger_retrieval(cleanup_collections):
    """Test retrieval by workflow_id, by trigger_id, and list with filters."""
    wf_id = cleanup_collections(f"wf-get-{uuid.uuid4().hex[:8]}")
    config = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=True,
        status=TriggerStatus.ACTIVE,
    )
    upsert_trigger_config(config)

    # Retrieve by workflow_id
    retrieved = get_trigger_by_workflow_id(wf_id)
    assert retrieved is not None
    assert retrieved.workflow_id == wf_id
    assert retrieved.trigger_id == config.trigger_id
    assert retrieved.status == TriggerStatus.ACTIVE

    # Retrieve by trigger_id
    by_tid = get_trigger_by_id(config.trigger_id)
    assert by_tid is not None
    assert by_tid.workflow_id == wf_id

    # Non-existent retrieval returns None
    assert get_trigger_by_workflow_id("wf-non-existent-999") is None
    assert get_trigger_by_id("tid-non-existent-999") is None

    # List triggers with application and is_enabled filter
    triggers = list_triggers(application="Gmail", is_enabled=True)
    assert any(t.workflow_id == wf_id for t in triggers)


# ---------------------------------------------------------------------------
# 6. Trigger Update
# ---------------------------------------------------------------------------

def test_trigger_update(cleanup_collections):
    """Test mutating specific fields and verifying updated_at refresh."""
    wf_id = cleanup_collections(f"wf-upd-{uuid.uuid4().hex[:8]}")
    config = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        poll_interval_seconds=30,
        consecutive_errors=0,
    )
    upsert_trigger_config(config)

    now = datetime.now(timezone.utc)
    updated = update_trigger(
        wf_id,
        {
            "poll_interval_seconds": 60,
            "query_filter": "label:INBOX",
            "consecutive_errors": 2,
            "last_polled_at": now,
        },
    )

    assert updated.poll_interval_seconds == 60
    assert updated.query_filter == "label:INBOX"
    assert updated.consecutive_errors == 2
    assert updated.last_polled_at is not None

    # Updating unknown workflow raises TriggerNotFoundError
    with pytest.raises(TriggerNotFoundError):
        update_trigger("wf-unknown-update-target", {"poll_interval_seconds": 50})


# ---------------------------------------------------------------------------
# 7. Enable / Disable Behavior
# ---------------------------------------------------------------------------

def test_trigger_enable_disable(cleanup_collections):
    """Test toggling trigger automation updates is_enabled and status."""
    wf_id = cleanup_collections(f"wf-toggle-{uuid.uuid4().hex[:8]}")
    config = WorkflowTriggerConfig(
        workflow_id=wf_id,
        application="Gmail",
        event="customer_email_received",
        is_enabled=False,
        status=TriggerStatus.PAUSED,
    )
    upsert_trigger_config(config)

    # Enable
    enabled = set_trigger_enabled(wf_id, True)
    assert enabled.is_enabled is True
    assert enabled.status == TriggerStatus.ACTIVE

    # Disable
    disabled = set_trigger_enabled(wf_id, False)
    assert disabled.is_enabled is False
    assert disabled.status == TriggerStatus.PAUSED


# ---------------------------------------------------------------------------
# 8. Checkpoint Persistence
# ---------------------------------------------------------------------------

def test_checkpoint_persistence(cleanup_collections):
    """Test creating and checking event deduplication checkpoints."""
    wf_id = cleanup_collections(f"wf-chk-{uuid.uuid4().hex[:8]}")
    msg_id = f"msg-{uuid.uuid4().hex[:12]}"
    exec_id = f"exec-{uuid.uuid4().hex[:8]}"

    # Initially event is not processed
    assert is_event_processed(wf_id, msg_id) is False

    # Create checkpoint
    checkpoint = TriggerCheckpoint(
        workflow_id=wf_id,
        source_application="Gmail",
        event_identifier=msg_id,
        execution_id=exec_id,
    )
    saved = create_checkpoint(checkpoint)
    assert saved.workflow_id == wf_id
    assert saved.event_identifier == msg_id

    # Now event is marked processed
    assert is_event_processed(wf_id, msg_id) is True

    # Retrieve checkpoint
    retrieved = get_checkpoint(wf_id, msg_id)
    assert retrieved is not None
    assert retrieved.execution_id == exec_id

    # List checkpoints for workflow
    checkpoints = list_checkpoints_for_workflow(wf_id)
    assert len(checkpoints) == 1
    assert checkpoints[0].event_identifier == msg_id


# ---------------------------------------------------------------------------
# 9. Duplicate Checkpoint Protection
# ---------------------------------------------------------------------------

def test_duplicate_checkpoint_protection(cleanup_collections):
    """Test that creating a duplicate checkpoint raises DuplicateCheckpointError."""
    wf_id = cleanup_collections(f"wf-dup-{uuid.uuid4().hex[:8]}")
    msg_id = f"msg-dup-{uuid.uuid4().hex[:10]}"

    checkpoint = TriggerCheckpoint(
        workflow_id=wf_id,
        source_application="Gmail",
        event_identifier=msg_id,
    )
    create_checkpoint(checkpoint)

    # Re-inserting identical (workflow_id, event_identifier) must raise DuplicateCheckpointError
    with pytest.raises(DuplicateCheckpointError):
        create_checkpoint(checkpoint)


# ---------------------------------------------------------------------------
# 10. workflow_id + event_identifier Compound Uniqueness
# ---------------------------------------------------------------------------

def test_checkpoint_compound_uniqueness(cleanup_collections):
    """
    Test compound uniqueness rules:
    - Same event_identifier with a DIFFERENT workflow_id is permitted.
    - Same workflow_id with a DIFFERENT event_identifier is permitted.
    """
    wf_id_1 = cleanup_collections(f"wf-comp-1-{uuid.uuid4().hex[:8]}")
    wf_id_2 = cleanup_collections(f"wf-comp-2-{uuid.uuid4().hex[:8]}")
    msg_id = f"msg-shared-{uuid.uuid4().hex[:10]}"

    chk_1 = TriggerCheckpoint(
        workflow_id=wf_id_1,
        source_application="Gmail",
        event_identifier=msg_id,
    )
    create_checkpoint(chk_1)

    # Different workflow can process the same event
    chk_2 = TriggerCheckpoint(
        workflow_id=wf_id_2,
        source_application="Gmail",
        event_identifier=msg_id,
    )
    saved_2 = create_checkpoint(chk_2)
    assert saved_2.workflow_id == wf_id_2

    # Same workflow with a different event is permitted
    msg_id_2 = f"msg-distinct-{uuid.uuid4().hex[:10]}"
    chk_3 = TriggerCheckpoint(
        workflow_id=wf_id_1,
        source_application="Gmail",
        event_identifier=msg_id_2,
    )
    saved_3 = create_checkpoint(chk_3)
    assert saved_3.event_identifier == msg_id_2


# ---------------------------------------------------------------------------
# 11. No Secrets Allowed in Trigger / Checkpoint Schemas
# ---------------------------------------------------------------------------

def test_no_secrets_in_trigger_and_checkpoint():
    """Ensure extra/secret fields are strictly forbidden by schema."""
    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(
            workflow_id="wf-sec",
            application="Gmail",
            event="email",
            api_key="super_secret_key",  # Forbidden extra field
        )

    with pytest.raises(ValidationError):
        WorkflowTriggerConfig(
            workflow_id="wf-sec",
            application="Gmail",
            event="email",
            client_secret="secret_oauth_val",  # Forbidden extra field
        )

    with pytest.raises(ValidationError):
        TriggerCheckpoint(
            workflow_id="wf-sec",
            source_application="Gmail",
            event_identifier="msg-001",
            slack_webhook_url="https://hooks.slack.com/...",  # Forbidden extra field
        )


# ---------------------------------------------------------------------------
# 12. Idempotent Index Initialization
# ---------------------------------------------------------------------------

def test_idempotent_index_initialization():
    """Calling ensure_trigger_indexes repeatedly must not raise PyMongo errors."""
    for _ in range(3):
        ensure_trigger_indexes(force=True)

    # Verify indexes exist on workflow_triggers
    triggers_col = _get_triggers_collection()
    triggers_indexes = triggers_col.index_information()
    assert "idx_workflow_id" in triggers_indexes
    assert "idx_enabled_application" in triggers_indexes
    assert "idx_trigger_id" in triggers_indexes

    # Verify indexes exist on trigger_checkpoints
    checkpoints_col = _get_checkpoints_collection()
    checkpoints_indexes = checkpoints_col.index_information()
    assert "idx_wf_event_dedup" in checkpoints_indexes
    assert "idx_processed_at" in checkpoints_indexes
    assert "idx_checkpoint_id" in checkpoints_indexes
