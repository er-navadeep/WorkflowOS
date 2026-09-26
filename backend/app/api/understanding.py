"""
Understanding API Router
=========================
Phase 5 API endpoints for AI-generated workflow understanding.

Endpoints:
    POST /api/v1/understanding/{candidate_id}
        Generate (or regenerate) AI understanding for a candidate.

    GET  /api/v1/understanding/{candidate_id}
        Retrieve the stored understanding for a candidate.

    GET  /api/v1/understanding
        List all stored understandings.

Security:
    - No credentials, API keys, or environment variables are returned.
    - Error messages are safe for external consumption.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from app.schemas.workflow_understanding import UnderstandingResponse, WorkflowUnderstanding
from app.services.ai_understanding_service import (
    UnderstandingServiceError,
    generate_understanding,
    get_understanding,
    list_all_understandings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/understanding", tags=["AI Workflow Understanding"])


# ---------------------------------------------------------------------------
# POST /understanding/{candidate_id}  — generate understanding
# ---------------------------------------------------------------------------

@router.post(
    "/{candidate_id}",
    response_model=UnderstandingResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate AI understanding for a workflow candidate",
    description=(
        "Retrieves the WorkflowCandidate, sends the observed sequence to Gemini, "
        "validates the structured response, persists it, and returns the understanding. "
        "Safe to call multiple times — re-running replaces the existing understanding."
    ),
)
def generate_understanding_endpoint(candidate_id: str) -> UnderstandingResponse:
    """Generate or regenerate AI understanding for a WorkflowCandidate."""
    try:
        understanding = generate_understanding(candidate_id)
    except UnderstandingServiceError as exc:
        _raise_http(exc)

    return UnderstandingResponse(
        success=True,
        understanding_id=understanding.understanding_id,
        candidate_id=understanding.candidate_id,
        message=f"Understanding generated with confidence {understanding.confidence:.2f}.",
        understanding=understanding,
    )


# ---------------------------------------------------------------------------
# GET /understanding/{candidate_id}  — retrieve stored understanding
# ---------------------------------------------------------------------------

@router.get(
    "/{candidate_id}",
    response_model=WorkflowUnderstanding,
    summary="Get stored understanding for a candidate",
    description=(
        "Returns the stored WorkflowUnderstanding for the given candidate_id. "
        "Returns 404 if no understanding has been generated yet."
    ),
)
def get_understanding_endpoint(candidate_id: str) -> WorkflowUnderstanding:
    """Retrieve a stored understanding by candidate_id."""
    try:
        understanding = get_understanding(candidate_id)
    except UnderstandingServiceError as exc:
        _raise_http(exc)

    if understanding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": (
                    f"No understanding found for candidate '{candidate_id}'. "
                    "Call POST /understanding/{candidate_id} to generate one."
                ),
            },
        )
    return understanding


# ---------------------------------------------------------------------------
# GET /understanding  — list all understandings
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[WorkflowUnderstanding],
    summary="List all stored understandings",
    description="Returns all WorkflowUnderstanding records, newest first.",
)
def list_understandings_endpoint() -> List[WorkflowUnderstanding]:
    """List all stored understandings."""
    try:
        return list_all_understandings()
    except UnderstandingServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _raise_http(exc: UnderstandingServiceError) -> None:
    """Convert an UnderstandingServiceError to the appropriate HTTPException."""
    code = getattr(exc, "status_code", 500)

    # Map codes to safe public messages
    if code == 404:
        detail = {"error": "not_found", "message": str(exc)}
    elif code == 503:
        detail = {"error": "service_unavailable", "message": str(exc)}
    elif code == 502:
        detail = {"error": "ai_response_error", "message": str(exc)}
    else:
        detail = {"error": "internal_error", "message": "An unexpected error occurred."}
        logger.error("Unexpected service error: %s", exc)

    raise HTTPException(status_code=code, detail=detail)
