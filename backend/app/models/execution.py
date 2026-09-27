"""
Execution Storage — Phase 8 Step 8.1
====================================
MongoDB persistence for WorkflowExecution documents.

Collection: executions

Indexes:
    - execution_id (unique)       — primary execution lookup key
    - workflow_id                 — lookup runs by workflow
    - status                      — filter by execution status
    - created_at (descending)     — chronological run history
    - idempotency_key (sparse/u) — prevent duplicate executions when provided

Safe and non-destructive:
    - Uses existing MongoDB connection from app.database.mongodb
    - Never stores credentials or authorization headers
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.execution import (
    ExecutionStatus,
    ExecutionStepRecord,
    WorkflowExecution,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "executions"
_indexes_created: bool = False


# ---------------------------------------------------------------------------
# Storage Exceptions
# ---------------------------------------------------------------------------

class ExecutionStorageError(Exception):
    """Base error for execution storage failures."""


class ExecutionNotFoundError(ExecutionStorageError):
    """Raised when an execution_id cannot be found in MongoDB."""


class ExecutionConflictError(ExecutionStorageError):
    """Raised when an execution conflict occurs (e.g. invalid state transition)."""


# ---------------------------------------------------------------------------
# Collection & Index Management
# ---------------------------------------------------------------------------

def _get_collection() -> Collection:
    """Return the executions collection, ensuring required indexes exist."""
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    global _indexes_created
    if not _indexes_created:
        try:
            col.create_index(
                [("execution_id", ASCENDING)],
                name="idx_execution_id",
                unique=True,
            )
            col.create_index(
                [("workflow_id", ASCENDING)],
                name="idx_workflow_id",
            )
            col.create_index(
                [("status", ASCENDING)],
                name="idx_status",
            )
            col.create_index(
                [("created_at", DESCENDING)],
                name="idx_created_at",
            )
            col.create_index(
                [("idempotency_key", ASCENDING)],
                name="idx_idempotency_key",
                unique=True,
                partialFilterExpression={"idempotency_key": {"$type": "string"}},
            )
            _indexes_created = True
            logger.debug("executions indexes ensured.")
        except PyMongoError as exc:
            logger.warning("Could not create execution indexes: %s", exc)
    return col


# ---------------------------------------------------------------------------
# Write Operations
# ---------------------------------------------------------------------------

def insert_execution(execution: WorkflowExecution) -> str:
    """
    Insert a new WorkflowExecution document into the executions collection.

    Returns:
        The execution_id of the created record.

    Raises:
        ExecutionConflictError: If execution_id or idempotency_key already exists.
        ExecutionStorageError: On database failure.
    """
    col = _get_collection()
    doc = execution.model_dump()
    if doc.get("idempotency_key") is None:
        doc.pop("idempotency_key", None)

    try:
        col.insert_one(doc)
        logger.info(
            "Inserted execution record %s for workflow %s (status=%s, mode=%s).",
            execution.execution_id,
            execution.workflow_id,
            execution.status.value,
            execution.mode.value,
        )
        return execution.execution_id
    except PyMongoError as exc:
        err_msg = str(exc)
        if "duplicate key error" in err_msg.lower():
            logger.warning("Duplicate execution key: %s", exc)
            raise ExecutionConflictError(
                f"Execution with duplicate key already exists: {exc}"
            ) from exc
        logger.error("Failed to insert execution record: %s", exc)
        raise ExecutionStorageError(f"Execution insert failed: {exc}") from exc


def save_execution(execution: WorkflowExecution) -> WorkflowExecution:
    """
    Save or replace the full execution record, updating updated_at.

    Returns:
        The updated WorkflowExecution instance.

    Raises:
        ExecutionNotFoundError: If the execution does not exist.
        ExecutionStorageError: On database failure.
    """
    col = _get_collection()
    now = datetime.now(timezone.utc)
    execution.updated_at = now
    doc = execution.model_dump()
    if doc.get("idempotency_key") is None:
        doc.pop("idempotency_key", None)

    try:
        result = col.replace_one(
            {"execution_id": execution.execution_id},
            doc,
            upsert=False,
        )
        if result.matched_count == 0:
            raise ExecutionNotFoundError(
                f"Execution '{execution.execution_id}' not found for update."
            )
        return execution
    except PyMongoError as exc:
        logger.error("Failed to save execution %s: %s", execution.execution_id, exc)
        raise ExecutionStorageError(f"Execution save failed: {exc}") from exc


def update_execution_status(
    execution_id: str,
    status: ExecutionStatus,
    current_step: Optional[int] = None,
    completed_steps: Optional[int] = None,
    failed_step: Optional[int] = None,
    error_information: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> WorkflowExecution:
    """
    Atomically update the lifecycle status and progress of an execution record.

    Returns:
        The updated WorkflowExecution.
    """
    col = _get_collection()
    now = datetime.now(timezone.utc)

    update_fields: Dict[str, Any] = {
        "status": status.value,
        "updated_at": now,
    }
    if current_step is not None:
        update_fields["current_step"] = current_step
    if completed_steps is not None:
        update_fields["completed_steps"] = completed_steps
    if failed_step is not None:
        update_fields["failed_step"] = failed_step
    if error_information is not None:
        update_fields["error_information"] = error_information
    if started_at is not None:
        update_fields["started_at"] = started_at
    if completed_at is not None:
        update_fields["completed_at"] = completed_at

    try:
        result = col.update_one(
            {"execution_id": execution_id},
            {"$set": update_fields},
        )
        if result.matched_count == 0:
            raise ExecutionNotFoundError(f"Execution '{execution_id}' not found.")

        updated_doc = col.find_one({"execution_id": execution_id})
        if updated_doc:
            updated_doc.pop("_id", None)
            return WorkflowExecution.model_validate(updated_doc)
        raise ExecutionNotFoundError(f"Execution '{execution_id}' not found.")
    except PyMongoError as exc:
        logger.error("Failed to update status for execution %s: %s", execution_id, exc)
        raise ExecutionStorageError(f"Execution status update failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Read Operations
# ---------------------------------------------------------------------------

def get_execution_by_id(execution_id: str) -> Optional[WorkflowExecution]:
    """Retrieve an execution record by execution_id, or None if not found."""
    col = _get_collection()
    try:
        doc = col.find_one({"execution_id": execution_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowExecution.model_validate(doc)
    except PyMongoError as exc:
        logger.error("Failed to fetch execution %s: %s", execution_id, exc)
        raise ExecutionStorageError(f"Execution fetch failed: {exc}") from exc


def get_execution_by_idempotency_key(idempotency_key: str) -> Optional[WorkflowExecution]:
    """Retrieve an execution record by idempotency_key, or None if not found."""
    if not idempotency_key:
        return None
    col = _get_collection()
    try:
        doc = col.find_one({"idempotency_key": idempotency_key})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowExecution.model_validate(doc)
    except PyMongoError as exc:
        logger.error(
            "Failed to fetch execution by idempotency_key %s: %s",
            idempotency_key,
            exc,
        )
        raise ExecutionStorageError(f"Execution lookup failed: {exc}") from exc


def list_executions(
    workflow_id: Optional[str] = None,
    limit: int = 50,
) -> List[WorkflowExecution]:
    """
    List execution records, newest first.

    Args:
        workflow_id: Optional filter for a specific workflow.
        limit: Maximum number of records to return (default: 50).

    Returns:
        List of WorkflowExecution records.
    """
    col = _get_collection()
    query: Dict[str, Any] = {}
    if workflow_id:
        query["workflow_id"] = workflow_id

    try:
        docs = list(
            col.find(query)
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        results = []
        for doc in docs:
            doc.pop("_id", None)
            results.append(WorkflowExecution.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("Failed to list executions: %s", exc)
        raise ExecutionStorageError(f"Execution listing failed: {exc}") from exc
