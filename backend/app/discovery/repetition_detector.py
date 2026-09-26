"""
Discovery — Repetition Detector
==================================
Groups normalised sequences by fingerprint to find repeated patterns.

Algorithm (deterministic):

    1. For each NormalisedSequence:
           key = sequence_fingerprint (SHA-256 of ordered step tuples)
    2. Group sequences sharing the same key into PatternGroups.
    3. Discard groups with fewer than MIN_OCCURRENCES sessions.
    4. Return surviving groups, sorted by occurrence count descending.

Why fingerprint grouping?
    - O(N) time: one pass through sequences, one dict lookup per sequence
    - Deterministic: same input always produces same groups
    - Exact: no false positives from approximate matching
    - Transparent: the fingerprint is inspectable in the API response

Fuzzy extension (future):
    The similarity module provides Jaccard-based grouping for partially
    matching sequences. Phase 5+ can use this to merge near-identical
    groups. For Phase 4, only exact-fingerprint grouping is used.

MIN_OCCURRENCES = 2 (a pattern must appear at least twice to be a candidate).
    This prevents one-off sessions from becoming workflow candidates.
    The MVP demo runs 3+ repetitions, so this threshold is always met.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from app.discovery.normalizer import NormalisedSequence
from app.discovery.similarity import average_pairwise_similarity

logger = logging.getLogger(__name__)

MIN_OCCURRENCES = 2  # Minimum sessions to consider a pattern "repeated"


@dataclass
class PatternGroup:
    """
    A group of sessions that share the exact same normalised sequence.

    Attributes:
        fingerprint:    SHA-256 hash identifying this pattern.
        sequences:      All NormalisedSequence objects with this fingerprint.
        occurrence_count: Number of matching sessions.
        similarity:     Mean pairwise Jaccard similarity of the group.
    """
    fingerprint: str
    sequences: List[NormalisedSequence] = field(default_factory=list)

    @property
    def occurrence_count(self) -> int:
        return len(self.sequences)

    @property
    def session_ids(self) -> List[str]:
        return [s.session_id for s in self.sequences]

    @property
    def similarity(self) -> float:
        """Average pairwise Jaccard similarity for all sessions in this group."""
        return average_pairwise_similarity(self.sequences)

    @property
    def representative_steps(self) -> List[dict]:
        """
        Return the normalised steps from the first sequence in the group.

        All sequences in the group have the same fingerprint, so any of
        them can serve as the canonical representation.
        """
        if not self.sequences:
            return []
        return self.sequences[0].steps

    @property
    def applications(self) -> List[str]:
        """Ordered unique applications from the representative sequence."""
        seen = set()
        result = []
        for step in self.representative_steps:
            app = step.get("application", "")
            if app and app not in seen:
                seen.add(app)
                result.append(app)
        return result


def detect_repeated_patterns(
    sequences: List[NormalisedSequence],
    min_occurrences: int = MIN_OCCURRENCES,
) -> List[PatternGroup]:
    """
    Detect sequences that appear across multiple sessions.

    Args:
        sequences:       All normalised sequences from the session grouper.
        min_occurrences: Minimum number of sessions for a pattern to qualify.

    Returns:
        List of PatternGroup objects, sorted by occurrence_count descending.
        Groups with fewer than min_occurrences sessions are excluded.

    Example:
        Given 3 sessions with identical sequences:
            → 1 PatternGroup with occurrence_count=3, similarity=1.0

        Given 3 identical sessions + 1 unrelated session:
            → 1 PatternGroup with occurrence_count=3
              (the unrelated session forms its own group of 1 — filtered out)
    """
    # Group sequences by fingerprint
    groups: Dict[str, PatternGroup] = {}
    for seq in sequences:
        fp = seq.fingerprint
        if fp not in groups:
            groups[fp] = PatternGroup(fingerprint=fp)
        groups[fp].sequences.append(seq)

    # Filter by minimum occurrence threshold
    repeated = [
        g for g in groups.values()
        if g.occurrence_count >= min_occurrences
    ]

    # Sort by occurrence count descending (most repeated first)
    repeated.sort(key=lambda g: g.occurrence_count, reverse=True)

    logger.info(
        "Detected %d repeated patterns from %d total fingerprints "
        "(min_occurrences=%d).",
        len(repeated),
        len(groups),
        min_occurrences,
    )

    for g in repeated:
        logger.debug(
            "Pattern %s...: %d occurrences, similarity=%.3f, apps=%s",
            g.fingerprint[:8],
            g.occurrence_count,
            g.similarity,
            g.applications,
        )

    return repeated
