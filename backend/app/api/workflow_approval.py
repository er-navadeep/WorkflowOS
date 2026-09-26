"""
Workflow Approval API Router
=============================
Phase 7 API endpoints for human approval and rejection of generated workflows.

Endpoints:
    GET  /api/v1/workflows/pending
        Retrieve all workflows awaiting human review (status == 'generated').
        NOTE: Must be declared before /{workflow_id} routes to prevent path conflict.

    POST /api/v1/workflows/{workflow_id}/approve
        Transition a workflow from 'generated' to 'approved'.

    POST /api/v1/workflows/{workflow_id}/reject
        Transition a workflow from 'generated' to 'rejected'.

Security and Guardrails:
    - No real Gmail, Slack, CRM, or external automation is triggered.
    - No credentials or secrets are exposed or accepted.
    - reviewer_id is an unauthenticated free-form string in Phase 7.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from app.schemas.workflow import (
    WorkflowApprovalResponse,
    WorkflowApproveRequest,
    WorkflowDefinition,
    WorkflowRejectRequest,
)
from app.services.workflow_approval_service import (
    WorkflowApprovalError,
    approve_workflow,
    get_pending_workflows,
    reject_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflow Approval"])


# ---------------------------------------------------------------------------
# GET /workflows/pending
# IMPORTANT: Declared first so FastAPI matches '/pending' before '/{workflow_id}'.
# ---------------------------------------------------------------------------

@router.get(
    "/pending",
    response_model=List[WorkflowDefinition],
    status_code=status.HTTP_200_OK,
    summary="List workflows awaiting human review",
    description=(
        "Returns all stored WorkflowDefinitions with status 'generated', "
        "ordered newest first. These workflows require human approval or rejection."
    ),
)
def get_pending_workflows_endpoint() -> List[WorkflowDefinition]:
    """List all workflows pending human review."""
    try:
        return get_pending_workflows()
    except WorkflowApprovalError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# POST /workflows/{workflow_id}/approve
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/approve",
    response_model=WorkflowApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a generated workflow",
    description=(
        "Transitions a workflow from 'generated' to 'approved'. "
        "Returns 409 if the workflow is already approved, rejected, or in an invalid state. "
        "Returns 404 if the workflow does not exist. "
        "Phase 7: No automation or execution is started. Reviewer identity is not yet authenticated."
    ),
)
def approve_workflow_endpoint(
    workflow_id: str,
    payload: WorkflowApproveRequest,
) -> WorkflowApprovalResponse:
    """Approve a workflow with status 'generated'."""
    try:
        return approve_workflow(
            workflow_id=workflow_id,
            reviewer_id=payload.reviewer_id,
            reviewer_notes=payload.reviewer_notes,
        )
    except WorkflowApprovalError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# POST /workflows/{workflow_id}/reject
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/reject",
    response_model=WorkflowApprovalResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject a generated workflow",
    description=(
        "Transitions a workflow from 'generated' to 'rejected'. "
        "Requires a non-empty rejection_reason. "
        "Returns 409 if the workflow is already approved or rejected. "
        "Returns 404 if the workflow does not exist."
    ),
)
def reject_workflow_endpoint(
    workflow_id: str,
    payload: WorkflowRejectRequest,
) -> WorkflowApprovalResponse:
    """Reject a workflow with status 'generated'."""
    try:
        return reject_workflow(
            workflow_id=workflow_id,
            reviewer_id=payload.reviewer_id,
            rejection_reason=payload.rejection_reason,
            reviewer_notes=payload.reviewer_notes,
        )
    except WorkflowApprovalError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# Internal HTTP error translator
# ---------------------------------------------------------------------------

def _raise_http(exc: WorkflowApprovalError) -> None:
    """Translate domain WorkflowApprovalError to FastAPI HTTPException."""
    code = exc.status_code

    if code == 404:
        detail = {"error": "not_found", "message": exc.message}
    elif code == 409:
        detail = {"error": "invalid_transition", "message": exc.message}
    elif code == 422:
        detail = {"error": "validation_error", "message": exc.message}
    elif code == 503:
        detail = {"error": "service_unavailable", "message": exc.message}
    else:
        detail = {"error": "internal_error", "message": "An unexpected error occurred."}
        logger.error("Unexpected approval service error: %s", exc)

    raise HTTPException(status_code=code, detail=detail)
