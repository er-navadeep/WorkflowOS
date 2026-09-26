"""
Phase 3 Tests — Demo Activity Agent
=====================================
Run from project root:

    $env:PYTHONPATH="backend;activity-agent"
    .venv\\Scripts\\python -m pytest tests/test_phase3_agent.py -v

Tests (13 total):

    Schema / source (no network):
        1.  CustomerRequestSource generates exactly 7 events per session
        2.  All events share the provided session_id
        3.  Events are ordered chronologically (ascending timestamps)
        4.  Event types match the expected sequence
        5.  Metadata is present and contains 'source' = 'simulation'
        6.  Repeated calls with different session_ids produce distinct events
        7.  Demo data cycles correctly across 3 repetitions

    Session management:
        8.  new_session_id() produces unique IDs on every call
        9.  new_session_id() format matches 'session-<hex>-<date>'
        10. demo_session_id(0) == 'session-demo-run-001'

    Config:
        11. AgentConfig reads defaults correctly
        12. AgentConfig derives correct endpoint URLs

    Integration (requires running backend on 127.0.0.1:8000):
        13. Three simulation repetitions are stored in MongoDB with
            distinct session IDs, correct event counts, and correct
            sequence order.

Test 13 is skipped automatically if the backend is not reachable.
"""

from __future__ import annotations

import os
import sys
import re
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_agent_dir = os.path.join(_root, "activity-agent")
_backend_dir = os.path.join(_root, "backend")

for p in [_agent_dir, _backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Imports (all local)
# ---------------------------------------------------------------------------

from agent.config import AgentConfig
from agent.session import new_session_id, demo_session_id
from sources.simulation.customer_request import CustomerRequestSource
from sources.simulation.demo_data import DEMO_EMAILS, get_demo_email, get_demo_customer

from app.schemas.activity_event import EventType


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def source() -> CustomerRequestSource:
    return CustomerRequestSource()


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig()


# ===========================================================================
# Source tests (pure unit — no network)
# ===========================================================================

class TestCustomerRequestSource:

    def test_generates_exactly_7_events(self, source):
        """Each session must produce exactly 7 events (the MVP sequence)."""
        events = source.generate_events_list("test-session-001")
        assert len(events) == 7, f"Expected 7 events, got {len(events)}"

    def test_all_events_share_session_id(self, source):
        """Every event must carry the provided session_id."""
        sid = "test-session-xyz"
        events = source.generate_events_list(sid)
        for e in events:
            assert e.session_id == sid, f"Event {e.event_id} has wrong session_id: {e.session_id}"

    def test_events_are_chronologically_ordered(self, source):
        """Timestamps must be monotonically non-decreasing."""
        events = source.generate_events_list("test-session-order")
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps), "Events are not in chronological order"

    def test_event_type_sequence_is_correct(self, source):
        """
        The sequence must be:
        application, email, file, application, crm, crm, slack
        """
        events = source.generate_events_list("test-session-types")
        expected = [
            EventType.application,
            EventType.email,
            EventType.file,
            EventType.application,
            EventType.crm,
            EventType.crm,
            EventType.slack,
        ]
        actual = [e.event_type for e in events]
        assert actual == expected, f"Type sequence mismatch: {actual}"

    def test_event_action_sequence_is_correct(self, source):
        """Verify the action verbs match the MVP workflow specification."""
        events = source.generate_events_list("test-session-actions")
        expected_actions = [
            "opened",
            "open_email",
            "download",
            "opened",
            "find_customer",
            "update_customer",
            "send_message",
        ]
        actual_actions = [e.action for e in events]
        assert actual_actions == expected_actions, f"Action sequence: {actual_actions}"

    def test_metadata_present_and_contains_source_tag(self, source):
        """Every event metadata dict must have 'source': 'simulation'."""
        events = source.generate_events_list("test-session-meta")
        for e in events:
            assert isinstance(e.metadata, dict), f"Event {e.event_id} metadata is not a dict"
            assert e.metadata.get("source") == "simulation", (
                f"Event {e.event_id} missing source=simulation in metadata"
            )

    def test_repetition_index_cycles_through_demo_data(self, source):
        """Three repetitions should use three different customer emails."""
        targets = set()
        for i in range(3):
            events = source.generate_events_list(f"session-{i}", repetition_index=i)
            email_event = events[1]  # second event is always the 'open_email'
            targets.add(email_event.target)
        assert len(targets) == 3, f"Expected 3 distinct email targets, got: {targets}"

    def test_source_name(self, source):
        assert source.name == "CustomerRequestSimulation"

    def test_generate_events_list_is_equivalent_to_iterator(self, source):
        """generate_events_list() must return same events as generate_events() iterator."""
        sid = "test-equiv"
        from_list = source.generate_events_list(sid)
        from_iter = list(source.generate_events(sid))
        assert len(from_list) == len(from_iter)
        for a, b in zip(from_list, from_iter):
            assert a.action == b.action
            assert a.event_type == b.event_type


