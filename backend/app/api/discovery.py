"""
Discovery API
==============
Endpoints:

    POST /api/v1/discovery/run
        Run workflow discovery against all stored activity events.
        Returns a summary of what was discovered.

    GET  /api/v1/discovery/candidates
        List all discovered workflow candidates.
        Supports optional ?status= filter.

    GET  /api/v1/discovery/candidates/{candidate_id}
        Return one candidate by ID.

All responses use structured JSON.
Errors are returned as structured dicts — no stack traces.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.workflow_candidate import WorkflowCandidate
from app.services.discovery_service import (
    get_candidate,
    get_candidate_count,
    list_candidates,
    run_discovery,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery", tags=["Workflow Discovery"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DiscoveryRunResponse(BaseModel):
    """Response from POST /discovery/run."""
    success: bool
    sessions_analysed: int
    patterns_found: int
    candidates_created: int
    candidates_updated: int
    total_candidates: int
    errors: List[str] = Field(default_factory=list)
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/run",
    response_model=DiscoveryRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run workflow discovery",
    description=(
        "Analyses all stored activity events, detects repeated workflow patterns, "
        "and creates or updates WorkflowCandidate records in MongoDB. "
        "Safe to call multiple times — existing candidates are updated, not duplicated."
    ),
)
def run_discovery_endpoint(
    min_occurrences: int = Query(
        2,
        ge=2,
        le=100,
        description="Minimum number of times a pattern must appear to qualify as a candidate.",
    ),
) -> DiscoveryRunResponse:
    """Trigger the discovery pipeline."""
    try:
        result = run_discovery(min_occurrences=min_occurrences)
        total = get_candidate_count()

        success = len(result.errors) == 0

        return DiscoveryRunResponse(
            success=success,
            sessions_analysed=result.sessions_analysed,
            patterns_found=result.patterns_found,
            candidates_created=result.candidates_created,
            candidates_updated=result.candidates_updated,
            total_candidates=total,
            errors=result.errors,
            message=(
                f"Discovery complete: {result.patterns_found} patterns found, "
                f"{result.candidates_created} new, {result.candidates_updated} updated."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Discovery run failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "discovery_failed", "message": str(exc)},
        ) from exc


@router.get(
    "/candidates",
    response_model=List[WorkflowCandidate],
    summary="List workflow candidates",
    description=(
        "Returns all discovered workflow candidates, sorted by score descending. "
        "Optionally filter by status: 'discovered', 'pending_approval', 'approved', 'rejected'."
    ),
)
def list_candidates_endpoint(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by candidate status.",
    ),
) -> List[WorkflowCandidate]:
    """List all workflow candidates."""
    try:
        return list_candidates(status=status_filter)
    except RuntimeError as exc:
        logger.error("Candidate list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "storage_error", "message": str(exc)},
        ) from exc


@router.get(
    "/candidates/{candidate_id}",
    response_model=WorkflowCandidate,
    summary="Get one workflow candidate",
    description="Return a single workflow candidate by its candidate_id.",
)
def get_candidate_endpoint(candidate_id: str) -> WorkflowCandidate:
    """Fetch one candidate by ID."""
    try:
        candidate = get_candidate(candidate_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "storage_error", "message": str(exc)},
        ) from exc

    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Candidate '{candidate_id}' not found.",
            },
        )

    return candidate
