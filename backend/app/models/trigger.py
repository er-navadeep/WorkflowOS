"""
Trigger Storage & Checkpoints — Phase 8.11.1
============================================
MongoDB persistence for WorkflowTriggerConfig and TriggerCheckpoint documents.

Collections:
    - workflow_triggers: Configuration and operational state for workflow triggers.
    - trigger_checkpoints: Deduplication store recording processed external events.

Indexes:
    workflow_triggers:
        - workflow_id (unique)       — primary lookup & single trigger per workflow
        - is_enabled + application   — query index for polling eligible triggers
        - trigger_id (unique)        — secondary key
    trigger_checkpoints:
        - workflow_id + event_identifier (unique compound) — deduplication invariant
        - processed_at (descending)  — chronological audit & cleanup
        - checkpoint_id (unique)     — secondary key

Safety & Security Guarantees:
    - Zero secrets: Never stores credentials, tokens, or webhook URLs.
    - Idempotent indexing: Index initialization can be called repeatedly without errors.
    - Atomic deduplication: Unique compound index enforces that an event is never checkpointed twice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.database.mongodb import get_database
from app.schemas.trigger import (
    TriggerCheckpoint,
    TriggerStatus,
    WorkflowTriggerConfig,
)

logger = logging.getLogger(__name__)

WORKFLOW_TRIGGERS_COLLECTION = "workflow_triggers"
TRIGGER_CHECKPOINTS_COLLECTION = "trigger_checkpoints"

_indexes_created: bool = False


# ---------------------------------------------------------------------------
# Storage Exceptions
# ---------------------------------------------------------------------------

class TriggerStorageError(Exception):
    """Base exception for trigger storage failures."""


class TriggerNotFoundError(TriggerStorageError):
    """Raised when a trigger configuration is not found."""


class DuplicateCheckpointError(TriggerStorageError):
    """Raised when an event has already been checkpointed for a workflow."""


# ---------------------------------------------------------------------------
# Collection & Index Management
# ---------------------------------------------------------------------------

def ensure_trigger_indexes(force: bool = False) -> None:
    """
    Ensure required indexes exist for both trigger collections.
    
    Safe to call multiple times (idempotent).
    """
    global _indexes_created
    if _indexes_created and not force:
        return

    db = get_database()
    try:
        # 1. workflow_triggers indexes
        triggers_col: Collection = db[WORKFLOW_TRIGGERS_COLLECTION]
        triggers_col.create_index(
            [("workflow_id", ASCENDING)],
            name="idx_workflow_id",
            unique=True,
        )
        triggers_col.create_index(
            [("is_enabled", ASCENDING), ("application", ASCENDING)],
            name="idx_enabled_application",
        )
        triggers_col.create_index(
            [("trigger_id", ASCENDING)],
            name="idx_trigger_id",
            unique=True,
        )

        # 2. trigger_checkpoints indexes
        checkpoints_col: Collection = db[TRIGGER_CHECKPOINTS_COLLECTION]
        checkpoints_col.create_index(
            [("workflow_id", ASCENDING), ("event_identifier", ASCENDING)],
            name="idx_wf_event_dedup",
            unique=True,
        )
        checkpoints_col.create_index(
            [("processed_at", DESCENDING)],
            name="idx_processed_at",
        )
        checkpoints_col.create_index(
            [("checkpoint_id", ASCENDING)],
            name="idx_checkpoint_id",
            unique=True,
        )

        _indexes_created = True
        logger.debug("Trigger and checkpoint indexes successfully verified.")
    except PyMongoError as exc:
        logger.warning("Could not ensure trigger indexes: %s", exc)


def _get_triggers_collection() -> Collection:
    ensure_trigger_indexes()
    return get_database()[WORKFLOW_TRIGGERS_COLLECTION]


def _get_checkpoints_collection() -> Collection:
    ensure_trigger_indexes()
    return get_database()[TRIGGER_CHECKPOINTS_COLLECTION]


# ---------------------------------------------------------------------------
# Trigger Configuration Operations
# ---------------------------------------------------------------------------

def upsert_trigger_config(trigger: WorkflowTriggerConfig) -> WorkflowTriggerConfig:
    """
    Create or update a trigger configuration, keyed uniquely on workflow_id.

    Returns:
        The updated WorkflowTriggerConfig.
    """
    col = _get_triggers_collection()
    now = datetime.now(timezone.utc)
    trigger.updated_at = now

    doc = trigger.model_dump()

    try:
        col.update_one(
            {"workflow_id": trigger.workflow_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info(
            "Upserted trigger configuration for workflow %s (enabled=%s, status=%s).",
            trigger.workflow_id,
            trigger.is_enabled,
            trigger.status,
        )
        return trigger
    except PyMongoError as exc:
        logger.error("DB error upserting trigger for workflow %s: %s", trigger.workflow_id, exc)
        raise TriggerStorageError(f"Failed to upsert trigger config: {exc}") from exc


def get_trigger_by_workflow_id(workflow_id: str) -> Optional[WorkflowTriggerConfig]:
    """
    Retrieve a trigger configuration by its target workflow_id.

    Returns:
        WorkflowTriggerConfig if found, None otherwise.
    """
    if not workflow_id or not workflow_id.strip():
        return None

    col = _get_triggers_collection()
    try:
        doc = col.find_one({"workflow_id": workflow_id.strip()})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowTriggerConfig.model_validate(doc)
    except PyMongoError as exc:
        logger.error("DB error retrieving trigger for workflow %s: %s", workflow_id, exc)
        raise TriggerStorageError(f"Failed to get trigger config: {exc}") from exc


def get_trigger_by_id(trigger_id: str) -> Optional[WorkflowTriggerConfig]:
    """
    Retrieve a trigger configuration by its unique trigger_id.

    Returns:
        WorkflowTriggerConfig if found, None otherwise.
    """
    if not trigger_id or not trigger_id.strip():
        return None

    col = _get_triggers_collection()
    try:
        doc = col.find_one({"trigger_id": trigger_id.strip()})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowTriggerConfig.model_validate(doc)
    except PyMongoError as exc:
        logger.error("DB error retrieving trigger by id %s: %s", trigger_id, exc)
        raise TriggerStorageError(f"Failed to get trigger config: {exc}") from exc


def list_triggers(
    application: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[WorkflowTriggerConfig]:
    """
    List trigger configurations with optional filtering.

    Args:
        application: Filter by emitting application (e.g. 'Gmail').
        is_enabled: Filter by active automation status.
        status: Filter by lifecycle status ('active', 'paused', 'error').
        limit: Maximum number of triggers to return.
    """
    col = _get_triggers_collection()
    query: Dict[str, Any] = {}

    if application:
        query["application"] = application.strip()
    if is_enabled is not None:
        query["is_enabled"] = is_enabled
    if status:
        query["status"] = status.strip().lower()

    try:
        cursor = col.find(query).sort("created_at", DESCENDING).limit(limit)
        results: List[WorkflowTriggerConfig] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(WorkflowTriggerConfig.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("DB error listing triggers: %s", exc)
        raise TriggerStorageError(f"Failed to list triggers: {exc}") from exc


def update_trigger(
    workflow_id: str,
    update_fields: Dict[str, Any],
) -> WorkflowTriggerConfig:
    """
    Update specific fields of an existing trigger configuration.

    Args:
        workflow_id: Target workflow ID.
        update_fields: Dictionary of fields to update.

    Returns:
        The updated WorkflowTriggerConfig.

    Raises:
        TriggerNotFoundError: If the trigger does not exist.
        TriggerStorageError: On database error.
    """
    if not workflow_id or not workflow_id.strip():
        raise TriggerNotFoundError("workflow_id must not be empty.")

    col = _get_triggers_collection()
    fields = dict(update_fields)
    fields["updated_at"] = datetime.now(timezone.utc)

    # Prevent overwriting identity keys maliciously
    fields.pop("_id", None)
    fields.pop("workflow_id", None)
    fields.pop("trigger_id", None)

    try:
        result = col.find_one_and_update(
            {"workflow_id": workflow_id.strip()},
            {"$set": fields},
            return_document=True,
        )
        if not result:
            raise TriggerNotFoundError(f"Trigger for workflow '{workflow_id}' not found.")
        result.pop("_id", None)
        return WorkflowTriggerConfig.model_validate(result)
    except TriggerNotFoundError:
        raise
    except PyMongoError as exc:
        logger.error("DB error updating trigger for workflow %s: %s", workflow_id, exc)
        raise TriggerStorageError(f"Failed to update trigger config: {exc}") from exc


def set_trigger_enabled(
    workflow_id: str,
    is_enabled: bool,
) -> WorkflowTriggerConfig:
    """
    Enable or disable automation for a workflow trigger.

    Automatically transitions status:
        is_enabled=True  -> status='active' (unless already in error)
        is_enabled=False -> status='paused'

    Returns:
        The updated WorkflowTriggerConfig.
    """
    new_status = TriggerStatus.ACTIVE.value if is_enabled else TriggerStatus.PAUSED.value
    return update_trigger(
        workflow_id=workflow_id,
        update_fields={
            "is_enabled": is_enabled,
            "status": new_status,
        },
    )


# ---------------------------------------------------------------------------
# Checkpoint Operations
# ---------------------------------------------------------------------------

def is_event_processed(workflow_id: str, event_identifier: str) -> bool:
    """
    Check whether a specific external event has already been checkpointed
    for the given workflow.

    Fast, atomic read using the unique compound index.
    """
    if not workflow_id or not event_identifier:
        return False

    col = _get_checkpoints_collection()
    try:
        count = col.count_documents(
            {
                "workflow_id": workflow_id.strip(),
                "event_identifier": event_identifier.strip(),
            },
            limit=1,
        )
        return count > 0
    except PyMongoError as exc:
        logger.error(
            "DB error checking checkpoint for workflow %s, event %s: %s",
            workflow_id,
            event_identifier,
            exc,
        )
        raise TriggerStorageError(f"Failed to check event checkpoint: {exc}") from exc


def create_checkpoint(checkpoint: TriggerCheckpoint) -> TriggerCheckpoint:
    """
    Atomically record a processed external event.

    Guaranteed deduplication: if the same (workflow_id, event_identifier)
    already exists, DuplicateCheckpointError is raised.

    Returns:
        The recorded TriggerCheckpoint.
    """
    col = _get_checkpoints_collection()
    doc = checkpoint.model_dump()

    try:
        col.insert_one(doc)
        logger.debug(
            "Created trigger checkpoint for workflow %s, event %s (execution=%s).",
            checkpoint.workflow_id,
            checkpoint.event_identifier,
            checkpoint.execution_id,
        )
        return checkpoint
    except DuplicateKeyError as exc:
        logger.warning(
            "Duplicate checkpoint prevented: workflow %s already processed event %s.",
            checkpoint.workflow_id,
            checkpoint.event_identifier,
        )
        raise DuplicateCheckpointError(
            f"Event '{checkpoint.event_identifier}' has already been processed "
            f"for workflow '{checkpoint.workflow_id}'."
        ) from exc
    except PyMongoError as exc:
        logger.error(
            "DB error creating checkpoint for workflow %s, event %s: %s",
            checkpoint.workflow_id,
            checkpoint.event_identifier,
            exc,
        )
        raise TriggerStorageError(f"Failed to create checkpoint: {exc}") from exc


def get_checkpoint(workflow_id: str, event_identifier: str) -> Optional[TriggerCheckpoint]:
    """
    Retrieve a specific checkpoint by workflow_id and event_identifier.
    """
    if not workflow_id or not event_identifier:
        return None

    col = _get_checkpoints_collection()
    try:
        doc = col.find_one({
            "workflow_id": workflow_id.strip(),
            "event_identifier": event_identifier.strip(),
        })
        if not doc:
            return None
        doc.pop("_id", None)
        return TriggerCheckpoint.model_validate(doc)
    except PyMongoError as exc:
        logger.error(
            "DB error retrieving checkpoint for workflow %s, event %s: %s",
            workflow_id,
            event_identifier,
            exc,
        )
        raise TriggerStorageError(f"Failed to get checkpoint: {exc}") from exc


def list_checkpoints_for_workflow(
    workflow_id: str,
    limit: int = 50,
) -> List[TriggerCheckpoint]:
    """
    List recent checkpoints for a workflow, sorted by processed_at descending.
    """
    if not workflow_id or not workflow_id.strip():
        return []

    col = _get_checkpoints_collection()
    try:
        cursor = (
            col.find({"workflow_id": workflow_id.strip()})
            .sort("processed_at", DESCENDING)
            .limit(limit)
        )
        results: List[TriggerCheckpoint] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(TriggerCheckpoint.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("DB error listing checkpoints for workflow %s: %s", workflow_id, exc)
        raise TriggerStorageError(f"Failed to list checkpoints: {exc}") from exc


def update_checkpoint_execution_id(
    workflow_id: str,
    event_identifier: str,
    execution_id: str,
) -> Optional[TriggerCheckpoint]:
    """
    Update a checkpoint record with the completed execution_id.
    """
    if not workflow_id or not event_identifier or not execution_id:
        return None

    col = _get_checkpoints_collection()
    try:
        doc = col.find_one_and_update(
            {
                "workflow_id": workflow_id.strip(),
                "event_identifier": event_identifier.strip(),
            },
            {"$set": {"execution_id": execution_id.strip()}},
            return_document=True,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return TriggerCheckpoint.model_validate(doc)
    except PyMongoError as exc:
        logger.error(
            "DB error updating checkpoint execution_id for workflow %s, event %s: %s",
            workflow_id,
            event_identifier,
            exc,
        )
        raise TriggerStorageError(f"Failed to update checkpoint: {exc}") from exc


def delete_checkpoint(workflow_id: str, event_identifier: str) -> bool:
    """
    Remove a checkpoint for a workflow and event identifier.
    Used to release a reservation if execution dispatch fails.
    """
    if not workflow_id or not event_identifier:
        return False

    col = _get_checkpoints_collection()
    try:
        res = col.delete_one({
            "workflow_id": workflow_id.strip(),
            "event_identifier": event_identifier.strip(),
        })
        return res.deleted_count > 0
    except PyMongoError as exc:
        logger.error(
            "DB error deleting checkpoint for workflow %s, event %s: %s",
            workflow_id,
            event_identifier,
            exc,
        )
        raise TriggerStorageError(f"Failed to delete checkpoint: {exc}") from exc

