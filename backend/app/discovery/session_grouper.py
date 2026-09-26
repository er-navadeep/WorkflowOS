"""
Discovery — Session Grouper
=============================
Loads ActivityEvents from MongoDB and groups them into sessions.

Each session is a chronologically ordered list of events sharing
a common session_id.  Sessions with fewer than 2 events are discarded
(they cannot form a meaningful workflow pattern).

This module is READ-ONLY with respect to activity_events.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from app.database.mongodb import get_database

logger = logging.getLogger(__name__)

ACTIVITY_COLLECTION = "activity_events"
MIN_SESSION_EVENTS = 2  # sessions shorter than this are ignored


@dataclass
class SessionGroup:
    """One session's worth of events, sorted chronologically."""
    session_id: str
    events: List[Dict] = field(default_factory=list)

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def first_timestamp(self) -> Optional[datetime]:
        return self.events[0]["timestamp"] if self.events else None

    @property
    def last_timestamp(self) -> Optional[datetime]:
        return self.events[-1]["timestamp"] if self.events else None

    @property
    def duration_seconds(self) -> float:
        """Wall-clock seconds from first to last event in this session."""
        if not self.events or len(self.events) < 2:
            return 0.0
        t0 = self.first_timestamp
        t1 = self.last_timestamp
        if t0 is None or t1 is None:
            return 0.0
        # Both are tz-aware datetimes (stored as UTC by the schema)
        diff = (t1 - t0).total_seconds()
        return max(0.0, diff)


def load_and_group_sessions(
    session_id_filter: Optional[str] = None,
    min_events: int = MIN_SESSION_EVENTS,
) -> List[SessionGroup]:
    """
    Load activity events from MongoDB and group them by session_id.

    Args:
        session_id_filter: If provided, only load events for this session.
        min_events:        Discard sessions shorter than this.

    Returns:
        List of SessionGroup objects, each sorted by timestamp ascending.
        Sessions with fewer than `min_events` events are excluded.
    """
    db = get_database()
    col = db[ACTIVITY_COLLECTION]

    query: Dict = {}
    if session_id_filter:
        query["session_id"] = session_id_filter

    # Fetch all events sorted chronologically
    try:
        raw_events = list(col.find(query).sort("timestamp", 1))
    except Exception as exc:
        logger.error("Failed to load activity events: %s", exc)
        raise RuntimeError(f"Event load failed: {exc}") from exc

    # Group by session_id preserving MongoDB ObjectId-free dicts
    session_map: Dict[str, List[Dict]] = {}
    for doc in raw_events:
        doc.pop("_id", None)
        sid = doc.get("session_id")
        if not sid:
            continue
        session_map.setdefault(sid, []).append(doc)

    # Build SessionGroup list, filtering short sessions
    groups: List[SessionGroup] = []
    for sid, events in session_map.items():
        # Events from the DB are already sorted by timestamp (from the query),
        # but re-sort defensively by the timestamp field value.
        events_sorted = _sort_events(events)
        if len(events_sorted) < min_events:
            logger.debug("Skipping session %s — only %d events", sid, len(events_sorted))
            continue
        groups.append(SessionGroup(session_id=sid, events=events_sorted))

    logger.info("Loaded %d sessions from %d raw events.", len(groups), len(raw_events))
    return groups


def _sort_events(events: List[Dict]) -> List[Dict]:
    """Sort events by timestamp, handling both datetime objects and ISO strings."""
    def _ts_key(doc: Dict):
        ts = doc.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.min
    return sorted(events, key=_ts_key)
