"""
Workflow Storage — Phase 6
============================
MongoDB persistence for WorkflowDefinition documents.

Collection: workflows

Uniqueness strategy:
    Each workflow is keyed on understanding_id.
    Re-running generation for the same understanding replaces the existing
    record (upsert on understanding_id).
    This prevents duplicates while allowing regeneration.

Indexes:
    - understanding_id (unique) — primary lookup key
    - workflow_id              — secondary lookup key
    - status                   — filter by lifecycle status
    - created_at               — chronological listing

Phase 6 is additive.  This module does NOT modify:
    - activity_events
    - workflow_candidates
    - workflow_understandings
"""

from __future__ import annotations

import logging
from typing import List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.workflow import WorkflowDefinition

logger = logging.getLogger(__name__)

COLLECTION_NAME = "workflows"

_indexes_created: bool = False


def _get_collection() -> Collection:
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    global _indexes_created
    if not _indexes_created:
        try:
            col.create_index(
                [("understanding_id", ASCENDING)],
                name="idx_understanding_id",
                unique=True,
            )
            col.create_index(
                [("workflow_id", ASCENDING)],
                name="idx_workflow_id",
            )
            col.create_index([("status", ASCENDING)], name="idx_status")
            col.create_index([("created_at", DESCENDING)], name="idx_created_at")
            _indexes_created = True
            logger.debug("workflows indexes ensured.")
        except PyMongoError as exc:
            logger.warning("Could not create workflow indexes: %s", exc)
    return col


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def upsert_workflow(workflow: WorkflowDefinition) -> str:
    """
    Insert or replace the workflow for an understanding.

    If a workflow already exists for understanding_id, it is fully
    replaced (regeneration use-case).

    Returns:
        The workflow_id of the stored document.

    Raises:
        RuntimeError: on MongoDB failure.
    """
    col = _get_collection()
    doc = workflow.model_dump()

    try:
        col.update_one(
            {"understanding_id": workflow.understanding_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info(
            "Upserted workflow %s for understanding %s.",
            workflow.workflow_id,
            workflow.understanding_id,
        )
        return workflow.workflow_id
    except PyMongoError as exc:
        logger.error("Failed to upsert workflow: %s", exc)
        raise RuntimeError(f"Workflow upsert failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def get_workflow_by_id(workflow_id: str) -> Optional[WorkflowDefinition]:
    """Return the stored workflow for a given workflow_id, or None."""
    col = _get_collection()
    try:
        doc = col.find_one({"workflow_id": workflow_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowDefinition.model_validate(doc)
    except PyMongoError as exc:
        logger.error("Failed to fetch workflow %s: %s", workflow_id, exc)
        raise RuntimeError(f"Workflow fetch failed: {exc}") from exc


def get_workflow_by_understanding(
    understanding_id: str,
) -> Optional[WorkflowDefinition]:
    """Return the stored workflow for a given understanding_id, or None."""
    col = _get_collection()
    try:
        doc = col.find_one({"understanding_id": understanding_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowDefinition.model_validate(doc)
    except PyMongoError as exc:
        logger.error(
            "Failed to fetch workflow for understanding %s: %s", understanding_id, exc
        )
        raise RuntimeError(f"Workflow fetch failed: {exc}") from exc


def list_workflows() -> List[WorkflowDefinition]:
    """Return all stored workflows, newest first."""
    col = _get_collection()
    try:
        docs = list(col.find({}).sort("created_at", DESCENDING))
        results = []
        for doc in docs:
            doc.pop("_id", None)
            results.append(WorkflowDefinition.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("Failed to list workflows: %s", exc)
        raise RuntimeError(f"Workflow list failed: {exc}") from exc


def count_workflows() -> int:
    """Return the total number of stored workflows."""
    return _get_collection().count_documents({})


# ---------------------------------------------------------------------------
# Phase 7: targeted approval / rejection updates
# ---------------------------------------------------------------------------

# IMPORTANT: These functions use targeted $set updates keyed on workflow_id.
# They do NOT call upsert_workflow(), which would overwrite the entire document.
# Each update also filters on status == "generated" to atomically enforce
# the transition guard — preventing race conditions and double-approval.


class WorkflowNotFoundError(Exception):
    """Raised when no workflow document matches the given workflow_id."""


class WorkflowTransitionError(Exception):
    """
    Raised when a workflow exists but its current status does not allow
    the requested transition (e.g. already approved or rejected).
    """

    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


def approve_workflow(
    workflow_id: str,
    reviewer_id: str,
    reviewer_notes: Optional[str] = None,
) -> WorkflowDefinition:
    """
    Atomically transition a workflow from 'generated' to 'approved'.

    Uses a conditional $set that only succeeds when:
        workflow_id == workflow_id AND status == "generated"

    This prevents race conditions and double-approval.

    Args:
        workflow_id:    The target workflow's unique ID.
        reviewer_id:    Free-form reviewer identifier (Phase 7: not authenticated).
        reviewer_notes: Optional notes from the reviewer.

    Returns:
        The updated WorkflowDefinition.

    Raises:
        WorkflowNotFoundError:   No workflow with this ID exists.
        WorkflowTransitionError: Workflow exists but cannot transition
                                 (already approved or rejected).
        RuntimeError:            MongoDB failure.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    update_fields = {
        "status": "approved",
        "reviewed_by": reviewer_id,
        "approved_at": now,
        "updated_at": now,
    }
    if reviewer_notes is not None:
        update_fields["reviewer_notes"] = reviewer_notes

    col = _get_collection()
    try:
        result = col.update_one(
            {"workflow_id": workflow_id, "status": "generated"},
            {"$set": update_fields},
        )
    except PyMongoError as exc:
        logger.error("MongoDB error during approval of %s: %s", workflow_id, exc)
        raise RuntimeError(f"Approval DB update failed: {exc}") from exc

    if result.matched_count == 0:
        # Either workflow doesn't exist, or it exists with wrong status
        existing = _get_collection().find_one({"workflow_id": workflow_id})
        if existing is None:
            raise WorkflowNotFoundError(
                f"Workflow '{workflow_id}' not found."
            )
        raise WorkflowTransitionError(
            f"Workflow '{workflow_id}' cannot be approved: "
            f"current status is '{existing.get('status', 'unknown')}'. "
            "Only 'generated' workflows may be approved.",
            current_status=existing.get("status", "unknown"),
        )

    logger.info(
        "Workflow %s approved by reviewer '%s'.", workflow_id, reviewer_id
    )
    updated_doc = col.find_one({"workflow_id": workflow_id})
    if updated_doc is not None:
        updated_doc.pop("_id", None)
        return WorkflowDefinition.model_validate(updated_doc)
    raise WorkflowNotFoundError(f"Workflow '{workflow_id}' not found after update.")


def reject_workflow(
    workflow_id: str,
    reviewer_id: str,
    rejection_reason: str,
    reviewer_notes: Optional[str] = None,
) -> WorkflowDefinition:
    """
    Atomically transition a workflow from 'generated' to 'rejected'.

    Uses a conditional $set that only succeeds when:
        workflow_id == workflow_id AND status == "generated"

    Args:
        workflow_id:       The target workflow's unique ID.
        reviewer_id:       Free-form reviewer identifier (Phase 7: not authenticated).
        rejection_reason:  Required reason for rejection.
        reviewer_notes:    Optional additional notes.

    Returns:
        The updated WorkflowDefinition.

    Raises:
        WorkflowNotFoundError:   No workflow with this ID exists.
        WorkflowTransitionError: Workflow exists but cannot transition.
        RuntimeError:            MongoDB failure.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    update_fields = {
        "status": "rejected",
        "reviewed_by": reviewer_id,
        "rejection_reason": rejection_reason,
        "rejected_at": now,
        "updated_at": now,
    }
    if reviewer_notes is not None:
        update_fields["reviewer_notes"] = reviewer_notes

    col = _get_collection()
    try:
        result = col.update_one(
            {"workflow_id": workflow_id, "status": "generated"},
            {"$set": update_fields},
        )
    except PyMongoError as exc:
        logger.error("MongoDB error during rejection of %s: %s", workflow_id, exc)
        raise RuntimeError(f"Rejection DB update failed: {exc}") from exc

    if result.matched_count == 0:
        existing = col.find_one({"workflow_id": workflow_id})
        if existing is None:
            raise WorkflowNotFoundError(
                f"Workflow '{workflow_id}' not found."
            )
        raise WorkflowTransitionError(
            f"Workflow '{workflow_id}' cannot be rejected: "
            f"current status is '{existing.get('status', 'unknown')}'. "
            "Only 'generated' workflows may be rejected.",
            current_status=existing.get("status", "unknown"),
        )

    logger.info(
        "Workflow %s rejected by reviewer '%s'. Reason: %s",
        workflow_id,
        reviewer_id,
        rejection_reason,
    )
    updated_doc = col.find_one({"workflow_id": workflow_id})
    if updated_doc is not None:
        updated_doc.pop("_id", None)
        return WorkflowDefinition.model_validate(updated_doc)
    raise WorkflowNotFoundError(f"Workflow '{workflow_id}' not found after update.")


def get_workflows_by_status(status: str) -> List[WorkflowDefinition]:
    """
    Return all workflows matching the given status, newest first.

    For Phase 7 pending-review queue: status='generated'.

    Args:
        status: The status value to filter by.

    Returns:
        List of matching WorkflowDefinition objects.

    Raises:
        RuntimeError: on MongoDB failure.
    """
    col = _get_collection()
    try:
        docs = list(col.find({"status": status}).sort("created_at", DESCENDING))
        results = []
        for doc in docs:
            doc.pop("_id", None)
            results.append(WorkflowDefinition.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("Failed to list workflows by status '%s': %s", status, exc)
        raise RuntimeError(f"Workflow list-by-status failed: {exc}") from exc
