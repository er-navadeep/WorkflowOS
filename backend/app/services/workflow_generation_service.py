"""
Workflow Generation Service — Phase 6
=======================================
Business logic facade for Phase 6.

Pipeline:
    1. Retrieve WorkflowUnderstanding from MongoDB.
    2. Build the Gemini workflow-generation prompt.
    3. Call Gemini via the existing Phase 5 GeminiClient.
    4. Parse + validate the structured response.
    5. Run deterministic validator.
    6. Persist the WorkflowDefinition.
    7. Return the result.

The API router calls this service; it never touches the Gemini client directly.
This keeps the router thin and the service independently testable.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.ai.gemini_client import GeminiClient, GeminiClientError
from app.models.workflow import (
    count_workflows,
    get_workflow_by_id,
    get_workflow_by_understanding,
    list_workflows,
    upsert_workflow,
)
from app.models.workflow_understanding import get_understanding_by_id
from app.schemas.workflow import WorkflowDefinition
from app.workflow_engine.generator import (
    WorkflowGenerationError,
    parse_workflow_response,
)
from app.workflow_engine.prompts import build_generation_prompt
from app.workflow_engine.validator import validate_workflow

logger = logging.getLogger(__name__)


class WorkflowServiceError(Exception):
    """Raised when the service cannot produce a workflow definition."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def generate_workflow(understanding_id: str) -> WorkflowDefinition:
    """
    Generate a WorkflowDefinition from an existing WorkflowUnderstanding.

    Pipeline:
        1. Fetch understanding (404 if not found).
        2. Build prompt.
        3. Call Gemini.
        4. Parse + validate response.
        5. Run deterministic validator.
        6. Persist workflow.
        7. Return workflow.

    Args:
        understanding_id: ID of the source WorkflowUnderstanding.

    Returns:
        The generated WorkflowDefinition.

    Raises:
        WorkflowServiceError with an appropriate status_code.
    """
    # 1. Fetch understanding
    try:
        understanding = get_understanding_by_id(understanding_id)
    except RuntimeError as exc:
        logger.error("DB error fetching understanding %s: %s", understanding_id, exc)
        raise WorkflowServiceError(
            "Database error while retrieving understanding.", status_code=503
        ) from exc

    if understanding is None:
        raise WorkflowServiceError(
            f"Understanding '{understanding_id}' not found.", status_code=404
        )

    # 2. Build prompt
    prompt = build_generation_prompt(understanding)

    # 3. Call Gemini
    try:
        client = GeminiClient()
        raw_response = client.generate(prompt)
    except GeminiClientError as exc:
        logger.error(
            "Gemini call failed for understanding %s: %s", understanding_id, exc
        )
        raise WorkflowServiceError(
            f"AI service error: {exc}", status_code=503
        ) from exc

    # 4. Parse and build WorkflowDefinition
    try:
        workflow = parse_workflow_response(
            raw_text=raw_response,
            understanding=understanding,
            model_used=client.model,
        )
    except WorkflowGenerationError as exc:
        logger.error(
            "Failed to parse Gemini workflow response for %s: %s",
            understanding_id,
            exc,
        )
        raise WorkflowServiceError(
            f"AI response parsing failed: {exc}", status_code=502
        ) from exc

    # 5. Deterministic validation
    validation = validate_workflow(workflow, understanding=understanding)
    if not validation.valid:
        logger.error(
            "Workflow validation failed for %s: %s",
            understanding_id,
            validation.errors,
        )
        raise WorkflowServiceError(
            f"Workflow validation failed: {'; '.join(validation.errors)}",
            status_code=422,
        )
    if validation.warnings:
        logger.warning(
            "Workflow validation warnings for %s: %s",
            understanding_id,
            validation.warnings,
        )

    # 6. Persist
    try:
        upsert_workflow(workflow)
    except RuntimeError as exc:
        logger.error(
            "DB error persisting workflow for %s: %s", understanding_id, exc
        )
        raise WorkflowServiceError(
            "Database error while saving workflow.", status_code=503
        ) from exc

    logger.info(
        "Workflow generated for understanding %s (steps=%d, confidence=%.2f).",
        understanding_id,
        len(workflow.steps),
        workflow.generation_confidence,
    )
    return workflow


def get_workflow(workflow_id: str) -> Optional[WorkflowDefinition]:
    """
    Return the stored workflow for workflow_id, or None.

    Raises:
        WorkflowServiceError: on database failure.
    """
    try:
        return get_workflow_by_id(workflow_id)
    except RuntimeError as exc:
        logger.error("DB error fetching workflow %s: %s", workflow_id, exc)
        raise WorkflowServiceError(
            "Database error while retrieving workflow.", status_code=503
        ) from exc


def list_all_workflows() -> List[WorkflowDefinition]:
    """Return all stored workflows, newest first."""
    try:
        return list_workflows()
    except RuntimeError as exc:
        logger.error("DB error listing workflows: %s", exc)
        raise WorkflowServiceError(
            "Database error while listing workflows.", status_code=503
        ) from exc
