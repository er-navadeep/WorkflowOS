"""
Phase 2 Tests: Activity Event Schema, Storage, and API
=======================================================
Run from project root:

    .venv\\Scripts\\python -m pytest tests/test_phase2_activity.py -v

Or run directly:

    .venv\\Scripts\\python tests/test_phase2_activity.py

Tests:
    1.  Valid ActivityEvent model
    2.  Auto-generated event_id
    3.  All event types validate
    4.  Batch schema
    5.  Filter schema
    6.  Invalid event type rejected (ValidationError)
    7.  Missing required field rejected (ValidationError)
    8.  MongoDB insert single event
    9.  MongoDB bulk insert
    10. Retrieve by session (chronological)
    11. Filtered retrieval (CRM only)
    12. Count events
"""

from __future__ import annotations

import sys
import os

# Ensure 'app' package resolves from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from pydantic import ValidationError

from app.schemas.activity_event import (
    ActivityEvent,
    ActivityEventBatch,
    ActivityEventFilter,
    EventType,
)
from app.activity.storage import (
    count_events,
    get_events,
    get_events_by_session,
    insert_event,
    insert_events,
)


# ---------------------------------------------------------------------------
# Unique test session to avoid cross-test interference
# ---------------------------------------------------------------------------

import uuid
TEST_SESSION = f"test-phase2-{uuid.uuid4().hex[:8]}"


# ===========================================================================
# Schema tests (no DB required)
# ===========================================================================

class TestActivityEventSchema:

    def test_valid_full_event(self):
        """A fully-specified event should parse without error."""
        e = ActivityEvent(
            event_type="email",
            application="Gmail",
            action="open_email",
            target="customer@example.com",
            session_id="s1",
            metadata={"subject": "Customer Request"},
        )
        assert e.event_type == EventType.email
        assert e.application == "Gmail"
        assert e.action == "open_email"
        assert e.target == "customer@example.com"
        assert e.session_id == "s1"
        assert e.metadata == {"subject": "Customer Request"}
        assert e.event_id  # non-empty auto-generated UUID

    def test_auto_generated_event_id_is_unique(self):
        """Two events without explicit event_id should get different IDs."""
        e1 = ActivityEvent(event_type="crm", application="CRM", action="find_customer", target="x@y.com", session_id="s")
        e2 = ActivityEvent(event_type="crm", application="CRM", action="find_customer", target="x@y.com", session_id="s")
        assert e1.event_id != e2.event_id

    def test_explicit_event_id_preserved(self):
        e = ActivityEvent(
            event_id="my-custom-id",
            event_type="slack",
            application="Slack",
            action="send_message",
            target="#support",
            session_id="s",
        )
        assert e.event_id == "my-custom-id"

    @pytest.mark.parametrize("et", [
        "application", "browser", "file", "ui",
        "email", "crm", "slack", "form", "system",
    ])
    def test_all_event_types_valid(self, et: str):
        e = ActivityEvent(
            event_type=et,
            application="App",
            action="act",
            target="tgt",
            session_id="s",
        )
        assert e.event_type.value == et

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValidationError):
            ActivityEvent(
                event_type="INVALID_TYPE",
                application="X",
                action="y",
                target="z",
                session_id="s",
            )

    def test_missing_required_target_rejected(self):
        with pytest.raises(ValidationError):
            ActivityEvent(
                event_type="email",
                application="Gmail",
                action="open_email",
                session_id="s",
                # target is missing
            )

    def test_whitespace_stripped_from_string_fields(self):
        e = ActivityEvent(
            event_type="crm",
            application="  CRM  ",
            action="  find_customer  ",
            target="  customer@example.com  ",
            session_id="s",
        )
        assert e.application == "CRM"
        assert e.action == "find_customer"
        assert e.target == "customer@example.com"

    def test_batch_schema_valid(self):
        events = [
            ActivityEvent(event_type="email", application="Gmail", action="open_email", target="x", session_id="s"),
            ActivityEvent(event_type="file",  application="Gmail", action="download",   target="f.pdf", session_id="s"),
        ]
        batch = ActivityEventBatch(events=events)
        assert len(batch.events) == 2

    def test_batch_schema_empty_rejected(self):
        with pytest.raises(ValidationError):
            ActivityEventBatch(events=[])

    def test_filter_defaults(self):
        f = ActivityEventFilter()
        assert f.limit == 100
        assert f.skip == 0
        assert f.session_id is None

    def test_filter_limit_range_enforced(self):
        with pytest.raises(ValidationError):
            ActivityEventFilter(limit=0)
        with pytest.raises(ValidationError):
            ActivityEventFilter(limit=1001)


# ===========================================================================
# Storage + MongoDB integration tests
# ===========================================================================

class TestActivityEventStorage:
    """
    These tests write to and read from the real 'workflowos' MongoDB instance.
    They use a unique session_id per test run so they are idempotent.
    """

    def _make_sequence(self):
        """Return the canonical MVP demo sequence: Gmail->Download->CRM->CRM->Slack."""
        return [
            ActivityEvent(event_type="email",  application="Gmail", action="open_email",     target="customer@example.com", session_id=TEST_SESSION),
            ActivityEvent(event_type="file",   application="Gmail", action="download",        target="request.pdf",          session_id=TEST_SESSION),
            ActivityEvent(event_type="crm",    application="CRM",   action="find_customer",   target="customer@example.com", session_id=TEST_SESSION),
            ActivityEvent(event_type="crm",    application="CRM",   action="update_customer", target="customer@example.com", session_id=TEST_SESSION),
            ActivityEvent(event_type="slack",  application="Slack", action="send_message",    target="#support",             session_id=TEST_SESSION),
        ]

    def test_insert_single_event(self):
        seq = self._make_sequence()
        returned_id = insert_event(seq[0])
        assert returned_id == seq[0].event_id

    def test_bulk_insert(self):
        seq = self._make_sequence()
        ids = insert_events(seq)
        assert len(ids) == len(seq)
        for e, eid in zip(seq, ids):
            assert eid == e.event_id

    def test_retrieve_by_session_chronological(self):
        """After inserting a sequence the session retrieval returns all events oldest-first."""
        seq = self._make_sequence()
        insert_events(seq)

        retrieved = get_events_by_session(TEST_SESSION)
        # Should contain at least our 5 events (may be more from test_insert_single_event)
        assert len(retrieved) >= 5
        # Must be ordered oldest first (ascending timestamp)
        timestamps = [e.timestamp for e in retrieved]
        assert timestamps == sorted(timestamps)

    def test_filtered_retrieval_crm_only(self):
        seq = self._make_sequence()
        insert_events(seq)

        f = ActivityEventFilter(session_id=TEST_SESSION, event_type="crm")
        crm_events = get_events(f)
        assert len(crm_events) >= 2
        for e in crm_events:
            assert e.event_type == EventType.crm

    def test_count_events_for_session(self):
        seq = self._make_sequence()
        before = count_events(session_id=TEST_SESSION)
        insert_events(seq)
        after = count_events(session_id=TEST_SESSION)
        assert after - before == len(seq)

    def test_get_events_default_limit(self):
        """GET /events with no filters returns up to 100 events."""
        events = get_events()
        assert isinstance(events, list)
        assert len(events) <= 100


# ---------------------------------------------------------------------------
# Self-running entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import unittest

    # Run via unittest runner if pytest not available
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
