"""
Workflows API Router
=====================
Phase 6 API endpoints for AI-generated workflow definitions.

Endpoints:
    POST /api/v1/workflows/generate/{understanding_id}
        Generate (or regenerate) a WorkflowDefinition from an existing
        WorkflowUnderstanding.  Calls Gemini, parses, validates, persists.

    GET  /api/v1/workflows/by-understanding/{understanding_id}
        Retrieve the stored WorkflowDefinition for an understanding_id.

    GET  /api/v1/workflows/{workflow_id}
        Retrieve a stored WorkflowDefinition by workflow_id.

    GET  /api/v1/workflows
        List all stored WorkflowDefinitions, newest first.

Security:
    - No credentials, API keys, or environment variables are returned.
    - Error messages are safe for external consumption.
    - No real Gmail/CRM/Slack actions are executed -- definitions only.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from app.schemas.workflow import WorkflowDefinition, WorkflowGenerationResponse
from app.services.workflow_generation_service import (
    WorkflowServiceError,
    generate_workflow,
    get_workflow,
    list_all_workflows,
)
from app.models.workflow import get_workflow_by_understanding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflow Generation"])


# ---------------------------------------------------------------------------
# POST /workflows/generate/{understanding_id}
# ---------------------------------------------------------------------------

@router.post(
    "/generate/{understanding_id}",
    response_model=WorkflowGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a WorkflowDefinition from an existing WorkflowUnderstanding",
    description=(
        "Retrieves the Phase 5 WorkflowUnderstanding, sends it to Gemini to produce "
        "a structured WorkflowDefinition, runs deterministic validation, persists the "
        "result, and returns the definition. "
        "Safe to call multiple times -- re-running replaces the existing workflow. "
        "No real Gmail, CRM, or Slack actions are executed. "
        "This is a definition-only operation."
    ),
)
def generate_workflow_endpoint(understanding_id: str) -> WorkflowGenerationResponse:
    """Generate or regenerate a WorkflowDefinition for a WorkflowUnderstanding."""
    try:
        workflow = generate_workflow(understanding_id)
    except WorkflowServiceError as exc:
        _raise_http(exc)

    return WorkflowGenerationResponse(
        success=True,
        workflow_id=workflow.workflow_id,
        understanding_id=workflow.understanding_id,
        message=(
            f"Workflow generated with {len(workflow.steps)} steps "
            f"(confidence {workflow.generation_confidence:.2f})."
        ),
        workflow=workflow,
    )


# ---------------------------------------------------------------------------
# GET /workflows/by-understanding/{understanding_id}
# NOTE: Declared before /{workflow_id} to avoid FastAPI path conflict.
# ---------------------------------------------------------------------------

@router.get(
    "/by-understanding/{understanding_id}",
    response_model=WorkflowDefinition,
    summary="Get the WorkflowDefinition for a specific understanding",
    description=(
        "Returns the stored WorkflowDefinition generated from the given understanding_id. "
        "Returns 404 if no workflow has been generated for this understanding."
    ),
)
def get_workflow_by_understanding_endpoint(understanding_id: str) -> WorkflowDefinition:
    """Retrieve a stored WorkflowDefinition by understanding_id."""
    try:
        workflow = get_workflow_by_understanding(understanding_id)
    except RuntimeError as exc:
        logger.error(
            "DB error fetching workflow for understanding %s: %s", understanding_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "service_unavailable",
                "message": "Database error while retrieving workflow.",
            },
        )

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": (
                    f"No workflow found for understanding '{understanding_id}'. "
                    "Call POST /workflows/generate/{{understanding_id}} to generate one."
                ),
            },
        )
    return workflow


# ---------------------------------------------------------------------------
# GET /workflows/{workflow_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{workflow_id}",
    response_model=WorkflowDefinition,
    summary="Get a stored WorkflowDefinition by workflow_id",
    description=(
        "Returns the stored WorkflowDefinition for the given workflow_id. "
        "Returns 404 if no workflow with that ID has been generated."
    ),
)
def get_workflow_endpoint(workflow_id: str) -> WorkflowDefinition:
    """Retrieve a stored WorkflowDefinition by workflow_id."""
    try:
        workflow = get_workflow(workflow_id)
    except WorkflowServiceError as exc:
        _raise_http(exc)

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": (
                    f"No workflow found with id '{workflow_id}'. "
                    "Call POST /workflows/generate/{{understanding_id}} to generate one."
                ),
            },
        )
    return workflow


# ---------------------------------------------------------------------------
# GET /workflows
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[WorkflowDefinition],
    summary="List all stored WorkflowDefinitions",
    description="Returns all WorkflowDefinition records, newest first.",
)
def list_workflows_endpoint() -> List[WorkflowDefinition]:
    """List all stored workflow definitions."""
    try:
        return list_all_workflows()
    except WorkflowServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _raise_http(exc: WorkflowServiceError) -> None:
    """Convert a WorkflowServiceError to the appropriate HTTPException."""
    code = getattr(exc, "status_code", 500)

    if code == 404:
        detail = {"error": "not_found", "message": str(exc)}
    elif code == 503:
        detail = {"error": "service_unavailable", "message": str(exc)}
    elif code == 502:
        detail = {"error": "ai_response_error", "message": str(exc)}
    elif code == 422:
        detail = {"error": "validation_failed", "message": str(exc)}
    else:
        detail = {"error": "internal_error", "message": "An unexpected error occurred."}
        logger.error("Unexpected service error: %s", exc)

    raise HTTPException(status_code=code, detail=detail)

