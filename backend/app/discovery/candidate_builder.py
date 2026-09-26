"""
Discovery — Candidate Builder
================================
Converts a PatternGroup + timing data into a WorkflowCandidate model.

Responsibilities:
    - Determine a human-readable name (deterministic for Phase 4)
    - Extract timing data from the original session events
    - Build the SequenceStep list for the candidate
    - Assemble CandidateEvidence from the ScoringResult
    - Construct the final WorkflowCandidate Pydantic object

NAME GENERATION (Phase 4 — deterministic):
    The name is derived from the application transitions in the sequence.
    A lookup table maps known patterns to readable names.
    Phase 5 AI Understanding will replace this with LLM-generated names.

    Known patterns → names:
        Gmail + CRM + Slack  → "Process Customer Request"
        Gmail + CRM          → "Update CRM from Email"
        CRM + Slack          → "Notify Team After CRM Update"
        Gmail + Slack        → "Forward Email to Slack"
        default              → "Automated Workflow: <apps>"

The architecture is designed so that name generation can be replaced
by injecting a different naming function without changing this module.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from app.discovery.repetition_detector import PatternGroup
from app.discovery.scorer import ScoringResult
from app.discovery.session_grouper import SessionGroup
from app.models.workflow_candidate import (
    CandidateEvidence,
    SequenceStep,
    WorkflowCandidate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic name generation (to be replaced by AI in Phase 5)
# ---------------------------------------------------------------------------

# Map frozensets of application names to workflow names
_APP_NAME_MAP: List[Tuple[frozenset, str]] = [
    (frozenset({"Gmail", "CRM", "Slack"}), "Process Customer Request"),
    (frozenset({"Gmail", "CRM"}),          "Update CRM from Email"),
    (frozenset({"CRM", "Slack"}),          "Notify Team After CRM Update"),
    (frozenset({"Gmail", "Slack"}),        "Forward Email to Slack"),
]


def generate_name_deterministic(applications: List[str]) -> str:
    """
    Produce a human-readable workflow name from the applications list.

    Args:
        applications: Ordered unique list of applications in the sequence.

    Returns:
        A meaningful name string.
    """
    app_set = frozenset(applications)
    for known_apps, name in _APP_NAME_MAP:
        if known_apps.issubset(app_set):
            return name
    # Fallback: "Automated Workflow: App1 → App2 → ..."
    return "Automated Workflow: " + " > ".join(applications)


# Default naming function — can be replaced in tests or Phase 5
NamingFunction = Callable[[List[str]], str]
_default_namer: NamingFunction = generate_name_deterministic


# ---------------------------------------------------------------------------
# Timing extraction
# ---------------------------------------------------------------------------

def _extract_timing(
    group: PatternGroup,
    sessions_by_id: Dict[str, SessionGroup],
) -> Tuple[datetime, datetime, float]:
    """
    Extract first_seen, last_seen, and average_duration_seconds
    from the original session events.

    Args:
        group:          The pattern group containing session IDs.
        sessions_by_id: Map from session_id → SessionGroup.

    Returns:
        (first_seen, last_seen, avg_duration_seconds)
    """
    all_first: List[datetime] = []
    all_last: List[datetime] = []
    durations: List[float] = []

    for sid in group.session_ids:
        sg = sessions_by_id.get(sid)
        if not sg or not sg.events:
            continue

        first_ts = sg.first_timestamp
        last_ts = sg.last_timestamp

        if first_ts:
            all_first.append(first_ts)
        if last_ts:
            all_last.append(last_ts)

        dur = sg.duration_seconds
        if dur >= 0:
            durations.append(dur)

    now = datetime.now(timezone.utc)

    first_seen = min(all_first) if all_first else now
    last_seen = max(all_last) if all_last else now
    avg_dur = sum(durations) / len(durations) if durations else 0.0

    return first_seen, last_seen, round(avg_dur, 2)


# ---------------------------------------------------------------------------
# Main builder function
# ---------------------------------------------------------------------------

def build_candidate(
    group: PatternGroup,
    scoring: ScoringResult,
    sessions_by_id: Dict[str, SessionGroup],
    namer: Optional[NamingFunction] = None,
) -> WorkflowCandidate:
    """
    Build a WorkflowCandidate from a PatternGroup + scoring result.

    Args:
        group:          The detected pattern group.
        scoring:        The ScoringResult from scorer.score_pattern().
        sessions_by_id: Map from session_id → SessionGroup for timing data.
        namer:          Optional naming function override (for testing / AI).

    Returns:
        A fully populated WorkflowCandidate ready for upsert.
    """
    if namer is None:
        namer = _default_namer

    applications = group.applications
    name = namer(applications)

    # Build typed SequenceStep list
    sequence_steps = [
        SequenceStep(
            order=i + 1,
            event_type=step.get("event_type", ""),
            application=step.get("application", ""),
            action=step.get("action", ""),
        )
        for i, step in enumerate(group.representative_steps)
    ]

    # Timing
    first_seen, last_seen, avg_duration = _extract_timing(group, sessions_by_id)

    # Evidence
    evidence = CandidateEvidence(
        occurrence_count=scoring.occurrence_count,
        sequence_similarity=scoring.similarity,
        application_count=scoring.application_count,
        sequence_length=scoring.sequence_length,
        occurrence_factor=scoring.occurrence_factor,
        coverage_factor=scoring.coverage_factor,
        length_factor=scoring.length_factor,
    )

    candidate = WorkflowCandidate(
        sequence_fingerprint=group.fingerprint,
        name=name,
        description=(
            f"Detected workflow spanning {', '.join(applications)}. "
            f"Observed {scoring.occurrence_count} times with "
            f"{scoring.similarity:.0%} sequence consistency."
        ),
        occurrence_count=scoring.occurrence_count,
        session_ids=group.session_ids,
        applications=applications,
        sequence=[s for s in sequence_steps],
        first_seen=first_seen,
        last_seen=last_seen,
        average_duration_seconds=avg_duration,
        similarity=scoring.similarity,
        score=scoring.score,
        evidence=evidence,
        status="discovered",
    )

    logger.info(
        "Built candidate '%s' | score=%.3f | occurrences=%d | apps=%s",
        name,
        scoring.score,
        scoring.occurrence_count,
        applications,
    )

    return candidate
