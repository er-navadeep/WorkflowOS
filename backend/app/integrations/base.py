"""
Base Integration Abstraction — Phase 8 Step 8.3
================================================
Defines abstract contracts for external application adapters, step execution contexts,
step results, and secret sanitization helpers.

Extensible for Slack (Phase 8.3) and future integrations (Gmail, CRM).
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.schemas.execution import ExecutionStepStatus
from app.schemas.workflow import WorkflowStep


# ---------------------------------------------------------------------------
# Sanitization Helper
# ---------------------------------------------------------------------------

_SLACK_WEBHOOK_REGEX = re.compile(
    r"https://hooks\.slack\.com/services/[A-Za-z0-9/_\-]+",
    re.IGNORECASE,
)
_TOKEN_REGEX = re.compile(
    r"xox[baprs]-[A-Za-z0-9\-]+",
    re.IGNORECASE,
)
_BEARER_REGEX = re.compile(
    r"Bearer\s+[A-Za-z0-9_.\-]+",
    re.IGNORECASE,
)
_GOOGLE_TOKEN_REGEX = re.compile(
    r"ya29\.[A-Za-z0-9_\-]+",
    re.IGNORECASE,
)
_GOOGLE_SECRET_REGEX = re.compile(
    r"GOCSPX-[A-Za-z0-9_\-]+",
    re.IGNORECASE,
)


def sanitize_text(text: Optional[str]) -> Optional[str]:
    """
    Sanitize text by removing or redacting known secrets and secret patterns.

    Guarantees:
    - SLACK_WEBHOOK_URL is never exposed.
    - LLM_API_KEY / GEMINI_API_KEY are never exposed.
    - Bearer tokens and Slack token patterns are redacted.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)

    sanitized = text

    # Redact active environment secrets if present
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if slack_webhook and len(slack_webhook) > 10:
        sanitized = sanitized.replace(slack_webhook, "[REDACTED_WEBHOOK_URL]")

    for env_key in (
        "LLM_API_KEY",
        "GEMINI_API_KEY",
        "SLACK_BOT_TOKEN",
        "SLACK_CLIENT_SECRET",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
    ):
        val = os.getenv(env_key, "").strip()
        if val and len(val) > 4:
            sanitized = sanitized.replace(val, f"[REDACTED_{env_key}]")

    # Redact pattern-based tokens and webhooks
    sanitized = _SLACK_WEBHOOK_REGEX.sub("[REDACTED_WEBHOOK_URL]", sanitized)
    sanitized = _TOKEN_REGEX.sub("[REDACTED_TOKEN]", sanitized)
    sanitized = _BEARER_REGEX.sub("Bearer [REDACTED]", sanitized)
    sanitized = _GOOGLE_TOKEN_REGEX.sub("[REDACTED_OAUTH_TOKEN]", sanitized)
    sanitized = _GOOGLE_SECRET_REGEX.sub("[REDACTED_CLIENT_SECRET]", sanitized)

    return sanitized


# ---------------------------------------------------------------------------
# Execution Context & Result Models
# ---------------------------------------------------------------------------

class StepExecutionContext(BaseModel):
    """
    Runtime execution context supplied to an integration adapter for a single step.
    """

    workflow_id: str = Field(description="ID of the workflow being executed.")
    execution_id: str = Field(description="Unique ID of this execution run.")
    step: WorkflowStep = Field(description="The workflow step being executed.")
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current runtime variables and prior step outputs.",
    )
    dry_run: bool = Field(
        default=False,
        description="True if running in simulated dry-run mode (zero external calls).",
    )


class StepExecutionResult(BaseModel):
    """
    Result returned by an integration adapter after executing a step.
    """

    success: bool = Field(description="True if the step completed successfully.")
    status: ExecutionStepStatus = Field(
        description="Step status: completed, failed, or dry_run."
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Outputs produced by this step, available to subsequent steps.",
    )
    result_summary: str = Field(
        description="Sanitized human-readable summary of the step result."
    )
    error_summary: Optional[str] = Field(
        default=None,
        description="Sanitized error summary if step failed.",
    )


# ---------------------------------------------------------------------------
# Base Adapter Interface
# ---------------------------------------------------------------------------

class BaseIntegrationAdapter(ABC):
    """
    Abstract base class for all WorkFlowOS external application adapters.
    """

    @property
    @abstractmethod
    def application_name(self) -> str:
        """Name of the application this adapter handles (e.g. 'Slack', 'Gmail', 'CRM')."""
        ...

    @abstractmethod
    def can_handle(self, action: str) -> bool:
        """Return True if this adapter supports the given action."""
        ...

    @abstractmethod
    def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute the step action.

        If context.dry_run is True, the adapter MUST NOT make any network call
        and must return status=ExecutionStepStatus.DRY_RUN with a safe summary.
        """
        ...
