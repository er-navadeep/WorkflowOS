"""
Workflow Approval Service
=========================
Phase 7 service implementing human approval lifecycle transitions:
    'generated' -> 'approved'
    'generated' -> 'rejected'

Security and Architectural Guardrails:
    - Phase 7 is strictly an approval / state-management layer.
    - No real Gmail, Slack, CRM, or external automation is triggered.
    - No Gemini AI calls are made.
    - The Phase 6 generation-time validator is NEVER called.
    - Reviewer identity (reviewer_id) is currently an unauthenticated free-form
      string for this phase; real authentication will be integrated in a future phase.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.models.workflow import (
    WorkflowNotFoundError,
    WorkflowTransitionError,
    approve_workflow as db_approve_workflow,
    get_workflows_by_status,
    reject_workflow as db_reject_workflow,
)
from app.schemas.workflow import (
    WorkflowApprovalResponse,
    WorkflowDefinition,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------

class WorkflowApprovalError(Exception):
    """
    Domain exception for workflow approval operations.

    Attributes:
        status_code: Suggested HTTP status code (404, 409, 422, 503).
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Service Functions
# ---------------------------------------------------------------------------

def approve_workflow(
    workflow_id: str,
    reviewer_id: str,
    reviewer_notes: Optional[str] = None,
) -> WorkflowApprovalResponse:
    """
    Approve a generated workflow.

    Enforces that:
        1. reviewer_id is provided and non-empty.
        2. Workflow exists.
        3. Workflow is in 'generated' state (atomic DB check).
        4. State transitions strictly: 'generated' -> 'approved'.

    Args:
        workflow_id:    Target workflow ID.
        reviewer_id:    Reviewer identifier (unauthenticated in Phase 7).
        reviewer_notes: Optional notes explaining the approval decision.

    Returns:
        WorkflowApprovalResponse with transition details.

    Raises:
        WorkflowApprovalError: 404 (not found), 409 (invalid transition),
                               422 (validation), 503 (database failure).
    """
    if not reviewer_id or not reviewer_id.strip():
        raise WorkflowApprovalError(
            "reviewer_id must not be empty or whitespace.",
            status_code=422,
        )

    cleaned_reviewer = reviewer_id.strip()
    cleaned_notes = reviewer_notes.strip() if reviewer_notes else None

    try:
        updated_wf = db_approve_workflow(
            workflow_id=workflow_id,
            reviewer_id=cleaned_reviewer,
            reviewer_notes=cleaned_notes,
        )
    except WorkflowNotFoundError as exc:
        logger.warning("Approval failed: workflow '%s' not found.", workflow_id)
        raise WorkflowApprovalError(str(exc), status_code=404) from exc
    except WorkflowTransitionError as exc:
        logger.warning(
            "Approval rejected for '%s': invalid transition from '%s'.",
            workflow_id,
            exc.current_status,
        )
        raise WorkflowApprovalError(str(exc), status_code=409) from exc
    except RuntimeError as exc:
        logger.error("DB error approving workflow '%s': %s", workflow_id, exc)
        raise WorkflowApprovalError(
            "Database error during workflow approval.",
            status_code=503,
        ) from exc

    return WorkflowApprovalResponse(
        success=True,
        workflow_id=updated_wf.workflow_id,
        previous_status="generated",
        new_status=updated_wf.status,
        reviewed_by=updated_wf.reviewed_by or cleaned_reviewer,
        approved_at=updated_wf.approved_at,
        rejected_at=None,
        reviewer_notes=updated_wf.reviewer_notes,
        rejection_reason=None,
        message=f"Workflow '{workflow_id}' approved successfully.",
    )


def reject_workflow(
    workflow_id: str,
    reviewer_id: str,
    rejection_reason: str,
    reviewer_notes: Optional[str] = None,
) -> WorkflowApprovalResponse:
    """
    Reject a generated workflow.

    Enforces that:
        1. reviewer_id and rejection_reason are provided and non-empty.
        2. Workflow exists.
        3. Workflow is in 'generated' state (atomic DB check).
        4. State transitions strictly: 'generated' -> 'rejected'.

    Args:
        workflow_id:       Target workflow ID.
        reviewer_id:       Reviewer identifier (unauthenticated in Phase 7).
        rejection_reason:  Mandatory reason for rejection.
        reviewer_notes:    Optional additional notes.

    Returns:
        WorkflowApprovalResponse with transition details.

    Raises:
        WorkflowApprovalError: 404 (not found), 409 (invalid transition),
                               422 (validation), 503 (database failure).
    """
    if not reviewer_id or not reviewer_id.strip():
        raise WorkflowApprovalError(
            "reviewer_id must not be empty or whitespace.",
            status_code=422,
        )

    if not rejection_reason or not rejection_reason.strip():
        raise WorkflowApprovalError(
            "rejection_reason must not be empty or whitespace.",
            status_code=422,
        )

    cleaned_reviewer = reviewer_id.strip()
    cleaned_reason = rejection_reason.strip()
    cleaned_notes = reviewer_notes.strip() if reviewer_notes else None

    try:
        updated_wf = db_reject_workflow(
            workflow_id=workflow_id,
            reviewer_id=cleaned_reviewer,
            rejection_reason=cleaned_reason,
            reviewer_notes=cleaned_notes,
        )
    except WorkflowNotFoundError as exc:
        logger.warning("Rejection failed: workflow '%s' not found.", workflow_id)
        raise WorkflowApprovalError(str(exc), status_code=404) from exc
    except WorkflowTransitionError as exc:
        logger.warning(
            "Rejection rejected for '%s': invalid transition from '%s'.",
            workflow_id,
            exc.current_status,
        )
        raise WorkflowApprovalError(str(exc), status_code=409) from exc
    except RuntimeError as exc:
        logger.error("DB error rejecting workflow '%s': %s", workflow_id, exc)
        raise WorkflowApprovalError(
            "Database error during workflow rejection.",
            status_code=503,
        ) from exc

    return WorkflowApprovalResponse(
        success=True,
        workflow_id=updated_wf.workflow_id,
        previous_status="generated",
        new_status=updated_wf.status,
        reviewed_by=updated_wf.reviewed_by or cleaned_reviewer,
        approved_at=None,
        rejected_at=updated_wf.rejected_at,
        reviewer_notes=updated_wf.reviewer_notes,
        rejection_reason=updated_wf.rejection_reason or cleaned_reason,
        message=f"Workflow '{workflow_id}' rejected successfully.",
    )


def get_pending_workflows() -> List[WorkflowDefinition]:
    """
    Retrieve all workflows awaiting human review (status == 'generated').

    Returns:
        List of WorkflowDefinition records with status 'generated', newest first.

    Raises:
        WorkflowApprovalError: on database failure (503).
    """
    try:
        return get_workflows_by_status("generated")
    except RuntimeError as exc:
        logger.error("DB error fetching pending workflows: %s", exc)
        raise WorkflowApprovalError(
            "Database error while listing pending workflows.",
            status_code=503,
        ) from exc
