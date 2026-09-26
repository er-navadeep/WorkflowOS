"""
Workflow Understanding Schema
==============================
Pydantic models for the structured semantic understanding
that Phase 5 derives from a WorkflowCandidate via AI.

MongoDB collection: workflow_understandings

Key relationship:
    WorkflowUnderstanding.candidate_id  →  WorkflowCandidate.candidate_id
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Nested value objects
# ---------------------------------------------------------------------------

class UnderstandingAction(BaseModel):
    """
    One semantic action inferred from the observed event sequence.

    Low-level events (e.g. event_type='email', action='open_email') are
    lifted into higher-level human-readable descriptions here.
    """
    order: int = Field(description="1-based position in the workflow.")
    application: str = Field(description="Application where the action occurs.")
    operation: str = Field(
        description="Short verb-noun phrase for the action (e.g. 'Read email')."
    )
    description: str = Field(
        description="One-sentence explanation derived from the observed evidence."
    )


class UnderstandingCondition(BaseModel):
    """
    A conditional branch or guard observed or inferred from the workflow.

    The AI must only state conditions that are supported by the evidence.
    When uncertain, it should mark inferred=True.
    """
    description: str = Field(description="What the condition checks.")
    consequence: str = Field(description="What happens when the condition is true.")
    inferred: bool = Field(
        default=False,
        description=(
            "True when this condition was not directly observed but is a "
            "reasonable inference from the evidence."
        ),
    )


class UnderstandingVariable(BaseModel):
    """
    A data value that flows between steps in the workflow.

    Only variables that are visible in the observed event sequence should
    be listed; the AI must not invent hidden variables.
    """
    name: str = Field(description="Variable name (camelCase or snake_case).")
    description: str = Field(description="What this variable holds.")
    observed_in: str = Field(
        description="Application/step where this variable was first observed."
    )


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------

class WorkflowUnderstanding(BaseModel):
    """
    Semantic understanding of a WorkflowCandidate produced by AI analysis.

    Created by Phase 5; read by Phase 6 (workflow proposal generation).

    Status lifecycle:
        pending   -> generated (AI succeeded)
        pending   -> failed    (AI call failed)
    """

    # --- Identity ---
    understanding_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique understanding identifier.",
    )
    candidate_id: str = Field(
        description="ID of the source WorkflowCandidate.",
    )

    # --- Semantic core ---
    intent: str = Field(
        description="Short noun-phrase capturing the user's goal (e.g. 'Process Customer Request')."
    )
    name: str = Field(
        description="Human-readable name derived from the observed workflow."
    )
    description: str = Field(
        description="One-paragraph explanation of what the workflow does."
    )
    trigger: str = Field(
        description="What event or condition starts this workflow."
    )

    # --- Evidence-derived content ---
    applications: List[str] = Field(
        description="Applications involved, in order of first appearance."
    )
    actions: List[UnderstandingAction] = Field(
        description="Ordered list of semantic actions."
    )
    conditions: List[UnderstandingCondition] = Field(
        default_factory=list,
        description="Conditional logic observed or inferred from the sequence.",
    )
    variables: List[UnderstandingVariable] = Field(
        default_factory=list,
        description="Data values that flow between steps.",
    )

    # --- AI metadata ---
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "AI-reported confidence in the understanding (0-1). "
            "This reflects the model's uncertainty, not a calibrated score."
        ),
    )
    model_used: str = Field(
        default="",
        description="Gemini model identifier used to generate this understanding.",
    )

    # --- Lifecycle ---
    status: str = Field(
        default="generated",
        description="'generated' | 'failed' | 'pending'",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    model_config = {"json_schema_extra": {"examples": []}}


# ---------------------------------------------------------------------------
# API response envelopes
# ---------------------------------------------------------------------------

class UnderstandingResponse(BaseModel):
    """Envelope returned by POST /understanding/{candidate_id}."""
    success: bool
    understanding_id: str
    candidate_id: str
    message: str
    understanding: WorkflowUnderstanding
