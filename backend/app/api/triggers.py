"""
Triggers API Router — Phase 8.11 Step 4
=======================================
REST API endpoints for managing automatic workflow triggers,
querying automation status, toggling enable/disable, and manual on-demand polling.

Endpoints:
    GET  /api/v1/triggers
    GET  /api/v1/triggers/{workflow_id}
    POST /api/v1/triggers/{workflow_id}/enable
    POST /api/v1/triggers/{workflow_id}/disable
    POST /api/v1/triggers/{workflow_id}/poll
    GET  /api/v1/triggers/{workflow_id}/feedback

Security & Architectural Guardrails:
    - Hard Approval Guard: Unapproved workflows ('generated' or 'rejected') CANNOT be enabled.
    - Zero Secrets: API responses never contain credentials, OAuth secrets, or webhooks.
    - Single-Tenant: Governed under the local WorkFlowOS environment.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.execution import list_executions
from app.models.trigger import (
    get_trigger_by_workflow_id,
    list_checkpoints_for_workflow,
    list_triggers,
    set_trigger_enabled,
    update_trigger,
    upsert_trigger_config,
)
from app.models.workflow import get_workflow_by_id
from app.schemas.trigger import (
    TriggerCheckpoint,
    TriggerStatus,
    WorkflowTriggerConfig,
)
from app.services.trigger_service import TriggerPollSummary, poll_triggers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triggers", tags=["Workflow Triggers"])


# ---------------------------------------------------------------------------
# Feedback Schema
# ---------------------------------------------------------------------------

class WorkflowFeedbackReport(BaseModel):
    workflow_id: str
    total_executions: int
    completed_count: int
    failed_count: int
    intervention_count: int
    completion_rate_pct: float
    common_failure_steps: List[int] = []
    latest_outcome: Optional[str] = None
    feedback_recommendation: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# GET /triggers
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=List[WorkflowTriggerConfig],
    status_code=status.HTTP_200_OK,
    summary="List all workflow trigger configurations",
    description="Retrieve trigger configurations with optional filtering by application, enabled state, and status.",
)
def list_triggers_endpoint(
    application: Optional[str] = Query(default=None, description="Filter by emitting application (e.g. Gmail)"),
    is_enabled: Optional[bool] = Query(default=None, description="Filter by active enabled state"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status (active, paused, error)"),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[WorkflowTriggerConfig]:
    """List triggers from MongoDB."""
    return list_triggers(
        application=application,
        is_enabled=is_enabled,
        status=status_filter,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /triggers/{workflow_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{workflow_id}",
    response_model=WorkflowTriggerConfig,
    status_code=status.HTTP_200_OK,
    summary="Get trigger configuration for a workflow",
    description="Retrieve trigger configuration for the specified workflow. Auto-initializes a default config if workflow exists.",
)
def get_trigger_endpoint(workflow_id: str) -> WorkflowTriggerConfig:
    """Retrieve trigger config for a workflow."""
    wf_id = workflow_id.strip()
    trigger = get_trigger_by_workflow_id(wf_id)
    if trigger:
        return trigger

    # Check if workflow exists to auto-synthesize default paused trigger
    wf = get_workflow_by_id(wf_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{wf_id}' not found.",
        )

    # Initialize a default inactive trigger configuration from the workflow definition
    app_name = wf.trigger.application if wf.trigger else "Gmail"
    event_name = wf.trigger.event if wf.trigger else "new_event"

    new_trigger = WorkflowTriggerConfig(
        workflow_id=wf.workflow_id,
        application=app_name,
        event=event_name,
        query_filter="label:INBOX is:unread" if app_name.lower() == "gmail" else None,
        poll_interval_seconds=30,
        is_enabled=False,
        status=TriggerStatus.PAUSED,
    )
    return upsert_trigger_config(new_trigger)


# ---------------------------------------------------------------------------
# POST /triggers/{workflow_id}/enable
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/enable",
    response_model=WorkflowTriggerConfig,
    status_code=status.HTTP_200_OK,
    summary="Enable automatic triggering for an approved workflow",
    description="Enables automated polling. Strictly requires the workflow to be in status 'approved'.",
)
def enable_trigger_endpoint(workflow_id: str) -> WorkflowTriggerConfig:
    """Enable automation for a workflow."""
    wf_id = workflow_id.strip()
    wf = get_workflow_by_id(wf_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{wf_id}' not found.",
        )

    # Hard Approval Guard
    if wf.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot enable automation for workflow '{wf_id}': status is '{wf.status}'. "
                "Only 'approved' workflows can have automated triggers enabled."
            ),
        )

    # Ensure trigger config exists
    trigger = get_trigger_by_workflow_id(wf_id)
    if not trigger:
        app_name = wf.trigger.application if wf.trigger else "Gmail"
        event_name = wf.trigger.event if wf.trigger else "new_event"
        trigger = WorkflowTriggerConfig(
            workflow_id=wf.workflow_id,
            application=app_name,
            event=event_name,
            query_filter="label:INBOX is:unread" if app_name.lower() == "gmail" else None,
            poll_interval_seconds=30,
            is_enabled=True,
            status=TriggerStatus.ACTIVE,
        )
        return upsert_trigger_config(trigger)

    return set_trigger_enabled(wf_id, True)


# ---------------------------------------------------------------------------
# POST /triggers/{workflow_id}/disable
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/disable",
    response_model=WorkflowTriggerConfig,
    status_code=status.HTTP_200_OK,
    summary="Disable automatic triggering for a workflow",
    description="Pauses automated execution without affecting workflow approval status.",
)
def disable_trigger_endpoint(workflow_id: str) -> WorkflowTriggerConfig:
    """Disable/pause automation for a workflow."""
    wf_id = workflow_id.strip()
    trigger = get_trigger_by_workflow_id(wf_id)
    if not trigger:
        # Check workflow exists
        wf = get_workflow_by_id(wf_id)
        if not wf:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{wf_id}' not found.",
            )
        trigger = WorkflowTriggerConfig(
            workflow_id=wf.workflow_id,
            application=wf.trigger.application if wf.trigger else "Gmail",
            event=wf.trigger.event if wf.trigger else "new_event",
            is_enabled=False,
            status=TriggerStatus.PAUSED,
        )
        return upsert_trigger_config(trigger)

    return set_trigger_enabled(wf_id, False)


# ---------------------------------------------------------------------------
# POST /triggers/{workflow_id}/poll
# ---------------------------------------------------------------------------

@router.post(
    "/{workflow_id}/poll",
    response_model=TriggerPollSummary,
    status_code=status.HTTP_200_OK,
    summary="Trigger on-demand polling check for a workflow",
    description="Performs an immediate controlled polling check for incoming events and dispatches execution if new events are found.",
)
def poll_trigger_endpoint(
    workflow_id: str,
    dry_run: bool = Query(default=False, description="Run simulation without real external actions"),
) -> TriggerPollSummary:
    """Perform immediate on-demand polling check."""
    wf_id = workflow_id.strip()
    wf = get_workflow_by_id(wf_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{wf_id}' not found.",
        )

    # Ensure trigger config exists
    trigger = get_trigger_by_workflow_id(wf_id)
    if not trigger:
        trigger = WorkflowTriggerConfig(
            workflow_id=wf.workflow_id,
            application=wf.trigger.application if wf.trigger else "Gmail",
            event=wf.trigger.event if wf.trigger else "new_event",
            query_filter="label:INBOX is:unread" if (wf.trigger and wf.trigger.application.lower() == "gmail") else None,
            is_enabled=True,
            status=TriggerStatus.ACTIVE,
        )
        upsert_trigger_config(trigger)

    return poll_triggers(dry_run=dry_run, workflow_id=wf_id)


# ---------------------------------------------------------------------------
# GET /triggers/{workflow_id}/feedback
# ---------------------------------------------------------------------------

@router.get(
    "/{workflow_id}/feedback",
    response_model=WorkflowFeedbackReport,
    status_code=status.HTTP_200_OK,
    summary="Retrieve execution feedback and audit metrics",
    description="Aggregates past execution outcomes to establish feedback loops for workflow reliability.",
)
def get_workflow_feedback_endpoint(workflow_id: str) -> WorkflowFeedbackReport:
    """Generate execution feedback analysis."""
    wf_id = workflow_id.strip()
    wf = get_workflow_by_id(wf_id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow '{wf_id}' not found.",
        )

    executions = list_executions(workflow_id=wf_id, limit=100)
    total = len(executions)
    completed = sum(1 for e in executions if e.status.value == "completed")
    failed = sum(1 for e in executions if e.status.value == "failed")
    interventions = sum(1 for e in executions if e.status.value == "needs_intervention")

    rate = (completed / total * 100.0) if total > 0 else 100.0

    failure_steps: List[int] = [e.failed_step for e in executions if e.failed_step is not None]
    latest_outcome = executions[0].status.value if executions else "none"

    if total == 0:
        recommendation = "No executions recorded yet. Enable automation or run dry-run to begin auditing."
    elif rate >= 90.0:
        recommendation = "High automation reliability (>90% success). Workflow execution pattern is stable."
    elif interventions > 0:
        recommendation = f"{interventions} run(s) required human intervention. Review variable flow and external record preconditions."
    else:
        recommendation = "Elevated failure rate detected. Inspect error logs and verify integration endpoints."

    return WorkflowFeedbackReport(
        workflow_id=wf_id,
        total_executions=total,
        completed_count=completed,
        failed_count=failed,
        intervention_count=interventions,
        completion_rate_pct=round(rate, 1),
        common_failure_steps=list(set(failure_steps)),
        latest_outcome=latest_outcome,
        feedback_recommendation=recommendation,
    )
