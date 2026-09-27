"""
Execution Service — Phase 8 Step 8.1
====================================
Core execution management, strict approval guards, structural validation,
and safe dry-run execution engine.

Critical Guardrails:
    1. Hard Approval Guard: Workflows MUST have status == 'approved' before
       any execution can run. Workflows in 'generated', 'rejected', or missing
       state strictly CANNOT be executed.
    2. Zero External Integrations: Gmail, Slack, CRM, browser, and desktop
       automations are strictly NOT called. Dry-run performs pure internal simulation.
    3. Zero Secrets: No credentials, tokens, or sensitive data are accepted,
       stored, or processed.
    4. Deterministic State Progression: Controlled transitions through
       pending -> running -> completed (or failed / needs_intervention).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.execution import (
    ExecutionConflictError as DbExecutionConflictError,
    ExecutionNotFoundError as DbExecutionNotFoundError,
    ExecutionStorageError,
    get_execution_by_id as db_get_execution_by_id,
    get_execution_by_idempotency_key as db_get_execution_by_idempotency_key,
    insert_execution as db_insert_execution,
    list_executions as db_list_executions,
    save_execution as db_save_execution,
    update_execution_status as db_update_execution_status,
)
from app.models.workflow import get_workflow_by_id as db_get_workflow_by_id
from app.schemas.execution import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepRecord,
    ExecutionStepStatus,
    WorkflowExecution,
)
from app.schemas.workflow import WorkflowDefinition
from app.integrations.base import (
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.integrations.registry import get_integration_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------

class ExecutionServiceError(Exception):
    """Base domain exception for execution operations with HTTP status code."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class WorkflowNotFoundError(ExecutionServiceError):
    """Raised when the target workflow does not exist."""

    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            f"Workflow '{workflow_id}' not found.",
            status_code=404,
        )
        self.workflow_id = workflow_id


class WorkflowNotApprovedError(ExecutionServiceError):
    """Raised when an execution is attempted on a non-approved workflow."""

    def __init__(self, workflow_id: str, current_status: str) -> None:
        super().__init__(
            f"Workflow '{workflow_id}' cannot be executed: current status is '{current_status}'. "
            "Only 'approved' workflows may be executed.",
            status_code=409,
        )
        self.workflow_id = workflow_id
        self.current_status = current_status


class WorkflowInvalidError(ExecutionServiceError):
    """Raised when an approved workflow fails structural execution validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class ExecutionNotFoundError(ExecutionServiceError):
    """Raised when an execution record is not found."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(f"Execution '{execution_id}' not found.", status_code=404)
        self.execution_id = execution_id


