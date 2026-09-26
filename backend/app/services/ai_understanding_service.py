"""
AI Understanding Service
=========================
Business logic facade for Phase 5.

Orchestrates:
  1. Retrieve WorkflowCandidate from MongoDB.
  2. Build the Gemini prompt.
  3. Call Gemini.
  4. Parse + validate the structured response.
  5. Persist the WorkflowUnderstanding.
  6. Return the result.

The API router calls this service; it never touches the Gemini client directly.
This keeps the router thin and the service independently testable.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.ai.gemini_client import GeminiClient, GeminiClientError
from app.ai.prompts import build_understanding_prompt
from app.ai.workflow_understanding import parse_understanding_response, ParseError
from app.models.workflow_candidate import get_candidate_by_id
from app.models.workflow_understanding import (
    upsert_understanding,
    get_understanding_by_candidate,
    list_understandings,
    count_understandings,
)
from app.schemas.workflow_understanding import WorkflowUnderstanding

logger = logging.getLogger(__name__)


class UnderstandingServiceError(Exception):
    """Raised when the service cannot produce an understanding."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


def generate_understanding(candidate_id: str) -> WorkflowUnderstanding:
    """
    Generate an AI understanding for the given WorkflowCandidate.

    Workflow:
        1. Fetch candidate (404 if not found).
        2. Build prompt.
        3. Call Gemini.
        4. Parse + validate response.
        5. Persist understanding.
        6. Return understanding.

    Args:
        candidate_id: ID of the WorkflowCandidate to understand.

    Returns:
        The newly generated WorkflowUnderstanding.

    Raises:
        UnderstandingServiceError: with an appropriate status_code.
    """
    # 1. Fetch candidate
    try:
        candidate = get_candidate_by_id(candidate_id)
    except RuntimeError as exc:
        logger.error("DB error fetching candidate %s: %s", candidate_id, exc)
        raise UnderstandingServiceError(
            "Database error while retrieving candidate.", status_code=503
        ) from exc

    if candidate is None:
        raise UnderstandingServiceError(
            f"Candidate '{candidate_id}' not found.", status_code=404
        )

    # 2. Build prompt
    prompt = build_understanding_prompt(candidate)

    # 3. Call Gemini
    try:
        client = GeminiClient()
        raw_response = client.generate(prompt)
    except GeminiClientError as exc:
        logger.error("Gemini call failed for candidate %s: %s", candidate_id, exc)
        raise UnderstandingServiceError(
            f"AI service error: {exc}", status_code=503
        ) from exc

    # 4. Parse and validate
    try:
        understanding = parse_understanding_response(
            raw_text=raw_response,
            candidate_id=candidate_id,
            model_used=client.model,
        )
    except ParseError as exc:
        logger.error("Failed to parse Gemini response for candidate %s: %s", candidate_id, exc)
        raise UnderstandingServiceError(
            f"AI response parsing failed: {exc}", status_code=502
        ) from exc

    # 5. Persist
    try:
        upsert_understanding(understanding)
    except RuntimeError as exc:
        logger.error("DB error persisting understanding for %s: %s", candidate_id, exc)
        raise UnderstandingServiceError(
            "Database error while saving understanding.", status_code=503
        ) from exc

    logger.info(
        "Understanding generated for candidate %s (confidence=%.2f).",
        candidate_id,
        understanding.confidence,
    )
    return understanding


def get_understanding(candidate_id: str) -> Optional[WorkflowUnderstanding]:
    """
    Return the stored understanding for candidate_id, or None.

    Raises:
        UnderstandingServiceError: on database failure.
    """
    try:
        return get_understanding_by_candidate(candidate_id)
    except RuntimeError as exc:
        logger.error("DB error fetching understanding for %s: %s", candidate_id, exc)
        raise UnderstandingServiceError(
            "Database error while retrieving understanding.", status_code=503
        ) from exc


def list_all_understandings() -> List[WorkflowUnderstanding]:
    """Return all stored understandings, newest first."""
    try:
        return list_understandings()
    except RuntimeError as exc:
        logger.error("DB error listing understandings: %s", exc)
        raise UnderstandingServiceError(
            "Database error while listing understandings.", status_code=503
        ) from exc
