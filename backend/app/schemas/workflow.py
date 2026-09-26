"""
Workflow Definition Schema
===========================
Pydantic models for the structured WorkflowDefinition produced by Phase 6.

Phase 6 converts a Phase 5 WorkflowUnderstanding into a machine-readable
WorkflowDefinition that a future automation engine (Phase 8) can consume.

MongoDB collection: workflows

Key relationships:
    WorkflowDefinition.understanding_id → WorkflowUnderstanding.understanding_id

Status lifecycle:
    generated → (future) approved → running → completed | failed
    Phase 6 only ever sets status = "generated".
    Approval, execution, and learning belong to future phases.

Design rules:
    - No secrets, credentials, or OAuth tokens.
    - No executable code.
    - No external API calls.
    - Only data derived from the WorkflowUnderstanding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Nested value objects
# ---------------------------------------------------------------------------


class WorkflowTrigger(BaseModel):
    """
    Describes what initiates the workflow.

    Derived from the WorkflowUnderstanding.trigger field.
    Only semantic information that can be justified by the understanding
    is included.  No invented channel names, URLs, or credentials.
    """

    application: str = Field(
        description="Application that emits the triggering event (e.g. 'Gmail')."
    )
    event: str = Field(
        description=(
            "Human-readable description of the triggering event "
            "(e.g. 'New incoming customer email')."
        )
    )
    description: str = Field(
        description="One-sentence explanation of the trigger, grounded in the understanding."
    )


class WorkflowStep(BaseModel):
    """
    One executable step in the generated workflow.

    Steps are derived 1-to-1 from the UnderstandingActions in Phase 5.
    Order is 1-based and must be sequential and unique.
    """

    step_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique step identifier.",
    )
    order: int = Field(
        description="1-based position of this step in the workflow.",
        ge=1,
    )
    application: str = Field(
        description="Application that performs this step (e.g. 'Gmail', 'CRM', 'Slack')."
    )
    action: str = Field(
        description=(
            "Short verb-noun phrase for the operation to perform "
            "(e.g. 'read_email', 'find_customer', 'send_message')."
        )
    )
    description: str = Field(
        description="One-sentence explanation of what this step does."
    )
    inputs: List[str] = Field(
        default_factory=list,
        description=(
            "Variable names required as inputs for this step. "
            "Only variables visible in the understanding are listed."
        ),
    )
    outputs: List[str] = Field(
        default_factory=list,
        description=(
            "Variable names produced by this step. "
            "Only variables visible in the understanding are listed."
        ),
    )
    on_failure: str = Field(
        default="stop",
        description=(
            "'stop' — halt the workflow on failure (default). "
            "'continue' — log the error and proceed. "
            "'human_intervention' — pause and request human review."
        ),
    )


class WorkflowCondition(BaseModel):
    """
    A conditional branch in the generated workflow.

    Conditions are derived from the UnderstandingConditions in Phase 5.
    Human-intervention paths are preserved exactly as understood.
    """

    condition_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique condition identifier.",
    )
    description: str = Field(
        description="What this condition checks (e.g. 'Customer record cannot be found')."
    )
    expression: str = Field(
        description=(
            "Natural-language expression of the condition. "
            "No executable code; represents intent only."
        )
    )
    on_true: str = Field(
        description=(
            "What happens when the condition is true "
            "(e.g. 'request_human_intervention', 'stop', 'continue')."
        )
    )
    on_false: str = Field(
        default="continue",
        description="What happens when the condition is false (default: continue).",
    )


class WorkflowVariable(BaseModel):
    """
    A data value that flows between steps.

    Derived from the UnderstandingVariables in Phase 5.
    Must not contain real data, credentials, or secrets.
    """

    name: str = Field(description="Variable name (camelCase or snake_case).")
    description: str = Field(description="What this variable holds.")
    source_step_order: Optional[int] = Field(
        default=None,
        description="Order of the step that produces this variable, if known.",
    )


class WorkflowIntegration(BaseModel):
    """
    Descriptive metadata about an external application the workflow uses.

    This is NOT a connection definition.  No credentials, OAuth tokens, or
    API keys are stored here.  This is documentation-only metadata.
    """

    application: str = Field(
        description="Application name as observed (e.g. 'Gmail', 'CRM', 'Slack')."
    )
    purpose: str = Field(
        description=(
            "One-sentence description of why this application is used in the workflow."
        )
    )
    required_capabilities: List[str] = Field(
        default_factory=list,
        description=(
            "High-level capability names needed from this application "
            "(e.g. ['read_email', 'send_message']). "
            "These are semantic descriptions, not API method names."
        ),
    )


class WorkflowErrorHandling(BaseModel):
    """
    Workflow-level error handling policy.

    Specifies what happens when a step fails or a required input is missing.
    These are policy declarations only — no executable code.
    """

    on_step_failure: str = Field(
        default="stop_and_report",
        description=(
            "Default action on step failure: 'stop_and_report' | 'request_human_intervention'."
        ),
    )
    on_missing_input: str = Field(
        default="stop",
        description="Action when a required variable is not available: 'stop' | 'skip_step'.",
    )
    on_timeout: str = Field(
        default="stop_and_report",
        description="Action when a step exceeds its expected duration: 'stop_and_report' | 'retry'.",
    )
    notes: str = Field(
        default="",
        description="Any additional error-handling notes derived from the understanding.",
    )


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class WorkflowDefinition(BaseModel):
    """
    Structured workflow definition generated by Phase 6.

    Created from a Phase 5 WorkflowUnderstanding; consumed by a future
    Phase 8 automation engine after Phase 7 human approval.

    Status lifecycle (Phase 6 only sets 'generated'):
        generated → approved → running → completed | failed
    """

    # --- Identity ---
    workflow_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique workflow identifier.",
    )
    understanding_id: str = Field(
        description="ID of the source WorkflowUnderstanding.",
    )

    # --- Human-readable identity ---
    name: str = Field(description="Human-readable workflow name.")
    description: str = Field(
        description="One-paragraph explanation of what the workflow does."
    )

    # --- Workflow structure ---
    trigger: WorkflowTrigger = Field(
        description="Event that starts this workflow."
    )
    steps: List[WorkflowStep] = Field(
        description="Ordered list of steps to execute."
    )
    conditions: List[WorkflowCondition] = Field(
        default_factory=list,
        description="Conditional branches and decision points.",
    )
    variables: List[WorkflowVariable] = Field(
        default_factory=list,
        description="Data values that flow between steps.",
    )
    integrations: List[WorkflowIntegration] = Field(
        default_factory=list,
        description="Applications involved and their required capabilities.",
    )
    error_handling: WorkflowErrorHandling = Field(
        default_factory=WorkflowErrorHandling,
        description="Workflow-level error handling policy.",
    )

    # --- AI generation metadata ---
    model_used: str = Field(
        default="",
        description="Gemini model identifier used to generate this workflow.",
    )
    generation_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score inherited from the source understanding.",
    )

    # --- Lifecycle ---
    status: str = Field(
        default="generated",
        description=(
            "Lifecycle status. "
            "'generated' — set by Phase 6 AI generation. "
            "'approved' — set by Phase 7 human approval. "
            "'rejected' — set by Phase 7 human rejection. "
            "Execution phases are future work."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the workflow was first generated.",
    )

    # --- Phase 7: Human Approval fields ---
    # NOTE: reviewer_id / reviewed_by is a free-form string in Phase 7.
    #       It is NOT authenticated.  Real authentication will be integrated
    #       in a future phase.  Do not treat this value as a verified identity.
    reviewed_by: Optional[str] = Field(
        default=None,
        description=(
            "Identifier of the reviewer who approved or rejected this workflow. "
            "Phase 7: free-form string, not yet authenticated."
        ),
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Optional human-readable notes from the reviewer.",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Required when status is 'rejected'. Reason for rejection.",
    )
    approved_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the workflow was approved. None if not yet approved.",
    )
    rejected_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the workflow was rejected. None if not yet rejected.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the last status change (approval or rejection).",
    )

    model_config = {"json_schema_extra": {"examples": []}}


# ---------------------------------------------------------------------------
# API response envelopes
# ---------------------------------------------------------------------------


class WorkflowGenerationResponse(BaseModel):
    """Envelope returned by POST /workflows/generate/{understanding_id}."""

    success: bool
    workflow_id: str
    understanding_id: str
    message: str
    workflow: WorkflowDefinition


# ---------------------------------------------------------------------------
# Phase 7: Human Approval request / response schemas
# ---------------------------------------------------------------------------


class WorkflowApproveRequest(BaseModel):
    """
    Request body for POST /workflows/{workflow_id}/approve.

    reviewer_id is a free-form string identifier for the approver.
    SECURITY NOTE: This is NOT authenticated in Phase 7.  It is stored
    as supplied and will be integrated with a real auth system in a
    future phase.  Do not treat it as a verified identity.
    """

    reviewer_id: str = Field(
        description=(
            "Identifier of the reviewer approving this workflow. "
            "Free-form string in Phase 7 (not yet authenticated)."
        )
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Optional notes explaining the approval decision.",
    )

    @field_validator("reviewer_id")
    @classmethod
    def reviewer_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reviewer_id must not be empty or whitespace.")
        return v.strip()


class WorkflowRejectRequest(BaseModel):
    """
    Request body for POST /workflows/{workflow_id}/reject.

    reviewer_id is a free-form string identifier for the reviewer.
    SECURITY NOTE: This is NOT authenticated in Phase 7.  See WorkflowApproveRequest.
    """

    reviewer_id: str = Field(
        description=(
            "Identifier of the reviewer rejecting this workflow. "
            "Free-form string in Phase 7 (not yet authenticated)."
        )
    )
    rejection_reason: str = Field(
        description="Required human-readable explanation of why the workflow is rejected."
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Optional additional notes from the reviewer.",
    )

    @field_validator("reviewer_id")
    @classmethod
    def reviewer_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reviewer_id must not be empty or whitespace.")
        return v.strip()

    @field_validator("rejection_reason")
    @classmethod
    def rejection_reason_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rejection_reason must not be empty or whitespace.")
        return v.strip()


class WorkflowApprovalResponse(BaseModel):
    """
    Response envelope for POST /workflows/{workflow_id}/approve
    and POST /workflows/{workflow_id}/reject.
    """

    success: bool
    workflow_id: str
    previous_status: str
    new_status: str
    reviewed_by: str
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    message: str
