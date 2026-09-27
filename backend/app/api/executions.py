"""
Executions API Router — Phase 8 Step 8.1
========================================
Phase 8.1 API endpoints for workflow execution records and safe dry-run execution.

Endpoints:
    POST /api/v1/executions/dry-run/{workflow_id}
        Initiate a simulated dry-run execution of an approved workflow.
        Strictly requires workflow status == 'approved'.
        Never performs real external actions.

    GET  /api/v1/executions/{execution_id}
        Retrieve an execution record by its unique execution_id.

    GET  /api/v1/executions
        List execution records, optionally filtered by workflow_id.

Security & Architectural Guardrails:
    - Real execution endpoints are NOT implemented.
    - Zero external integrations (Gmail, Slack, CRM, browser, desktop are not touched).
    - Hard guard: workflows in 'generated', 'rejected', or missing state return 409 / 404.
    - Zero secrets or tokens are exposed or accepted.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.execution import (
    DryRunExecutionRequest,
    ExecutionStatus,
    LiveExecutionRequest,
    WorkflowExecution,
    WorkflowExecutionResponse,
)
from app.services.execution_service import (
    ExecutionNotFoundError,
    ExecutionServiceError,
    WorkflowNotApprovedError,
    WorkflowNotFoundError,
    execute_dry_run,
    execute_live,
    get_execution,
    list_executions_for_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/executions", tags=["Workflow Execution"])


# ---------------------------------------------------------------------------
# POST /executions/dry-run/{workflow_id}
# ---------------------------------------------------------------------------

@router.post(
    "/dry-run/{workflow_id}",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate dry-run execution of an approved workflow",
    description=(
        "Executes a safe dry-run simulation of an approved workflow. "
        "Validates that the workflow exists and has status 'approved'. "
        "Records simulated execution step records without performing any external calls. "
        "Returns 409 if the workflow is not approved. "
        "Returns 404 if the workflow is not found. "
        "Returns 422 if the workflow definition has invalid steps."
    ),
)
def dry_run_workflow_endpoint(
    workflow_id: str,
    payload: Optional[DryRunExecutionRequest] = None,
) -> WorkflowExecutionResponse:
    """Execute safe dry-run simulation for an approved workflow."""
    idempotency_key = payload.idempotency_key if payload else None
    trigger_override = payload.trigger_override if payload else None

    try:
        execution = execute_dry_run(
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            trigger_override=trigger_override,
        )
        return WorkflowExecutionResponse(
            success=True,
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status.value,
            message="Dry-run simulation completed successfully.",
            execution=execution,
        )
    except ExecutionServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# POST /executions/live/{workflow_id}
# ---------------------------------------------------------------------------

@router.post(
    "/live/{workflow_id}",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute live approved workflow with external integrations",
    description=(
        "Executes supported steps of an approved workflow in LIVE mode with real external integrations (Slack). "
        "Strictly requires workflow status == 'approved'. "
        "Returns 409 if the workflow is not approved. "
        "Returns 404 if the workflow is not found. "
        "Returns 422 if the workflow definition has invalid steps."
    ),
)
def live_workflow_endpoint(
    workflow_id: str,
    payload: Optional[LiveExecutionRequest] = None,
) -> WorkflowExecutionResponse:
    """Execute live integration for an approved workflow."""
    idempotency_key = payload.idempotency_key if payload else None
    trigger_override = payload.trigger_override if payload else None
    variables = payload.variables if payload else None

    try:
        execution = execute_live(
            workflow_id=workflow_id,
            idempotency_key=idempotency_key,
            trigger_override=trigger_override,
            variables=variables,
        )
        return WorkflowExecutionResponse(
            success=execution.status == ExecutionStatus.COMPLETED,
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            status=execution.status.value,
            message=f"Live execution completed with status '{execution.status.value}'.",
            execution=execution,
        )
    except ExecutionServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# GET /executions/{execution_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{execution_id}",
    response_model=WorkflowExecution,
    status_code=status.HTTP_200_OK,
    summary="Get execution record by ID",
    description="Returns the persisted audit and status record for a workflow execution.",
)
def get_execution_endpoint(execution_id: str) -> WorkflowExecution:
    """Retrieve an execution record by execution_id."""
    try:
        return get_execution(execution_id)
    except ExecutionServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# GET /executions
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[WorkflowExecution],
    status_code=status.HTTP_200_OK,
    summary="List execution records",
    description="Returns a chronological list of execution records, optionally filtered by workflow_id.",
)
def list_executions_endpoint(
    workflow_id: Optional[str] = Query(
        None, description="Optional workflow_id filter"
    ),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
) -> List[WorkflowExecution]:
    """List execution records with optional filtering."""
    try:
        return list_executions_for_workflow(workflow_id=workflow_id, limit=limit)
    except ExecutionServiceError as exc:
        _raise_http(exc)


# ---------------------------------------------------------------------------
# Error Translator
# ---------------------------------------------------------------------------

def _raise_http(exc: ExecutionServiceError) -> None:
    """Translate domain ExecutionServiceError to FastAPI HTTPException."""
    code = exc.status_code

    if code == 404:
        detail = {"error": "not_found", "message": exc.message}
    elif code == 409:
        detail = {"error": "invalid_execution_state", "message": exc.message}
    elif code == 422:
        detail = {"error": "validation_error", "message": exc.message}
    elif code == 503:
        detail = {"error": "service_unavailable", "message": exc.message}
    else:
        detail = {"error": "internal_error", "message": "An unexpected execution error occurred."}
        logger.error("Unexpected execution service error: %s", exc)

    raise HTTPException(status_code=code, detail=detail)
