"""
Workflow Generator — Phase 6
==============================
Converts raw Gemini text output into a validated WorkflowDefinition.

Responsibilities:
- Strip markdown fences that Gemini may accidentally include.
- Parse JSON.
- Build and validate the WorkflowDefinition schema.
- Return structured errors, never raw exceptions.

Mirrors the architecture of app/ai/workflow_understanding.py from Phase 5.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.workflow import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowVariable,
)
from app.schemas.workflow_understanding import WorkflowUnderstanding

logger = logging.getLogger(__name__)


class WorkflowGenerationError(Exception):
    """Raised when the Gemini response cannot be converted to a valid WorkflowDefinition."""


def parse_workflow_response(
    raw_text: str,
    understanding: WorkflowUnderstanding,
    model_used: str,
) -> WorkflowDefinition:
    """
    Parse the raw Gemini text into a WorkflowDefinition.

    Args:
        raw_text:      Text returned by Gemini.
        understanding: The source WorkflowUnderstanding.
        model_used:    Gemini model identifier (for provenance).

    Returns:
        A validated WorkflowDefinition.

    Raises:
        WorkflowGenerationError: when the text cannot be parsed or validated.
    """
    # 1. Strip accidental markdown code fences
    cleaned = _strip_markdown_fences(raw_text)

    # 2. Parse JSON
    data = _parse_json(cleaned)

    # 3. Validate and build the model
    return _build_model(data, understanding=understanding, model_used=model_used)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers the model may add."""
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```\s*$"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_json(text: str) -> Dict[str, Any]:
    """Parse JSON text, raising WorkflowGenerationError on failure."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini workflow response is not valid JSON: %s", exc)
        raise WorkflowGenerationError(
            f"Workflow response is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise WorkflowGenerationError(
            f"Expected a JSON object, got {type(data).__name__}."
        )
    return data


def _build_model(
    data: Dict[str, Any],
    understanding: WorkflowUnderstanding,
    model_used: str,
) -> WorkflowDefinition:
    """
    Build and validate a WorkflowDefinition from a parsed dict.

    Raises WorkflowGenerationError on any structural problem.
    """
    # --- Required top-level fields ---
    required = ("name", "description", "trigger", "steps")
    missing = [k for k in required if k not in data or not data[k]]
    if missing:
        raise WorkflowGenerationError(
            f"Missing required fields in Gemini workflow response: {missing}"
        )

    # --- Trigger ---
    trigger = _build_trigger(data.get("trigger", {}))

    # --- Steps ---
    steps = _build_steps(data.get("steps", []))
    if not steps:
        raise WorkflowGenerationError("'steps' must be a non-empty list.")

    # --- Conditions ---
    conditions = _build_conditions(data.get("conditions", []))

    # --- Variables ---
    variables = _build_variables(data.get("variables", []))

    # --- Integrations ---
    integrations = _build_integrations(
        data.get("integrations", []),
        allowed_applications=understanding.applications,
    )

    # --- Error handling ---
    error_handling = _build_error_handling(data.get("error_handling", {}))

    try:
        return WorkflowDefinition(
            understanding_id=understanding.understanding_id,
            name=str(data["name"]),
            description=str(data["description"]),
            trigger=trigger,
            steps=steps,
            conditions=conditions,
            variables=variables,
            integrations=integrations,
            error_handling=error_handling,
            model_used=model_used,
            generation_confidence=understanding.confidence,
            status="generated",
        )
    except Exception as exc:  # noqa: BLE001
        raise WorkflowGenerationError(f"Schema validation failed: {exc}") from exc


def _build_trigger(raw: Any) -> WorkflowTrigger:
    """Build a WorkflowTrigger from raw dict."""
    if not isinstance(raw, dict):
        raise WorkflowGenerationError("'trigger' must be a JSON object.")
    if not raw.get("application") or not raw.get("event"):
        raise WorkflowGenerationError(
            "'trigger' must have non-empty 'application' and 'event' fields."
        )
    try:
        return WorkflowTrigger(
            application=str(raw.get("application", "")),
            event=str(raw.get("event", "")),
            description=str(raw.get("description", "")),
        )
    except Exception as exc:  # noqa: BLE001
        raise WorkflowGenerationError(f"Invalid trigger: {exc}") from exc


def _build_steps(raw_steps: Any) -> List[WorkflowStep]:
    """Build an ordered list of WorkflowStep objects."""
    if not isinstance(raw_steps, list) or len(raw_steps) == 0:
        raise WorkflowGenerationError("'steps' must be a non-empty list.")

    steps: List[WorkflowStep] = []
    for i, s in enumerate(raw_steps):
        if not isinstance(s, dict):
            raise WorkflowGenerationError(f"Step at index {i} is not a dict.")
        if not s.get("application"):
            raise WorkflowGenerationError(
                f"Step at index {i} is missing 'application'."
            )
        if not s.get("action"):
            raise WorkflowGenerationError(
                f"Step at index {i} is missing 'action'."
            )
        try:
            steps.append(
                WorkflowStep(
                    order=int(s.get("order", i + 1)),
                    application=str(s["application"]),
                    action=str(s["action"]),
                    description=str(s.get("description", "")),
                    inputs=[str(x) for x in s.get("inputs", []) if x],
                    outputs=[str(x) for x in s.get("outputs", []) if x],
                    on_failure=str(s.get("on_failure", "stop")),
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise WorkflowGenerationError(
                f"Invalid step at index {i}: {exc}"
            ) from exc
    return steps


def _build_conditions(raw_conditions: Any) -> List[WorkflowCondition]:
    """Build WorkflowCondition objects, skipping malformed entries."""
    conditions: List[WorkflowCondition] = []
    if not isinstance(raw_conditions, list):
        return conditions
    for i, c in enumerate(raw_conditions):
        if not isinstance(c, dict):
            logger.warning("Skipping non-dict condition at index %d.", i)
            continue
        try:
            conditions.append(
                WorkflowCondition(
                    description=str(c.get("description", "")),
                    expression=str(c.get("expression", "")),
                    on_true=str(c.get("on_true", "stop")),
                    on_false=str(c.get("on_false", "continue")),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed condition at index %d: %s", i, exc)
    return conditions


def _build_variables(raw_variables: Any) -> List[WorkflowVariable]:
    """Build WorkflowVariable objects, skipping malformed entries."""
    variables: List[WorkflowVariable] = []
    if not isinstance(raw_variables, list):
        return variables
    for i, v in enumerate(raw_variables):
        if not isinstance(v, dict):
            continue
        try:
            src = v.get("source_step_order")
            variables.append(
                WorkflowVariable(
                    name=str(v.get("name", "")),
                    description=str(v.get("description", "")),
                    source_step_order=int(src) if src is not None else None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed variable at index %d: %s", i, exc)
    return variables


def _build_integrations(
    raw_integrations: Any,
    allowed_applications: List[str],
) -> List[WorkflowIntegration]:
    """
    Build WorkflowIntegration objects.

    Applications not present in allowed_applications are silently skipped
    to prevent evidence invention.
    """
    integrations: List[WorkflowIntegration] = []
    if not isinstance(raw_integrations, list):
        return integrations

    # Normalise for case-insensitive comparison
    allowed_lower = {a.lower() for a in allowed_applications}

    for i, itg in enumerate(raw_integrations):
        if not isinstance(itg, dict):
            continue
        app_name = str(itg.get("application", ""))
        if app_name.lower() not in allowed_lower:
            logger.warning(
                "Skipping invented integration '%s' (not in understanding).", app_name
            )
            continue
        try:
            integrations.append(
                WorkflowIntegration(
                    application=app_name,
                    purpose=str(itg.get("purpose", "")),
                    required_capabilities=[
                        str(c) for c in itg.get("required_capabilities", []) if c
                    ],
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed integration at index %d: %s", i, exc)
    return integrations


def _build_error_handling(raw: Any) -> WorkflowErrorHandling:
    """Build WorkflowErrorHandling from raw dict, using defaults for missing fields."""
    if not isinstance(raw, dict):
        return WorkflowErrorHandling()
    try:
        return WorkflowErrorHandling(
            on_step_failure=str(raw.get("on_step_failure", "stop_and_report")),
            on_missing_input=str(raw.get("on_missing_input", "stop")),
            on_timeout=str(raw.get("on_timeout", "stop_and_report")),
            notes=str(raw.get("notes", "")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build error_handling, using defaults: %s", exc)
        return WorkflowErrorHandling()
