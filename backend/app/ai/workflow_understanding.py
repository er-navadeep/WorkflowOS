"""
AI Workflow Understanding — Parsing & Validation
=================================================
Converts a raw Gemini text response into a validated WorkflowUnderstanding.

Responsibilities:
- Strip markdown fences that the model may accidentally include.
- Parse JSON.
- Validate the parsed dict against the WorkflowUnderstanding schema.
- Return structured errors, never raw exceptions.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Tuple

from app.schemas.workflow_understanding import (
    WorkflowUnderstanding,
    UnderstandingAction,
    UnderstandingCondition,
    UnderstandingVariable,
)

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when the Gemini response cannot be converted to a valid understanding."""


def parse_understanding_response(
    raw_text: str,
    candidate_id: str,
    model_used: str,
) -> WorkflowUnderstanding:
    """
    Parse the raw Gemini text into a WorkflowUnderstanding model.

    Args:
        raw_text:     Text returned by Gemini.
        candidate_id: ID of the source WorkflowCandidate.
        model_used:   Gemini model identifier (for provenance).

    Returns:
        A validated WorkflowUnderstanding.

    Raises:
        ParseError: when the text cannot be parsed or validated.
    """
    # 1. Strip accidental markdown code fences
    cleaned = _strip_markdown_fences(raw_text)

    # 2. Parse JSON
    data = _parse_json(cleaned)

    # 3. Validate and build the model
    return _build_model(data, candidate_id=candidate_id, model_used=model_used)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers the model may add."""
    # Match optional language tag after opening fence
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```\s*$"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_json(text: str) -> Dict[str, Any]:
    """Parse JSON text, raising ParseError on failure."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini response is not valid JSON: %s", exc)
        raise ParseError(f"Response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ParseError(
            f"Expected a JSON object, got {type(data).__name__}."
        )
    return data


def _build_model(
    data: Dict[str, Any],
    candidate_id: str,
    model_used: str,
) -> WorkflowUnderstanding:
    """
    Build and validate a WorkflowUnderstanding from a parsed dict.

    Performs field-level validation and raises ParseError on any problem.
    """
    required = ("intent", "name", "description", "trigger", "applications", "actions", "confidence")
    missing = [k for k in required if k not in data]
    if missing:
        raise ParseError(f"Missing required fields in Gemini response: {missing}")

    # --- Validate and build actions ---
    raw_actions = data.get("actions", [])
    if not isinstance(raw_actions, list) or len(raw_actions) == 0:
        raise ParseError("'actions' must be a non-empty list.")

    actions = []
    for i, a in enumerate(raw_actions):
        if not isinstance(a, dict):
            raise ParseError(f"Action at index {i} is not a dict.")
        try:
            actions.append(UnderstandingAction(
                order=int(a.get("order", i + 1)),
                application=str(a.get("application", "")),
                operation=str(a.get("operation", "")),
                description=str(a.get("description", "")),
            ))
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"Invalid action at index {i}: {exc}") from exc

    # --- Validate and build conditions ---
    raw_conditions = data.get("conditions", [])
    conditions = []
    if isinstance(raw_conditions, list):
        for i, c in enumerate(raw_conditions):
            if not isinstance(c, dict):
                continue
            try:
                conditions.append(UnderstandingCondition(
                    description=str(c.get("description", "")),
                    consequence=str(c.get("consequence", "")),
                    inferred=bool(c.get("inferred", True)),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed condition at index %d: %s", i, exc)

    # --- Validate and build variables ---
    raw_variables = data.get("variables", [])
    variables = []
    if isinstance(raw_variables, list):
        for i, v in enumerate(raw_variables):
            if not isinstance(v, dict):
                continue
            try:
                variables.append(UnderstandingVariable(
                    name=str(v.get("name", "")),
                    description=str(v.get("description", "")),
                    observed_in=str(v.get("observed_in", "")),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping malformed variable at index %d: %s", i, exc)

    # --- Confidence ---
    try:
        confidence = float(data["confidence"])
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError) as exc:
        raise ParseError(f"'confidence' must be a float: {exc}") from exc

    # --- Applications ---
    raw_apps = data.get("applications", [])
    applications = [str(a) for a in raw_apps] if isinstance(raw_apps, list) else []

    try:
        return WorkflowUnderstanding(
            candidate_id=candidate_id,
            intent=str(data["intent"]),
            name=str(data["name"]),
            description=str(data["description"]),
            trigger=str(data["trigger"]),
            applications=applications,
            actions=actions,
            conditions=conditions,
            variables=variables,
            confidence=confidence,
            model_used=model_used,
            status="generated",
        )
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"Schema validation failed: {exc}") from exc
