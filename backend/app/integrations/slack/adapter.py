"""
Slack Adapter — Phase 8 Step 8.3
=================================
Executes Slack actions for WorkFlowOS workflows.
Supported action: 'send_message' via Slack Incoming Webhook (SLACK_WEBHOOK_URL).

Security & Guardrails:
    - Never prints, logs, or returns SLACK_WEBHOOK_URL.
    - Webhook URL is read strictly from environment at runtime.
    - Timeout enforced at 5.0 seconds.
    - Zero external network requests during dry-run simulation.
    - Fails safely on missing credentials, unsupported actions, or missing inputs.
    - Never invents customer or message data.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from app.integrations.base import (
    BaseIntegrationAdapter,
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.schemas.execution import ExecutionStepStatus

logger = logging.getLogger(__name__)


class SlackAdapter(BaseIntegrationAdapter):
    """
    Adapter for integrating WorkFlowOS with Slack.
    """

    @property
    def application_name(self) -> str:
        return "Slack"

    def can_handle(self, action: str) -> bool:
        """
        SlackAdapter supports only 'send_message' in Phase 8.3.
        """
        if not action or not isinstance(action, str):
            return False
        return action.strip().lower() == "send_message"

    def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute Slack action for the given workflow step context.
        """
        action = context.step.action.strip().lower() if context.step.action else ""
        if not self.can_handle(action):
            error_msg = f"Unsupported action '{context.step.action}' for Slack adapter."
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=f"Slack adapter does not support action '{context.step.action}'.",
                error_summary=sanitize_text(error_msg),
            )

        # -------------------------------------------------------------------
        # Dry-run handling: MUST NOT make any external network call
        # -------------------------------------------------------------------
        if context.dry_run:
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.DRY_RUN,
                outputs={},
                result_summary="Slack send_message simulated; no external request sent.",
                error_summary=None,
            )

        # -------------------------------------------------------------------
        # Configuration check: SLACK_WEBHOOK_URL
        # -------------------------------------------------------------------
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        if not webhook_url:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Slack execution failed: missing webhook configuration.",
                error_summary="Missing SLACK_WEBHOOK_URL configuration.",
            )

        # -------------------------------------------------------------------
        # Input handling: resolve message text safely
        # -------------------------------------------------------------------
        message_text = self._resolve_message(context)
        if not message_text:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Slack send_message failed: missing input text.",
                error_summary="Cannot resolve message text: required input variable not found in execution context.",
            )

        # -------------------------------------------------------------------
        # Live HTTP POST to Slack Webhook (5-second timeout)
        # -------------------------------------------------------------------
        payload_bytes = json.dumps({"text": message_text}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp_body = resp.read().decode("utf-8")

            if resp_body.strip().lower() == "ok":
                logger.info(
                    "Successfully delivered Slack message for execution %s (step %d).",
                    context.execution_id,
                    context.step.order,
                )
                return StepExecutionResult(
                    success=True,
                    status=ExecutionStepStatus.COMPLETED,
                    outputs={"slack_delivery": "delivered"},
                    result_summary="Slack message sent successfully to configured webhook channel.",
                    error_summary=None,
                )
            else:
                sanitized_resp = sanitize_text(resp_body)
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Slack webhook returned non-ok response.",
                    error_summary=f"Slack webhook error response: {sanitized_resp}",
                )

        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = str(exc)
            sanitized_err = sanitize_text(f"HTTPError {exc.code}: {err_body}")
            logger.error("Slack webhook HTTP error: %s", sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Slack webhook call failed with HTTP error.",
                error_summary=f"Slack webhook request failed: {sanitized_err}",
            )
        except urllib.error.URLError as exc:
            sanitized_err = sanitize_text(f"URLError: {exc.reason}")
            logger.error("Slack webhook URL error: %s", sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Slack webhook connection failed.",
                error_summary=f"Slack webhook request failed: {sanitized_err}",
            )
        except Exception as exc:
            sanitized_err = sanitize_text(f"{type(exc).__name__}: {exc}")
            logger.error("Slack webhook delivery failed: %s", sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Slack webhook call failed.",
                error_summary=f"Slack webhook delivery error: {sanitized_err}",
            )

    def _resolve_message(self, context: StepExecutionContext) -> Optional[str]:
        """
        Safely resolve message text from runtime variables matching step.inputs
        or explicit request parameters.

        Does NOT invent customer information or manufacture arbitrary data.
        """
        # 1. Check variables explicitly matching declared step inputs
        for inp in context.step.inputs:
            if inp in context.variables and context.variables[inp] is not None:
                val = str(context.variables[inp]).strip()
                if val:
                    return val

        # 2. Check explicit direct message overrides from execution payload
        for key in ("message", "text", "slack_message", "notification_text", "fallback_message"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    return val

        return None
