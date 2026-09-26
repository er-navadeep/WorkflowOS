"""
Activity Agent — Source Base Interface
=========================================
All activity sources (simulation, OS observer, browser observer, etc.)
implement this interface so the Runner can treat them identically.

To add a new source later:
    1. Create a new module under sources/<name>/
    2. Subclass BaseActivitySource
    3. Implement generate_events()
    4. Register it in runner.py

The Runner never knows which concrete source it is using.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, List

# We import the ActivityEvent schema from the backend package.
# The runner adds the backend/ directory to sys.path before importing
# this module, so this import resolves correctly.
import sys
import os

# Allow running the agent from any working directory by ensuring
# the backend package is always importable.
_backend_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from app.schemas.activity_event import ActivityEvent  # noqa: E402


class BaseActivitySource(ABC):
    """
    Abstract base for all activity event sources.

    A source is responsible for:
    - generating ActivityEvent objects for a given session
    - knowing nothing about HTTP, storage, or discovery

    It must NOT:
    - send events to the backend itself
    - access MongoDB
    - have side effects beyond yielding events
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this source (used in logs)."""
        ...

    @abstractmethod
    def generate_events(self, session_id: str) -> Iterator[ActivityEvent]:
        """
        Yield ActivityEvent objects for one complete workflow session.

        Args:
            session_id: The session identifier to embed in every event.

        Yields:
            ActivityEvent objects in the order they should be sent.

        The caller (Runner) is responsible for:
            - applying delays between events
            - sending events to the backend
            - handling send errors
        """
        ...

    def generate_events_list(self, session_id: str, **kwargs) -> List[ActivityEvent]:
        """
        Convenience method: collect all events into a list.

        Useful for tests and batch sending.
        Extra keyword arguments are forwarded to generate_events() so
        subclasses with additional parameters (e.g. repetition_index) work
        correctly without needing to override this method.
        """
        return list(self.generate_events(session_id, **kwargs))
