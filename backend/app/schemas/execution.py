"""
Execution Schemas — Phase 8 Step 8.1
====================================
Pydantic schemas for WorkFlowOS execution records, execution lifecycle status,
and dry-run simulation results.

Phase 8.1 provides the safe execution foundation:
    - Governed execution lifecycle (pending -> running -> completed | failed | cancelled | needs_intervention)
    - Step-level execution audit records
    - Hard approval guard (only 'approved' workflows may be executed)
    - Safe dry-run execution (simulation without external side-effects)
    - Zero external integrations (Gmail, Slack, CRM are NOT implemented)
    - Zero secrets/credentials storage
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExecutionStatus(str, Enum):
    """Controlled lifecycle statuses for workflow executions."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INTERVENTION = "needs_intervention"


class ExecutionStepStatus(str, Enum):
    """Lifecycle statuses for individual execution steps."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class ExecutionMode(str, Enum):
    """Execution mode: dry-run (simulation) or live (not implemented in 8.1)."""

    DRY_RUN = "dry_run"
    LIVE = "live"


# ---------------------------------------------------------------------------
# Step Record Schema
# ---------------------------------------------------------------------------

class ExecutionStepRecord(BaseModel):
    """
    Audit record for a single step within a workflow execution.

    Contains step metadata, simulation status, timing, and safe summaries.
    CRITICAL: Never stores passwords, tokens, API keys, or raw payloads.
    """

    step_id: str = Field(
        description="Unique identifier of the workflow step being executed."
    )
    order: int = Field(
        ge=1,
        description="1-based step order matching WorkflowStep.order."
    )
    application: str = Field(
        description="Target application (e.g., 'Gmail', 'Slack', 'CRM')."
    )
    action: str = Field(
        description="Action to perform (e.g., 'read_email', 'find_customer')."
    )
    status: ExecutionStepStatus = Field(
        default=ExecutionStepStatus.PENDING,
        description="Step status: pending, running, completed, failed, skipped, or dry_run."
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when step execution started."
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when step execution completed."
    )
    result_summary: Optional[str] = Field(
        default=None,
        description="Safe, sanitized summary of step outcome (e.g. simulated dry-run output)."
    )
    error_summary: Optional[str] = Field(
        default=None,
        description="Sanitized error summary if step failed. No credentials or trace leaks."
    )


# ---------------------------------------------------------------------------
# Workflow Execution Record Schema
# ---------------------------------------------------------------------------

class WorkflowExecution(BaseModel):
    """
    Complete audit and state record for a workflow execution.

    Stored in the 'executions' MongoDB collection.
    """

    execution_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this execution run."
    )
    workflow_id: str = Field(
        description="ID of the workflow being executed."
    )
    workflow_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the workflow at time of execution."
    )
    status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING,
        description="Current lifecycle status of the execution."
    )
    mode: ExecutionMode = Field(
        default=ExecutionMode.DRY_RUN,
        description="Execution mode: 'dry_run' or 'live'."
    )
    trigger_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Information about the event or context that triggered execution."
    )
    current_step: Optional[int] = Field(
        default=None,
        description="Order number of the currently active step, if running."
    )
    total_steps: int = Field(
        default=0,
        ge=0,
        description="Total number of steps in this workflow."
    )
    completed_steps: int = Field(
        default=0,
        ge=0,
        description="Number of steps completed or simulated."
    )
    failed_step: Optional[int] = Field(
        default=None,
        description="Order number of the step that failed, if any."
    )
    step_records: List[ExecutionStepRecord] = Field(
        default_factory=list,
        description="Chronological step execution records."
    )
    error_information: Optional[str] = Field(
        default=None,
        description="Sanitized summary of execution error if status is 'failed'."
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional idempotency key to prevent duplicate runs."
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when execution entered 'running' status."
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when execution concluded (completed, failed, cancelled)."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when execution record was created."
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of last status or step update."
    )


# ---------------------------------------------------------------------------
# API Request / Response Schemas
# ---------------------------------------------------------------------------

class DryRunExecutionRequest(BaseModel):
    """Optional request payload for POST /api/v1/executions/dry-run/{workflow_id}."""

    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional idempotency key to prevent duplicate dry-runs."
    )
    trigger_override: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional context override for the trigger."
    )

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None


class LiveExecutionRequest(BaseModel):
    """Optional request payload for POST /api/v1/executions/live/{workflow_id}."""

    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional idempotency key to prevent duplicate live executions."
    )
    trigger_override: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional context override for the trigger."
    )
    variables: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional runtime variable inputs (e.g. requestNotificationText) to pass to steps."
    )

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            return cleaned if cleaned else None
        return None


class WorkflowExecutionResponse(BaseModel):
    """API response envelope for execution operations."""

    success: bool
    execution_id: str
    workflow_id: str
    status: str
    message: str
    execution: WorkflowExecution
