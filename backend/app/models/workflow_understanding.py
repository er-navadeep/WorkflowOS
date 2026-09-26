"""
Workflow Understanding Storage
================================
MongoDB persistence for WorkflowUnderstanding documents.

Collection: workflow_understandings

Uniqueness strategy:
    Each understanding is keyed on candidate_id.
    Re-running understanding generation for the same candidate
    replaces the existing record (upsert on candidate_id).
    This prevents duplicates while allowing regeneration.

Indexes:
    - candidate_id (unique) — primary lookup key
    - status               — filter by status
    - created_at           — chronological listing
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.workflow_understanding import WorkflowUnderstanding

logger = logging.getLogger(__name__)

COLLECTION_NAME = "workflow_understandings"

_indexes_created: bool = False


def _get_collection() -> Collection:
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    global _indexes_created
    if not _indexes_created:
        try:
            col.create_index(
                [("candidate_id", ASCENDING)],
                name="idx_candidate_id",
                unique=True,
            )
            col.create_index([("status", ASCENDING)], name="idx_status")
            col.create_index([("created_at", DESCENDING)], name="idx_created_at")
            _indexes_created = True
            logger.debug("workflow_understandings indexes ensured.")
        except PyMongoError as exc:
            logger.warning("Could not create understanding indexes: %s", exc)
    return col


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def upsert_understanding(understanding: WorkflowUnderstanding) -> str:
    """
    Insert or replace the understanding for a candidate.

    If an understanding already exists for candidate_id, it is fully
    replaced with the new understanding (regeneration use-case).

    Returns:
        The understanding_id of the stored document.

    Raises:
        RuntimeError: on MongoDB failure.
    """
    col = _get_collection()
    doc = understanding.model_dump()

    try:
        col.update_one(
            {"candidate_id": understanding.candidate_id},
            {"$set": doc},
            upsert=True,
        )
        logger.info(
            "Upserted understanding %s for candidate %s.",
            understanding.understanding_id,
            understanding.candidate_id,
        )
        return understanding.understanding_id
    except PyMongoError as exc:
        logger.error("Failed to upsert understanding: %s", exc)
        raise RuntimeError(f"Understanding upsert failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_understanding_by_candidate(candidate_id: str) -> Optional[WorkflowUnderstanding]:
    """
    Return the stored understanding for a given candidate_id, or None.

    Raises:
        RuntimeError: on MongoDB failure.
    """
    col = _get_collection()
    try:
        doc = col.find_one({"candidate_id": candidate_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowUnderstanding.model_validate(doc)
    except PyMongoError as exc:
        logger.error("Failed to fetch understanding for %s: %s", candidate_id, exc)
        raise RuntimeError(f"Understanding fetch failed: {exc}") from exc


def get_understanding_by_id(understanding_id: str) -> Optional[WorkflowUnderstanding]:
    """Return the understanding with the given understanding_id, or None."""
    col = _get_collection()
    try:
        doc = col.find_one({"understanding_id": understanding_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowUnderstanding.model_validate(doc)
    except PyMongoError as exc:
        logger.error("Failed to fetch understanding %s: %s", understanding_id, exc)
        raise RuntimeError(f"Understanding fetch failed: {exc}") from exc


def list_understandings() -> List[WorkflowUnderstanding]:
    """Return all stored understandings, newest first."""
    col = _get_collection()
    try:
        docs = list(col.find({}).sort("created_at", DESCENDING))
        results = []
        for doc in docs:
            doc.pop("_id", None)
            results.append(WorkflowUnderstanding.model_validate(doc))
        return results
    except PyMongoError as exc:
        logger.error("Failed to list understandings: %s", exc)
        raise RuntimeError(f"Understanding list failed: {exc}") from exc


def count_understandings() -> int:
    """Return the total number of stored understandings."""
    return _get_collection().count_documents({})