class ExecutionConflictError(ExecutionServiceError):
    """Raised when an execution state conflict or duplicate idempotency key occurs."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409)


# ---------------------------------------------------------------------------
# Approval Guard & Validation
# ---------------------------------------------------------------------------

def validate_workflow_for_execution(workflow: Optional[WorkflowDefinition], workflow_id: str) -> WorkflowDefinition:
    """
    Validate that a workflow is eligible for execution:
    1. Workflow exists.
    2. Workflow status is strictly 'approved'.
    3. Workflow definition is structurally valid.
    4. Workflow has valid workflow_id.
    5. Workflow has at least 1 step.
    6. Step ordering is valid and contiguous (1..N).

    Raises:
        WorkflowNotFoundError (404)
        WorkflowNotApprovedError (409)
        WorkflowInvalidError (422)
    """
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id)

    if not workflow.workflow_id or not workflow.workflow_id.strip():
        raise WorkflowInvalidError("Workflow has an empty or invalid workflow_id.")

    # Critical hard approval guard
    if workflow.status != "approved":
        logger.warning(
            "Execution blocked by approval guard for workflow %s (status=%s).",
            workflow.workflow_id,
            workflow.status,
        )
        raise WorkflowNotApprovedError(
            workflow_id=workflow.workflow_id,
            current_status=workflow.status,
        )

    # Structural validations
    if not workflow.steps or len(workflow.steps) == 0:
        raise WorkflowInvalidError(
            f"Workflow '{workflow.workflow_id}' has no steps to execute."
        )

    # Validate step ordering: must be 1..N contiguous without duplicates or gaps
    orders = [s.order for s in workflow.steps]
    expected_orders = list(range(1, len(workflow.steps) + 1))
    if sorted(orders) != expected_orders:
        raise WorkflowInvalidError(
            f"Workflow '{workflow.workflow_id}' has invalid step ordering: {orders}. "
            f"Expected contiguous sequence {expected_orders}."
        )

    # Validate each step has required structural identifiers
    for step in workflow.steps:
        if not step.step_id or not step.step_id.strip():
            raise WorkflowInvalidError(
                f"Step order {step.order} is missing a valid step_id."
            )
        if not step.application or not step.application.strip():
            raise WorkflowInvalidError(
                f"Step order {step.order} is missing application declaration."
            )
        if not step.action or not step.action.strip():
            raise WorkflowInvalidError(
                f"Step order {step.order} is missing action declaration."
            )

    return workflow


# ---------------------------------------------------------------------------
# Execution Operations
# ---------------------------------------------------------------------------

def create_execution_record(
    workflow: WorkflowDefinition,
    mode: ExecutionMode = ExecutionMode.DRY_RUN,
    idempotency_key: Optional[str] = None,
    trigger_override: Optional[Dict[str, Any]] = None,
) -> WorkflowExecution:
    """
    Create a new execution record in PENDING state.

    Performs approval guard check first.
    """
    validate_workflow_for_execution(workflow, workflow.workflow_id)

    trigger_data: Dict[str, Any] = {}
    if trigger_override:
        trigger_data = trigger_override
    elif workflow.trigger:
        trigger_data = workflow.trigger.model_dump()

    execution = WorkflowExecution(
        execution_id=str(uuid4()),
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.name,
        status=ExecutionStatus.PENDING,
        mode=mode,
        trigger_info=trigger_data,
        total_steps=len(workflow.steps),
        completed_steps=0,
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
    )

    try:
        db_insert_execution(execution)
    except DbExecutionConflictError as exc:
        raise ExecutionConflictError(str(exc)) from exc
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc

    return execution


def get_execution(execution_id: str) -> WorkflowExecution:
    """Retrieve an execution record by execution_id."""
    if not execution_id or not execution_id.strip():
        raise ExecutionNotFoundError(execution_id)

    try:
        record = db_get_execution_by_id(execution_id.strip())
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc

    if not record:
        raise ExecutionNotFoundError(execution_id)
    return record


def list_executions_for_workflow(
    workflow_id: Optional[str] = None,
    limit: int = 50,
) -> List[WorkflowExecution]:
    """List execution records, optionally filtered by workflow_id."""
    try:
        return db_list_executions(workflow_id=workflow_id, limit=limit)
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc


def update_status(
    execution_id: str,
    status: ExecutionStatus,
    current_step: Optional[int] = None,
    completed_steps: Optional[int] = None,
    failed_step: Optional[int] = None,
    error_information: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> WorkflowExecution:
    """Safely update execution lifecycle status."""
    try:
        return db_update_execution_status(
            execution_id=execution_id,
            status=status,
            current_step=current_step,
            completed_steps=completed_steps,
            failed_step=failed_step,
            error_information=error_information,
            started_at=started_at,
            completed_at=completed_at,
        )
    except DbExecutionNotFoundError:
        raise ExecutionNotFoundError(execution_id)
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc


# ---------------------------------------------------------------------------
# Safe Dry-Run Engine
# ---------------------------------------------------------------------------

def execute_dry_run(
    workflow_id: str,
    idempotency_key: Optional[str] = None,
    trigger_override: Optional[Dict[str, Any]] = None,
) -> WorkflowExecution:
    """
    Execute a safe, simulated dry-run of an approved workflow.

    Workflow Life Cycle & Invariants:
        1. Checks idempotency: if idempotency_key is provided and exists, returns it.
        2. Retrieves the workflow; raises WorkflowNotFoundError (404) if missing.
        3. Hard Guard: validates status == 'approved'; raises WorkflowNotApprovedError (409) if not.
        4. Validates structural definition; raises WorkflowInvalidError (422) if invalid.
        5. Creates WorkflowExecution in 'pending' state.
        6. Transitions to 'running'.
        7. Walks through each step, simulating the action without ANY external calls.
        8. Records simulated ExecutionStepRecord for each step with status='dry_run'.
        9. Marks execution 'completed' with completed_at timestamp.
        10. Persists and returns the completed execution audit record.
    """
    # 1. Idempotency check
    if idempotency_key:
        try:
            existing = db_get_execution_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(
                    "Idempotency match found for key '%s': returning execution %s.",
                    idempotency_key,
                    existing.execution_id,
                )
                return existing
        except ExecutionStorageError as exc:
            raise ExecutionServiceError(str(exc), status_code=503) from exc

    # 2. Retrieve workflow
    try:
        workflow = db_get_workflow_by_id(workflow_id)
    except Exception as exc:
        logger.error("Failed to query workflow %s: %s", workflow_id, exc)
        raise ExecutionServiceError(f"Database error: {exc}", status_code=503) from exc

    # 3 & 4. Guard & Validation
    validated_wf = validate_workflow_for_execution(workflow, workflow_id)

    # 5. Create Execution Record (PENDING)
    execution = create_execution_record(
        workflow=validated_wf,
        mode=ExecutionMode.DRY_RUN,
        idempotency_key=idempotency_key,
        trigger_override=trigger_override,
    )

    # 6. Transition to RUNNING
    now = datetime.now(timezone.utc)
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = now
    execution.updated_at = now
    execution.current_step = 1

    # 7 & 8. Step Simulation Loop (ZERO external network calls)
    step_records: List[ExecutionStepRecord] = []
    sorted_steps = sorted(validated_wf.steps, key=lambda s: s.order)

    for step in sorted_steps:
        step_now = datetime.now(timezone.utc)
        execution.current_step = step.order

        simulated_step = ExecutionStepRecord(
            step_id=step.step_id,
            order=step.order,
            application=step.application,
            action=step.action,
            status=ExecutionStepStatus.DRY_RUN,
            started_at=step_now,
            completed_at=step_now,
            result_summary=f"DRY RUN — Simulating {step.application} / {step.action}. No external action performed.",
            error_summary=None,
        )
        step_records.append(simulated_step)
        execution.completed_steps = step.order

    # 9. Mark COMPLETED
    end_time = datetime.now(timezone.utc)
    execution.step_records = step_records
    execution.status = ExecutionStatus.COMPLETED
    execution.completed_steps = len(sorted_steps)
    execution.current_step = None
    execution.completed_at = end_time
    execution.updated_at = end_time

    # 10. Persist and return
    try:
        saved_execution = db_save_execution(execution)
        logger.info(
            "Dry-run execution %s completed successfully for workflow %s (%d steps simulated).",
            saved_execution.execution_id,
            workflow_id,
            len(sorted_steps),
        )
        return saved_execution
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc


# ---------------------------------------------------------------------------
# Live Execution Engine — Phase 8 Step 8.3
# ---------------------------------------------------------------------------

def execute_live(
    workflow_id: str,
    idempotency_key: Optional[str] = None,
    trigger_override: Optional[Dict[str, Any]] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> WorkflowExecution:
    """
    Execute an approved workflow in LIVE mode with real external integrations.

    Workflow Life Cycle & Invariants:
        1. Checks idempotency: if idempotency_key is provided and exists, returns it.
        2. Retrieves the workflow; raises WorkflowNotFoundError (404) if missing.
        3. Hard Guard: validates status == 'approved'; raises WorkflowNotApprovedError (409) if not.
        4. Validates structural definition; raises WorkflowInvalidError (422) if invalid.
        5. Creates WorkflowExecution in 'pending' state with mode=LIVE.
        6. Transitions to 'running'.
        7. Walks through each step, resolving adapter from IntegrationRegistry:
           - Supported steps (e.g. Slack / send_message) execute via registered adapter.
           - Unsupported steps fail safely with FAILED or NEEDS_INTERVENTION and halt execution.
        8. Records ExecutionStepRecord for each executed step with sanitized summaries.
        9. Marks execution 'completed' (or 'failed' / 'needs_intervention') with timestamps.
        10. Persists and returns the completed execution audit record.
    """
    # 1. Idempotency check
    if idempotency_key:
        try:
            existing = db_get_execution_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(
                    "Idempotency match found for key '%s': returning existing execution %s.",
                    idempotency_key,
                    existing.execution_id,
                )
                return existing
        except ExecutionStorageError as exc:
            raise ExecutionServiceError(str(exc), status_code=503) from exc

    # 2. Retrieve workflow
    try:
        workflow = db_get_workflow_by_id(workflow_id)
    except Exception as exc:
        logger.error("Failed to query workflow %s: %s", workflow_id, exc)
        raise ExecutionServiceError(f"Database error: {exc}", status_code=503) from exc

    # 3 & 4. Hard Approval Guard & Structural Validation
    validated_wf = validate_workflow_for_execution(workflow, workflow_id)

    # 5. Create Execution Record (PENDING, mode=LIVE)
    execution = create_execution_record(
        workflow=validated_wf,
        mode=ExecutionMode.LIVE,
        idempotency_key=idempotency_key,
        trigger_override=trigger_override,
    )

    # 6. Transition to RUNNING
    now = datetime.now(timezone.utc)
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = now
    execution.updated_at = now
    execution.current_step = 1

    # 7 & 8. Step Execution Loop via Integration Registry
    step_records: List[ExecutionStepRecord] = []
    sorted_steps = sorted(validated_wf.steps, key=lambda s: s.order)

    runtime_vars: Dict[str, Any] = {}
    if trigger_override:
        runtime_vars.update(trigger_override)
    if variables:
        runtime_vars.update(variables)

    registry = get_integration_registry()
    has_failed = False

    for step in sorted_steps:
        step_start_time = datetime.now(timezone.utc)
        execution.current_step = step.order

        adapter = registry.get_adapter(step.application, step.action)

        if adapter is None:
            # Unsupported integration action — fail safely
            error_msg = (
                f"Unsupported integration action: '{step.application}' / '{step.action}'. "
                "No adapter available."
            )
            sanitized_err = sanitize_text(error_msg)
            logger.warning(
                "Execution %s step %d blocked: %s",
                execution.execution_id,
                step.order,
                sanitized_err,
            )

            failed_step_rec = ExecutionStepRecord(
                step_id=step.step_id,
                order=step.order,
                application=step.application,
                action=step.action,
                status=ExecutionStepStatus.FAILED,
                started_at=step_start_time,
                completed_at=datetime.now(timezone.utc),
                result_summary="Execution halted: unsupported integration action.",
                error_summary=sanitized_err,
            )
            step_records.append(failed_step_rec)
            execution.failed_step = step.order
            execution.error_information = sanitized_err

            if (
                step.on_failure == "human_intervention"
                or validated_wf.error_handling.on_step_failure == "request_human_intervention"
            ):
                execution.status = ExecutionStatus.NEEDS_INTERVENTION
            else:
                execution.status = ExecutionStatus.FAILED

            has_failed = True
            break

        # Supported action — execute through adapter
        context = StepExecutionContext(
            workflow_id=validated_wf.workflow_id,
            execution_id=execution.execution_id,
            step=step,
            variables=dict(runtime_vars),
            dry_run=False,
        )

        try:
            step_result = adapter.execute(context)
        except Exception as exc:
            sanitized_exc = sanitize_text(f"Unhandled adapter exception: {exc}")
            logger.error("Step execution threw exception: %s", sanitized_exc)
            step_result = StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Step failed with unhandled exception.",
                error_summary=sanitized_exc,
            )

        step_end_time = datetime.now(timezone.utc)
        step_rec = ExecutionStepRecord(
            step_id=step.step_id,
            order=step.order,
            application=step.application,
            action=step.action,
            status=step_result.status,
            started_at=step_start_time,
            completed_at=step_end_time,
            result_summary=sanitize_text(step_result.result_summary),
            error_summary=sanitize_text(step_result.error_summary),
        )
        step_records.append(step_rec)

        if step_result.success:
            if step_result.outputs:
                runtime_vars.update(step_result.outputs)
            execution.completed_steps = step.order
        else:
            execution.failed_step = step.order
            execution.error_information = sanitize_text(step_result.error_summary)

            if (
                step.on_failure == "human_intervention"
                or validated_wf.error_handling.on_step_failure == "request_human_intervention"
            ):
                execution.status = ExecutionStatus.NEEDS_INTERVENTION
            else:
                execution.status = ExecutionStatus.FAILED

            has_failed = True
            break

    # 9. Conclude status & timestamps
    end_time = datetime.now(timezone.utc)
    execution.step_records = step_records
    execution.current_step = None
    execution.completed_at = end_time
    execution.updated_at = end_time

    if not has_failed:
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_steps = len(sorted_steps)

    # 10. Persist and return
    try:
        saved_execution = db_save_execution(execution)
        logger.info(
            "Live execution %s finished with status '%s' for workflow %s (%d steps recorded).",
            saved_execution.execution_id,
            saved_execution.status.value,
            workflow_id,
            len(step_records),
        )
        return saved_execution
    except ExecutionStorageError as exc:
        raise ExecutionServiceError(str(exc), status_code=503) from exc