# ===========================================================================
# Session management tests
# ===========================================================================

class TestSessionManagement:

    def test_new_session_id_is_unique(self):
        """Two consecutive calls must not produce the same ID."""
        s1 = new_session_id()
        s2 = new_session_id()
        assert s1 != s2

    def test_new_session_id_format(self):
        """Must match 'session-<8hex>-<YYYY-MM-DD>'."""
        sid = new_session_id()
        pattern = r"^session-[0-9a-f]{8}-\d{4}-\d{2}-\d{2}$"
        assert re.match(pattern, sid), f"Format mismatch: {sid!r}"

    def test_demo_session_id_format(self):
        assert demo_session_id(0) == "session-demo-run-001"
        assert demo_session_id(1) == "session-demo-run-002"
        assert demo_session_id(9) == "session-demo-run-010"


# ===========================================================================
# Config tests
# ===========================================================================

class TestAgentConfig:

    def test_default_backend_url(self, config):
        assert config.backend_url == "http://127.0.0.1:8000"

    def test_default_repetitions(self, config):
        assert config.simulation_repetitions == 3

    def test_events_endpoint_derived(self, config):
        assert config.events_endpoint == "http://127.0.0.1:8000/api/v1/events"

    def test_batch_endpoint_derived(self, config):
        assert config.batch_endpoint == "http://127.0.0.1:8000/api/v1/events/batch"

    def test_health_endpoint_derived(self, config):
        assert config.health_endpoint == "http://127.0.0.1:8000/health"


# ===========================================================================
# Demo data tests
# ===========================================================================

class TestDemoData:

    def test_three_demo_emails_defined(self):
        assert len(DEMO_EMAILS) == 3

    def test_get_demo_email_cycles(self):
        """Index beyond list length should cycle, not error."""
        e0 = get_demo_email(0)
        e3 = get_demo_email(3)
        assert e0["email_id"] == e3["email_id"]

    def test_get_demo_customer_by_email(self):
        c = get_demo_customer("support@acme.com")
        assert c["customer_id"] == "CUS-001"

    def test_get_demo_customer_unknown_returns_fallback(self):
        c = get_demo_customer("unknown@nobody.com")
        assert c is not None  # falls back to first customer


# ===========================================================================
# Integration test (requires running backend)
# ===========================================================================

def _backend_is_reachable() -> bool:
    """Return True if the local backend is running and healthy."""
    try:
        import requests
        resp = requests.get("http://127.0.0.1:8000/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not _backend_is_reachable(),
    reason="Backend not reachable at http://127.0.0.1:8000 — skipping integration test",
)
class TestAgentIntegration:
    """
    Runs the full agent loop against the real backend.
    Verifies MongoDB receives the correct events with distinct sessions.
    """

    def test_three_repetitions_stored_in_mongodb(self):
        """
        Core end-to-end test:

        1. Run 3 simulation repetitions
        2. Verify 3 distinct session IDs in MongoDB
        3. Verify each session has exactly 7 events
        4. Verify event sequence within each session
        5. Verify at least one CRM update event per session
        6. Verify at least one Slack event per session
        """
        from agent.config import AgentConfig
        from agent.runner import AgentRunner
        from sources.simulation.customer_request import CustomerRequestSource

        # Run with fast delays for test speed
        os.environ["AGENT_EVENT_DELAY_SECONDS"] = "0.05"
        os.environ["AGENT_SESSION_DELAY_SECONDS"] = "0.05"

        config = AgentConfig()
        source = CustomerRequestSource()
        runner = AgentRunner(source=source, config=config)
        summary = runner.run(repetitions=3)

        # --- Agent-level assertions ---
        assert summary.total_sessions == 3
        assert summary.total_events_sent == 21   # 3 sessions x 7 events
        assert summary.total_events_failed == 0
        assert summary.success_rate == 100.0

        session_ids = [s.session_id for s in summary.sessions]
        assert len(set(session_ids)) == 3, "Session IDs must be unique"

        # --- MongoDB verification ---
        sys.path.insert(0, _backend_dir)
        from app.activity.storage import get_events_by_session, count_events
        from app.schemas.activity_event import EventType

        for sess in summary.sessions:
            events = get_events_by_session(sess.session_id)

            # Count
            assert len(events) == 7, (
                f"Session {sess.session_id} has {len(events)} events, expected 7"
            )

            # Chronological order
            timestamps = [e.timestamp for e in events]
            assert timestamps == sorted(timestamps), "Events not in chronological order"

            # CRM update present
            crm_updates = [e for e in events if e.action == "update_customer"]
            assert len(crm_updates) >= 1, "No CRM update event found"

            # Slack notification present
            slack_events = [e for e in events if e.event_type == EventType.slack]
            assert len(slack_events) >= 1, "No Slack notification event found"

        print(f"\nIntegration test PASSED: {summary.total_events_sent} events across "
              f"{summary.total_sessions} sessions stored in MongoDB.")
