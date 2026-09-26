"""
Discovery Engine
==================
Orchestrates the complete Workflow Discovery Pipeline:

    MongoDB ActivityEvents
            ↓
    Session Grouping        (session_grouper.py)
            ↓
    Sequence Building       (sequence_builder.py)
            ↓
    Normalisation           (normalizer.py)
            ↓
    Repetition Detection    (repetition_detector.py)
            ↓
    Scoring                 (scorer.py)
            ↓
    Candidate Building      (candidate_builder.py)
            ↓
    MongoDB Upsert          (models/workflow_candidate.py)
            ↓
    DiscoveryResult

The engine is stateless — each call to run() is independent.
It can be called:
    - on-demand via POST /api/v1/discovery/run
    - on a schedule (future)
    - from tests

It is READ-ONLY with respect to activity_events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.discovery.session_grouper import SessionGroup, load_and_group_sessions
from app.discovery.sequence_builder import build_sequences
from app.discovery.normalizer import normalise_all
from app.discovery.repetition_detector import detect_repeated_patterns
from app.discovery.scorer import score_pattern
from app.discovery.candidate_builder import build_candidate
from app.models.workflow_candidate import WorkflowCandidate, upsert_candidate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    """Summary of one discovery run."""
    sessions_analysed: int
    patterns_found: int
    candidates_created: int
    candidates_updated: int
    candidates: List[WorkflowCandidate] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DiscoveryEngine:
    """
    Runs the full workflow discovery pipeline against stored activity events.

    Args:
        min_occurrences: Minimum times a sequence must appear to become a candidate.
                         Defaults to 2.
    """

    def __init__(self, min_occurrences: int = 2) -> None:
        self._min_occurrences = min_occurrences

    def run(self) -> DiscoveryResult:
        """
        Execute the discovery pipeline end-to-end.

        Steps:
            1. Load and group sessions from MongoDB
            2. Build normalised sequences
            3. Detect repeated patterns
            4. Score each pattern
            5. Build WorkflowCandidate objects
            6. Upsert candidates to MongoDB

        Returns:
            DiscoveryResult with statistics and discovered candidates.
        """
        result = DiscoveryResult(
            sessions_analysed=0,
            patterns_found=0,
            candidates_created=0,
            candidates_updated=0,
        )

        # Step 1: Load sessions
        logger.info("Discovery run started.")
        try:
            sessions: List[SessionGroup] = load_and_group_sessions()
        except RuntimeError as exc:
            result.errors.append(f"Session load failed: {exc}")
            logger.error("Discovery aborted: %s", exc)
            return result

        result.sessions_analysed = len(sessions)

        if not sessions:
            logger.info("No sessions found. Discovery complete (nothing to discover).")
            return result

        # Build session lookup for timing extraction
        sessions_by_id = {s.session_id: s for s in sessions}

        # Step 2: Build normalised sequences
        sequences = build_sequences(sessions)
        normalised = normalise_all(sequences)

        logger.info(
            "Built %d sequences from %d sessions.",
            len(normalised),
            len(sessions),
        )

        # Step 3: Detect repeated patterns
        pattern_groups = detect_repeated_patterns(
            normalised,
            min_occurrences=self._min_occurrences,
        )
        result.patterns_found = len(pattern_groups)

        if not pattern_groups:
            logger.info(
                "No repeated patterns found (min_occurrences=%d).",
                self._min_occurrences,
            )
            return result

        # Steps 4-6: Score → Build → Upsert each pattern
        for group in pattern_groups:
            try:
                # Score
                scoring = score_pattern(group)

                # Build candidate
                candidate = build_candidate(
                    group=group,
                    scoring=scoring,
                    sessions_by_id=sessions_by_id,
                )

                # Upsert to MongoDB
                from app.models.workflow_candidate import get_candidate_by_fingerprint
                existing = get_candidate_by_fingerprint(group.fingerprint)

                upsert_candidate(candidate)

                if existing:
                    result.candidates_updated += 1
                else:
                    result.candidates_created += 1

                result.candidates.append(candidate)

                logger.info(
                    "Candidate '%s': score=%.3f, occurrences=%d, apps=%s",
                    candidate.name,
                    candidate.score,
                    candidate.occurrence_count,
                    candidate.applications,
                )

            except Exception as exc:  # noqa: BLE001
                msg = f"Failed to process pattern {group.fingerprint[:8]}: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        logger.info(
            "Discovery complete: %d sessions analysed, %d patterns, "
            "%d created, %d updated.",
            result.sessions_analysed,
            result.patterns_found,
            result.candidates_created,
            result.candidates_updated,
        )

        return result
