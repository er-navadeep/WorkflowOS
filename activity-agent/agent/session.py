"""
Activity Agent — Session Manager
===================================
Each complete execution of a workflow pattern is a "session".

A session_id groups all events from one run together so the
Workflow Discovery Engine can recognise them as a unit.

Format:
    session-<8-char-hex>-<iso-date>
    e.g.  session-a3f2c1b0-2026-09-26

This is stable enough for the discovery engine to group by prefix date
while still being unique per run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def new_session_id() -> str:
    """
    Generate a fresh, unique session identifier.

    Each call returns a different ID so every workflow repetition
    is stored under its own session in MongoDB.

    Format:
        session-<8-hex>-<YYYY-MM-DD>

    Example:
        session-a3f2c1b0-2026-09-26
    """
    hex_part = uuid.uuid4().hex[:8]
    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"session-{hex_part}-{date_part}"


def demo_session_id(index: int) -> str:
    """
    Generate a deterministic demo session ID for testing / seeding.

    Args:
        index: Zero-based repetition index.

    Example:
        demo_session_id(0)  ->  "session-demo-run-001"
        demo_session_id(2)  ->  "session-demo-run-003"
    """
    return f"session-demo-run-{index + 1:03d}"
