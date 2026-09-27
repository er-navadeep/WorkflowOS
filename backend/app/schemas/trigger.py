"""
Trigger Schemas — Phase 8.11.1
==============================
Pydantic schemas for WorkFlowOS automatic workflow trigger configurations,
trigger lifecycle statuses, and event deduplication checkpoints.

Architectural Guarantees:
    - Zero secrets: Trigger configs store only metadata and operational parameters.
      Never store OAuth tokens, API keys, webhook URLs, or passwords.
    - Single-tenant: Operates within the local WorkFlowOS environment without
      unauthenticated tenant/user pollution.
    - Non-executable: Schemas define pure data contracts without execution logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_POLL_INTERVAL_SECONDS: int = 5
DEFAULT_POLL_INTERVAL_SECONDS: int = 30


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TriggerStatus(str, Enum):
    """
    Lifecycle status of an automated trigger configuration.
    
    Supported states:
        ACTIVE: Trigger is enabled and actively eligible for scheduled polling.
        PAUSED: Trigger is paused / disabled; polling will skip this workflow.
        ERROR:  Trigger encountered repeated failures and is quarantined.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"

    @classmethod
    def _missing_(cls, value: object) -> Optional[TriggerStatus]:
        if isinstance(value, str):
            val_lower = value.strip().lower()
            for member in cls:
                if member.value == val_lower:
                    return member
        return None


# ---------------------------------------------------------------------------
# Trigger Configuration Schema
# ---------------------------------------------------------------------------

class WorkflowTriggerConfig(BaseModel):
    """
    Persistent configuration for an automated workflow trigger.

    Bound to an approved WorkflowDefinition by workflow_id.
    """

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        extra="forbid",
    )

    trigger_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this trigger configuration.",
    )
    workflow_id: str = Field(
        ...,
        description="ID of the target approved workflow.",
    )
    application: str = Field(
        ...,
        description="Application emitting the triggering event (e.g. 'Gmail').",
    )
    event: str = Field(
        ...,
        description="Human-readable event name (e.g. 'customer_email_received').",
    )
    query_filter: Optional[str] = Field(
        default=None,
        description="Optional application query filter (e.g. 'label:INBOX is:unread').",
    )
    poll_interval_seconds: int = Field(
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        ge=MIN_POLL_INTERVAL_SECONDS,
        description=f"Polling frequency in seconds (minimum {MIN_POLL_INTERVAL_SECONDS}s).",
    )
    is_enabled: bool = Field(
        default=False,
        description="Whether this trigger is actively enabled for automated execution.",
    )
    status: TriggerStatus = Field(
        default=TriggerStatus.PAUSED,
        description="Operational status: ACTIVE, PAUSED, or ERROR.",
    )
    last_polled_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the last polling check.",
    )
    last_triggered_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the most recent execution triggered.",
    )
    consecutive_errors: int = Field(
        default=0,
        ge=0,
        description="Count of consecutive errors encountered during polling.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this trigger configuration was created.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the most recent configuration update.",
    )

    @field_validator("workflow_id", "application", "event")
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        if not value or not str(value).strip():
            raise ValueError(f"'{info.field_name}' must not be empty or whitespace.")
        return str(value).strip()

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if isinstance(value, str):
            val_lower = value.strip().lower()
            if val_lower in ("active", "paused", "error"):
                return TriggerStatus(val_lower)
        return value


# ---------------------------------------------------------------------------
# Trigger Checkpoint Schema
# ---------------------------------------------------------------------------

class TriggerCheckpoint(BaseModel):
    """
    Deduplication record representing one processed external event.

    Guarantees that a specific external event (such as a Gmail messageId)
    is never processed more than once by the same workflow.
    """

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        extra="forbid",
    )

    checkpoint_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this checkpoint record.",
    )
    workflow_id: str = Field(
        ...,
        description="Workflow ID that processed the event.",
    )
    source_application: str = Field(
        ...,
        description="Source application that emitted the event (e.g. 'Gmail').",
    )
    event_identifier: str = Field(
        ...,
        description="Immutable external event identifier (e.g. Gmail messageId).",
    )
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the event was checkpointed.",
    )
    execution_id: Optional[str] = Field(
        default=None,
        description="ID of the WorkflowExecution created for this event, if any.",
    )

    @field_validator("workflow_id", "source_application", "event_identifier")
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        if not value or not str(value).strip():
            raise ValueError(f"'{info.field_name}' must not be empty or whitespace.")
        return str(value).strip()


# ---------------------------------------------------------------------------
# Feedback / Audit Report Schema (Phase 8 Master Automation Layer)
# ---------------------------------------------------------------------------

class WorkflowFeedbackReport(BaseModel):
    """
    Structured execution feedback report summarizing reliability,
    human intervention requests, and failure patterns for workflow improvement.
    """

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        extra="forbid",
    )

    workflow_id: str
    total_executions: int
    completed_count: int
    failed_count: int
    intervention_count: int
    completion_rate_pct: float
    common_failure_steps: List[int] = Field(default_factory=list)
    latest_outcome: Optional[str] = None
    feedback_recommendation: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

