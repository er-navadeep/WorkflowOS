"""
Activity Events API
====================
Endpoints:

    POST /api/v1/events            — Ingest a single activity event
    POST /api/v1/events/batch      — Ingest multiple events at once
    GET  /api/v1/events            — Retrieve recent events (debug / demo)

All request bodies are validated with Pydantic.
Errors are returned as structured JSON — never raw stack traces.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.activity import storage
from app.schemas.activity_event import (
    ActivityEvent,
    ActivityEventBatch,
    ActivityEventBatchResponse,
    ActivityEventFilter,
    ActivityEventResponse,
    EventType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Activity Events"])


# ---------------------------------------------------------------------------
# POST /events
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ActivityEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single activity event",
    description=(
        "Receives one structured activity event from the Desktop Activity Agent "
        "or any other observer.  The event is validated and stored in MongoDB."
    ),
)
def ingest_event(event: ActivityEvent) -> ActivityEventResponse:
    """
    Accept one activity event, validate it, and persist it to MongoDB.

    Returns the event_id of the inserted record.
    """
    try:
        event_id = storage.insert_event(event)
        return ActivityEventResponse(
            success=True,
            event_id=event_id,
            message="Event stored successfully.",
        )
    except RuntimeError as exc:
        logger.error("Ingest failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "storage_error", "message": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# POST /events/batch
# ---------------------------------------------------------------------------

@router.post(
    "/batch",
    response_model=ActivityEventBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest multiple activity events",
    description=(
        "Accepts a batch of structured activity events in a single request. "
        "Useful for the Desktop Activity Agent to flush buffered events. "
        "All events are validated before any are written."
    ),
)
def ingest_events_batch(batch: ActivityEventBatch) -> ActivityEventBatchResponse:
    """
    Accept multiple activity events, validate all, and bulk-insert to MongoDB.

    Returns the event_ids of all inserted records.
    """
    try:
        event_ids = storage.insert_events(batch.events)
        return ActivityEventBatchResponse(
            success=True,
            inserted=len(event_ids),
            event_ids=event_ids,
            message=f"{len(event_ids)} events stored successfully.",
        )
    except RuntimeError as exc:
        logger.error("Batch ingest failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "storage_error", "message": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# GET /events
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[ActivityEvent],
    summary="List recent activity events",
    description=(
        "Returns stored activity events in reverse-chronological order. "
        "Supports filtering by session, event type, and application. "
        "Primarily intended for debugging and demo purposes."
    ),
)
def list_events(
    session_id: Optional[str] = Query(None, description="Filter by session ID."),
    event_type: Optional[EventType] = Query(None, description="Filter by event type."),
    application: Optional[str] = Query(None, description="Filter by application name (partial match)."),
    limit: int = Query(100, ge=1, le=1000, description="Max events to return."),
    skip: int = Query(0, ge=0, description="Events to skip (pagination)."),
) -> List[ActivityEvent]:
    """
    Retrieve recent activity events from MongoDB.

    Results are ordered newest-first (descending timestamp).
    """
    filters = ActivityEventFilter(
        session_id=session_id,
        event_type=event_type,
        application=application,
        limit=limit,
        skip=skip,
    )
    try:
        return storage.get_events(filters)
    except RuntimeError as exc:
        logger.error("Event retrieval failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "storage_error", "message": str(exc)},
        ) from exc
