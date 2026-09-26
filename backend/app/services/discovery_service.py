"""
Discovery Service
==================
Business logic facade for the API layer.

The API router calls this service, never the engine directly.
This keeps the router thin and makes the service independently testable.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.discovery.engine import DiscoveryEngine, DiscoveryResult
from app.models.workflow_candidate import (
    WorkflowCandidate,
    get_all_candidates,
    get_candidate_by_id,
    count_candidates,
)

logger = logging.getLogger(__name__)


def run_discovery(min_occurrences: int = 2) -> DiscoveryResult:
    """
    Trigger the discovery pipeline against all stored activity events.

    Args:
        min_occurrences: Minimum occurrences for a pattern to qualify.

    Returns:
        DiscoveryResult with statistics and discovered candidates.
    """
    engine = DiscoveryEngine(min_occurrences=min_occurrences)
    result = engine.run()
    logger.info(
        "Discovery service: %d sessions, %d patterns, %d new, %d updated.",
        result.sessions_analysed,
        result.patterns_found,
        result.candidates_created,
        result.candidates_updated,
    )
    return result


def list_candidates(status: Optional[str] = None) -> List[WorkflowCandidate]:
    """Return all workflow candidates, optionally filtered by status."""
    return get_all_candidates(status=status)


def get_candidate(candidate_id: str) -> Optional[WorkflowCandidate]:
    """Return a single candidate by ID, or None if not found."""
    return get_candidate_by_id(candidate_id)


def get_candidate_count() -> int:
    """Return the total number of stored candidates."""
    return count_candidates()
