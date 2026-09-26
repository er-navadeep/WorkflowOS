"""
Activity Event Storage Service
================================
Responsible for persisting ActivityEvent objects to MongoDB and
retrieving them for the API layer and discovery engine.

Collection: activity_events

Indexes created on first run:
    - session_id      (for grouping events by workflow run)
    - event_type      (for filtering)
    - application     (for filtering)
    - timestamp       (for chronological queries and TTL candidates)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database
from app.schemas.activity_event import ActivityEvent, ActivityEventFilter

logger = logging.getLogger(__name__)

# MongoDB collection name
COLLECTION_NAME = "activity_events"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_collection() -> Collection:
    """Return the activity_events collection, ensuring indexes exist."""
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    _ensure_indexes(col)
    return col


# Track whether indexes have already been created in this process
_indexes_created: bool = False


def _ensure_indexes(col: Collection) -> None:
    """Create indexes if they haven't been set up yet in this process."""
    global _indexes_created
    if _indexes_created:
        return

    try:
        col.create_index([("session_id", ASCENDING)], name="idx_session_id")
        col.create_index([("event_type", ASCENDING)], name="idx_event_type")
        col.create_index([("application", ASCENDING)], name="idx_application")
        col.create_index([("timestamp", DESCENDING)], name="idx_timestamp_desc")
        _indexes_created = True
        logger.debug("activity_events indexes ensured.")
    except PyMongoError as exc:
        # Non-fatal — indexes may already exist
        logger.warning("Could not create indexes: %s", exc)


def _event_to_doc(event: ActivityEvent) -> Dict[str, Any]:
    """Convert an ActivityEvent Pydantic model to a MongoDB document dict."""
    doc = event.model_dump()
    # MongoDB _id will be auto-created; we keep event_id as our application-level ID.
    # Store timestamp as a native Python datetime (MongoDB BSON Date).
    if isinstance(doc.get("timestamp"), datetime):
        # Ensure it is stored as UTC-aware datetime
        ts: datetime = doc["timestamp"]
        if ts.tzinfo is None:
            doc["timestamp"] = ts.replace(tzinfo=timezone.utc)
    # Convert EventType enum to its string value
    if hasattr(doc.get("event_type"), "value"):
        doc["event_type"] = doc["event_type"].value
    return doc


def _doc_to_event(doc: Dict[str, Any]) -> ActivityEvent:
    """Convert a MongoDB document back to an ActivityEvent model."""
    doc = dict(doc)
    doc.pop("_id", None)  # Remove MongoDB's internal _id
    return ActivityEvent.model_validate(doc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def insert_event(event: ActivityEvent) -> str:
    """
    Persist a single ActivityEvent to MongoDB.

    Returns:
        event_id (str) of the inserted event.

    Raises:
        RuntimeError: on MongoDB write failure.
    """
    col = _get_collection()
    doc = _event_to_doc(event)
    try:
        col.insert_one(doc)
        logger.info(
            "Inserted event %s | type=%s app=%s action=%s session=%s",
            event.event_id,
            event.event_type.value,
            event.application,
            event.action,
            event.session_id,
        )
        return event.event_id
    except PyMongoError as exc:
        logger.error("Failed to insert event %s: %s", event.event_id, exc)
        raise RuntimeError(f"Database write failed: {exc}") from exc


def insert_events(events: List[ActivityEvent]) -> List[str]:
    """
    Persist a list of ActivityEvents using a single bulk insert.

    Returns:
        List of event_ids in the same order as input.

    Raises:
        RuntimeError: on MongoDB write failure.
    """
    if not events:
        return []

    col = _get_collection()
    docs = [_event_to_doc(e) for e in events]
    try:
        col.insert_many(docs, ordered=False)
        ids = [e.event_id for e in events]
        logger.info("Bulk-inserted %d events (session=%s)", len(ids), events[0].session_id)
        return ids
    except PyMongoError as exc:
        logger.error("Bulk insert failed: %s", exc)
        raise RuntimeError(f"Database bulk write failed: {exc}") from exc


def get_events(filters: Optional[ActivityEventFilter] = None) -> List[ActivityEvent]:
    """
    Retrieve activity events from MongoDB, ordered by timestamp descending.

    Args:
        filters: Optional ActivityEventFilter controlling which events to return.

    Returns:
        List of ActivityEvent models.
    """
    col = _get_collection()

    query: Dict[str, Any] = {}
    limit = 100
    skip = 0

    if filters:
        if filters.session_id:
            query["session_id"] = filters.session_id
        if filters.event_type:
            query["event_type"] = filters.event_type.value
        if filters.application:
            # Case-insensitive substring match
            query["application"] = {"$regex": filters.application, "$options": "i"}
        limit = filters.limit
        skip = filters.skip

    try:
        cursor = (
            col.find(query)
            .sort("timestamp", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        events = [_doc_to_event(doc) for doc in cursor]
        logger.debug("Retrieved %d events (query=%s)", len(events), query)
        return events
    except PyMongoError as exc:
        logger.error("Failed to retrieve events: %s", exc)
        raise RuntimeError(f"Database read failed: {exc}") from exc


def get_events_by_session(session_id: str) -> List[ActivityEvent]:
    """
    Retrieve all events for a given session, ordered chronologically (oldest first).

    Used by the discovery engine to reconstruct a workflow sequence.
    """
    col = _get_collection()
    try:
        cursor = col.find({"session_id": session_id}).sort("timestamp", ASCENDING)
        events = [_doc_to_event(doc) for doc in cursor]
        logger.debug("Retrieved %d events for session %s", len(events), session_id)
        return events
    except PyMongoError as exc:
        logger.error("Failed to retrieve session events: %s", exc)
        raise RuntimeError(f"Database read failed: {exc}") from exc


def count_events(session_id: Optional[str] = None) -> int:
    """Return the total number of stored events, optionally filtered by session."""
    col = _get_collection()
    query: Dict[str, Any] = {}
    if session_id:
        query["session_id"] = session_id
    return col.count_documents(query)
