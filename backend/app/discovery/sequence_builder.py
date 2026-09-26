"""
Discovery — Sequence Builder
==============================
Converts a SessionGroup (raw event dicts) into a typed sequence of steps.

A "step" is the smallest meaningful unit of comparison:
    (event_type, application, action)

Volatile fields (event_id, timestamp, target, metadata) are intentionally
excluded from the sequence because:
    - timestamps differ between runs
    - targets may differ (different customer emails per run)
    - we want to detect the *workflow pattern*, not identical data

Application transitions are derived from the step sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from app.discovery.session_grouper import SessionGroup


@dataclass(frozen=True)
class SequenceStep:
    """
    One normalised step extracted from an activity event.

    Fields used for pattern comparison:
        event_type   - the category of action (email, crm, slack …)
        application  - the software used (Gmail, CRM, Slack …)
        action       - the verb (open_email, find_customer …)
    """
    event_type: str
    application: str
    action: str

    def as_tuple(self) -> Tuple[str, str, str]:
        return (self.event_type, self.application, self.action)

    def as_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "application": self.application,
            "action": self.action,
        }

    def __str__(self) -> str:
        return f"{self.application}/{self.action}"


@dataclass
class EventSequence:
    """
    The normalised sequence of steps for a single session.

    Also carries derived cross-application analysis.
    """
    session_id: str
    steps: List[SequenceStep]

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def applications(self) -> List[str]:
        """Ordered list of applications, deduplicated while preserving first-seen order."""
        seen = set()
        result = []
        for step in self.steps:
            if step.application not in seen:
                seen.add(step.application)
                result.append(step.application)
        return result

    @property
    def transitions(self) -> List[Tuple[str, str]]:
        """
        List of (from_app, to_app) application-level transitions.

        Only records transitions where the application actually changes.
        """
        result = []
        for i in range(1, len(self.steps)):
            prev_app = self.steps[i - 1].application
            curr_app = self.steps[i].application
            if prev_app != curr_app:
                result.append((prev_app, curr_app))
        return result

    @property
    def transition_count(self) -> int:
        return len(self.transitions)

    def as_key(self) -> Tuple[Tuple[str, str, str], ...]:
        """
        Hashable tuple representation — used as a dict key for grouping.
        """
        return tuple(s.as_tuple() for s in self.steps)

    def as_dict_list(self) -> List[dict]:
        return [s.as_dict() for s in self.steps]


def build_sequence(session: SessionGroup) -> EventSequence:
    """
    Build an EventSequence from a SessionGroup.

    Extracts (event_type, application, action) from each event dict,
    ignoring events that are missing any of those three fields.

    Args:
        session: A SessionGroup with sorted event dicts.

    Returns:
        An EventSequence for that session.
    """
    steps: List[SequenceStep] = []

    for event in session.events:
        et = event.get("event_type")
        app = event.get("application")
        action = event.get("action")

        # Skip any event missing the three core fields
        if not et or not app or not action:
            continue

        # Normalise: strip whitespace, lowercase event_type for consistency
        steps.append(SequenceStep(
            event_type=str(et).strip().lower(),
            application=str(app).strip(),
            action=str(action).strip().lower(),
        ))

    return EventSequence(session_id=session.session_id, steps=steps)


def build_sequences(sessions: List[SessionGroup]) -> List[EventSequence]:
    """Build EventSequence objects for a list of sessions."""
    return [build_sequence(s) for s in sessions if s.events]
