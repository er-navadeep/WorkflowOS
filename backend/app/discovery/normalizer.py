"""
Discovery — Sequence Normalizer
=================================
Maps EventSequence objects to canonical forms for comparison.

Normalisation goals:
    1. Make the same workflow pattern produce the same fingerprint,
       even when run by different users or with different data.
    2. Support future fuzzy matching by exposing a token set per sequence.

What is normalised:
    - event_type: lowercased
    - application: whitespace-stripped (case-preserved for readability)
    - action: lowercased, whitespace-stripped

What is NOT normalised (intentionally excluded):
    - target (different customer per run)
    - metadata (runtime-specific values)
    - timestamps
    - event_id

The fingerprint is a deterministic SHA-256 hash of the canonical form.
See workflow_candidate.build_fingerprint() for the hashing logic.

Normalised form:
    A list of dicts, each with keys: event_type, application, action.
    Order is preserved.
"""

from __future__ import annotations

from typing import List, Tuple

from app.discovery.sequence_builder import EventSequence, SequenceStep
from app.models.workflow_candidate import build_fingerprint


class NormalisedSequence:
    """
    The canonical, fingerprinted form of an EventSequence.

    Attributes:
        session_id:    Source session.
        steps:         Normalised step dicts.
        fingerprint:   SHA-256 hash (first 32 chars) — used for grouping.
        token_set:     Flat set of "app/action" strings for Jaccard similarity.
    """

    __slots__ = ("session_id", "steps", "fingerprint", "token_set")

    def __init__(self, session_id: str, steps: List[dict]) -> None:
        self.session_id: str = session_id
        self.steps: List[dict] = steps
        self.fingerprint: str = build_fingerprint(steps)
        self.token_set: frozenset = frozenset(
            f"{s['application']}/{s['action']}" for s in steps
        )

    @property
    def length(self) -> int:
        return len(self.steps)

    def __repr__(self) -> str:
        return f"NormalisedSequence(session={self.session_id}, fp={self.fingerprint[:8]}...)"


def normalise(sequence: EventSequence) -> NormalisedSequence:
    """
    Convert an EventSequence into a NormalisedSequence.

    Normalisation rules applied here:
        - event_type: already lowercased by sequence_builder
        - application: strip whitespace
        - action: already lowercased by sequence_builder
    """
    normalised_steps = [
        {
            "event_type": step.event_type,
            "application": step.application.strip(),
            "action": step.action,
        }
        for step in sequence.steps
    ]
    return NormalisedSequence(
        session_id=sequence.session_id,
        steps=normalised_steps,
    )


def normalise_all(sequences: List[EventSequence]) -> List[NormalisedSequence]:
    """Normalise a list of EventSequences."""
    return [normalise(seq) for seq in sequences]
