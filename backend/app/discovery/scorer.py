"""
Discovery — Candidate Scorer
==============================
Computes a deterministic composite confidence score for a PatternGroup.

SCORING FORMULA
===============

score = (
    w_occurrence  * occurrence_factor  +
    w_similarity  * similarity         +
    w_coverage    * coverage_factor    +
    w_length      * length_factor
)

Where:

    w_occurrence = 0.40   (frequency is the strongest signal)
    w_similarity = 0.30   (how consistent the pattern is)
    w_coverage   = 0.20   (cross-application workflows are more automatable)
    w_length     = 0.10   (longer sequences have more automation value)

FACTOR CALCULATIONS
===================

occurrence_factor = min(occurrence_count / OCCURRENCE_CAP, 1.0)
    OCCURRENCE_CAP = 5
    Rationale: 5+ occurrences provides high confidence. Above 5 is capped
    at 1.0. This prevents one extremely frequent pattern from dominating
    while still rewarding frequency.

    Examples:
        1 occurrence  → 0.20
        2 occurrences → 0.40
        3 occurrences → 0.60
        5 occurrences → 1.00

similarity = average_pairwise_jaccard(sessions)
    Range: [0.0, 1.0]
    For identical sequences: 1.0

coverage_factor = min((application_count - 1) / (MAX_APPS - 1), 1.0)
    MAX_APPS = 4
    Rationale: A single-app workflow (app_count=1) → 0.0 coverage.
    A workflow spanning 4+ apps → 1.0.

    Examples:
        1 app  → 0.00
        2 apps → 0.33
        3 apps → 0.67
        4 apps → 1.00

length_factor = min(sequence_length / LENGTH_CAP, 1.0)
    LENGTH_CAP = 10
    Rationale: A 10-step workflow is fully automated value. Shorter
    sequences score proportionally lower but are still valuable.

    Examples:
        3 steps  → 0.30
        5 steps  → 0.50
        7 steps  → 0.70
        10 steps → 1.00

TOTAL WEIGHTS
=============
w_occurrence + w_similarity + w_coverage + w_length = 1.00

All factors and the final score are in [0.0, 1.0].

EXAMPLE (3 sessions, 7 steps, 3 apps, similarity=1.0):
    occurrence_factor = min(3/5, 1.0)    = 0.60
    similarity        = 1.0              = 1.00
    coverage_factor   = min(2/3, 1.0)   ≈ 0.67
    length_factor     = min(7/10, 1.0)  = 0.70

    score = 0.40*0.60 + 0.30*1.00 + 0.20*0.67 + 0.10*0.70
          = 0.24      + 0.30      + 0.134      + 0.07
          = 0.744  ≈ 0.74
"""

from __future__ import annotations

from dataclasses import dataclass

from app.discovery.repetition_detector import PatternGroup

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

W_OCCURRENCE: float = 0.40
W_SIMILARITY: float = 0.30
W_COVERAGE: float = 0.20
W_LENGTH: float = 0.10

OCCURRENCE_CAP: int = 5   # occurrences beyond this are treated as 1.0
MAX_APPS: int = 4         # applications beyond this are treated as 1.0
LENGTH_CAP: int = 10      # steps beyond this are treated as 1.0

# Sanity check — weights must sum to 1.0
assert abs(W_OCCURRENCE + W_SIMILARITY + W_COVERAGE + W_LENGTH - 1.0) < 1e-9


@dataclass
class ScoringResult:
    """All scoring factors and the final composite score."""
    score: float
    occurrence_factor: float
    similarity: float
    coverage_factor: float
    length_factor: float
    occurrence_count: int
    application_count: int
    sequence_length: int


def score_pattern(group: PatternGroup) -> ScoringResult:
    """
    Calculate the composite discovery score for a PatternGroup.

    Args:
        group: A PatternGroup produced by the repetition detector.

    Returns:
        ScoringResult with all factors and the final score.
    """
    occurrence_count = group.occurrence_count
    application_count = len(group.applications)
    sequence_length = len(group.representative_steps)
    similarity = group.similarity

    # Factor calculations
    occurrence_factor = min(occurrence_count / OCCURRENCE_CAP, 1.0)
    coverage_factor = (
        min((application_count - 1) / (MAX_APPS - 1), 1.0)
        if application_count > 1
        else 0.0
    )
    length_factor = min(sequence_length / LENGTH_CAP, 1.0)

    # Weighted composite
    score = (
        W_OCCURRENCE * occurrence_factor
        + W_SIMILARITY * similarity
        + W_COVERAGE * coverage_factor
        + W_LENGTH * length_factor
    )
    score = round(min(max(score, 0.0), 1.0), 4)

    return ScoringResult(
        score=score,
        occurrence_factor=round(occurrence_factor, 4),
        similarity=round(similarity, 4),
        coverage_factor=round(coverage_factor, 4),
        length_factor=round(length_factor, 4),
        occurrence_count=occurrence_count,
        application_count=application_count,
        sequence_length=sequence_length,
    )
