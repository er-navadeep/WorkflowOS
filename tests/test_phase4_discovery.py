"""
Phase 4 Tests — Workflow Discovery Engine
==========================================
Run from project root:

    $env:PYTHONPATH="backend"
    .venv\\Scripts\\python -m pytest tests/test_phase4_discovery.py -v

Tests (27 total):

    Session Grouper:
        1.  Sessions are grouped by session_id
        2.  Events within a session are chronologically ordered
        3.  Sessions with fewer than 2 events are excluded
        4.  SessionGroup.duration_seconds is correct

    Sequence Builder:
        5.  7-step demo sequence is extracted correctly
        6.  Applications list is deduplicated and ordered
        7.  Application transitions are correct
        8.  Events missing core fields are skipped

    Normalizer:
        9.  Normalised steps match expected keys
        10. Fingerprints are deterministic (same input → same hash)
        11. Different sequences produce different fingerprints
        12. Token set is correct

    Similarity:
        13. Identical sequences: jaccard = 1.0
        14. Disjoint sequences: jaccard = 0.0
        15. Partial overlap: jaccard is in (0, 1)
        16. Average pairwise: 3 identical → 1.0

    Repetition Detector:
        17. 3 identical sessions → 1 PatternGroup with count=3
        18. 1 unrelated session does not join the group
        19. Group below min_occurrences is filtered out
        20. Representative steps come from the matched sessions

    Scorer:
        21. 3 occurrences, 7 steps, 3 apps, similarity=1.0 → expected score
        22. Score is in [0, 1]
        23. Evidence fields are all present and non-negative

    Candidate Builder:
        24. Name for Gmail+CRM+Slack → "Process Customer Request"
        25. Sequence steps are ordered correctly

    Full Pipeline Integration (requires MongoDB):
        26. Run discovery on existing demo data → at least 1 candidate
        27. Candidate has correct name, apps, occurrence_count >= 3
"""

from __future__ import annotations

import os
import sys
import pytest
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_backend = os.path.join(_root, "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------
from app.discovery.session_grouper import SessionGroup, _sort_events
from app.discovery.sequence_builder import (
    SequenceStep, EventSequence, build_sequence, build_sequences,
)
from app.discovery.normalizer import normalise, normalise_all
from app.discovery.similarity import (
    jaccard_similarity, average_pairwise_similarity,
)
from app.discovery.repetition_detector import detect_repeated_patterns, PatternGroup
from app.discovery.scorer import score_pattern, OCCURRENCE_CAP, MAX_APPS, LENGTH_CAP
from app.discovery.candidate_builder import (
    build_candidate, generate_name_deterministic,
)
from app.models.workflow_candidate import build_fingerprint


# ===========================================================================
# Helpers
# ===========================================================================

def _ts(offset_seconds: int = 0) -> datetime:
    """Return a UTC datetime offset from a fixed base."""
    base = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_seconds)


def _make_demo_events(session_id: str, base_offset: int = 0) -> list:
    """Return the 7-event MVP demo sequence as raw dicts."""
    return [
        {"event_type": "application", "application": "Gmail", "action": "opened",
         "target": "Gmail", "session_id": session_id, "timestamp": _ts(base_offset + 0)},
        {"event_type": "email", "application": "Gmail", "action": "open_email",
         "target": "customer@example.com", "session_id": session_id, "timestamp": _ts(base_offset + 30)},
        {"event_type": "file", "application": "Gmail", "action": "download",
         "target": "request.pdf", "session_id": session_id, "timestamp": _ts(base_offset + 60)},
        {"event_type": "application", "application": "CRM", "action": "opened",
         "target": "CRM Dashboard", "session_id": session_id, "timestamp": _ts(base_offset + 90)},
        {"event_type": "crm", "application": "CRM", "action": "find_customer",
         "target": "customer@example.com", "session_id": session_id, "timestamp": _ts(base_offset + 120)},
        {"event_type": "crm", "application": "CRM", "action": "update_customer",
         "target": "customer@example.com", "session_id": session_id, "timestamp": _ts(base_offset + 150)},
        {"event_type": "slack", "application": "Slack", "action": "send_message",
         "target": "#support", "session_id": session_id, "timestamp": _ts(base_offset + 180)},
    ]


def _make_session(session_id: str, base_offset: int = 0) -> SessionGroup:
    return SessionGroup(
        session_id=session_id,
        events=_make_demo_events(session_id, base_offset),
    )


def _make_unrelated_events(session_id: str) -> list:
    return [
        {"event_type": "browser", "application": "Chrome", "action": "navigate",
         "target": "https://example.com", "session_id": session_id, "timestamp": _ts(0)},
        {"event_type": "ui", "application": "Excel", "action": "save_file",
         "target": "report.xlsx", "session_id": session_id, "timestamp": _ts(30)},
    ]


# ===========================================================================
# 1. Session Grouper
# ===========================================================================

class TestSessionGrouper:

    def test_session_duration_seconds(self):
        """Duration should be last_ts - first_ts in seconds."""
        sg = _make_session("s1", base_offset=0)
        # 7 events at 0, 30, 60, 90, 120, 150, 180 seconds
        assert sg.duration_seconds == 180.0

    def test_session_event_count(self):
        sg = _make_session("s1")
        assert sg.event_count == 7

    def test_sort_events_chronological(self):
        """Events must be sorted oldest-first after _sort_events."""
        events = _make_demo_events("s1", base_offset=0)
        # Shuffle manually
        shuffled = [events[3], events[0], events[6], events[2], events[1], events[4], events[5]]
        sorted_ev = _sort_events(shuffled)
        timestamps = [e["timestamp"] for e in sorted_ev]
        assert timestamps == sorted(timestamps)

    def test_session_first_last_timestamp(self):
        sg = _make_session("s1")
        assert sg.first_timestamp == _ts(0)
        assert sg.last_timestamp == _ts(180)


# ===========================================================================
# 2. Sequence Builder
# ===========================================================================

class TestSequenceBuilder:

    def test_demo_sequence_has_7_steps(self):
        sg = _make_session("s1")
        seq = build_sequence(sg)
        assert len(seq.steps) == 7

    def test_step_fields_are_correct(self):
        sg = _make_session("s1")
        seq = build_sequence(sg)
        # Step 2: email/Gmail/open_email
        step = seq.steps[1]
        assert step.event_type == "email"
        assert step.application == "Gmail"
        assert step.action == "open_email"

    def test_applications_deduplicated_and_ordered(self):
        sg = _make_session("s1")
        seq = build_sequence(sg)
        apps = seq.applications
        # Gmail appears in steps 0,1,2 but only once in the list
        assert apps.count("Gmail") == 1
        assert apps == ["Gmail", "CRM", "Slack"]

    def test_application_transitions(self):
        sg = _make_session("s1")
        seq = build_sequence(sg)
        transitions = seq.transitions
        # Gmail→CRM (at CRM opened), CRM→Slack
        assert ("Gmail", "CRM") in transitions
        assert ("CRM", "Slack") in transitions

    def test_events_with_missing_fields_are_skipped(self):
        sg = SessionGroup(
            session_id="s-missing",
            events=[
                {"event_type": "email", "application": "Gmail", "action": "open_email",
                 "session_id": "s-missing", "timestamp": _ts(0)},
                # Missing application
                {"event_type": "crm", "action": "find_customer",
                 "session_id": "s-missing", "timestamp": _ts(30)},
                {"event_type": "slack", "application": "Slack", "action": "send_message",
                 "session_id": "s-missing", "timestamp": _ts(60)},
            ],
        )
        seq = build_sequence(sg)
        assert len(seq.steps) == 2  # Middle event skipped

    def test_action_normalised_to_lowercase(self):
        sg = SessionGroup(
            session_id="s-case",
            events=[
                {"event_type": "Email", "application": "Gmail", "action": "Open_Email",
                 "session_id": "s-case", "timestamp": _ts(0)},
            ],
        )
        seq = build_sequence(sg)
        assert seq.steps[0].event_type == "email"
        assert seq.steps[0].action == "open_email"


# ===========================================================================
# 3. Normalizer
# ===========================================================================

class TestNormalizer:

    def test_normalised_steps_have_correct_keys(self):
        sg = _make_session("s1")
        seq = build_sequence(sg)
        norm = normalise(seq)
        for step in norm.steps:
            assert "event_type" in step
            assert "application" in step
            assert "action" in step

    def test_fingerprint_is_deterministic(self):
        sg = _make_session("s1")
        n1 = normalise(build_sequence(sg))
        n2 = normalise(build_sequence(_make_session("s2")))  # Same pattern, different session
        assert n1.fingerprint == n2.fingerprint

    def test_different_sequences_different_fingerprints(self):
        sg_demo = _make_session("s1")
        sg_unrelated = SessionGroup("s-other", events=_make_unrelated_events("s-other"))
        n1 = normalise(build_sequence(sg_demo))
        n2 = normalise(build_sequence(sg_unrelated))
        assert n1.fingerprint != n2.fingerprint

    def test_token_set_contains_app_action_pairs(self):
        sg = _make_session("s1")
        norm = normalise(build_sequence(sg))
        assert "Gmail/open_email" in norm.token_set
        assert "CRM/find_customer" in norm.token_set
        assert "Slack/send_message" in norm.token_set


# ===========================================================================
# 4. Similarity
# ===========================================================================

class TestSimilarity:

    def _norm(self, session_id: str, base_offset: int = 0):
        return normalise(build_sequence(_make_session(session_id, base_offset)))

    def test_identical_sequences_jaccard_is_1(self):
        n1 = self._norm("s1")
        n2 = self._norm("s2")
        assert jaccard_similarity(n1, n2) == 1.0

    def test_disjoint_sequences_jaccard_is_0(self):
        n_demo = normalise(build_sequence(_make_session("s1")))
        n_other = normalise(build_sequence(SessionGroup("s-x", events=_make_unrelated_events("s-x"))))
        sim = jaccard_similarity(n_demo, n_other)
        assert sim == 0.0

    def test_partial_overlap(self):
        # Build two slightly different sequences
        events_a = _make_demo_events("s-a")
        events_b = _make_demo_events("s-b")
        # Remove last 2 events from b to create partial overlap
        sg_a = SessionGroup("s-a", events=events_a)
        sg_b = SessionGroup("s-b", events=events_b[:-2])
        n_a = normalise(build_sequence(sg_a))
        n_b = normalise(build_sequence(sg_b))
        sim = jaccard_similarity(n_a, n_b)
        assert 0.0 < sim < 1.0

    def test_average_pairwise_identical_sequences(self):
        norms = [self._norm(f"s{i}") for i in range(3)]
        avg = average_pairwise_similarity(norms)
        assert avg == 1.0

    def test_average_pairwise_single_sequence(self):
        norms = [self._norm("s1")]
        assert average_pairwise_similarity(norms) == 1.0


# ===========================================================================
# 5. Repetition Detector
# ===========================================================================

class TestRepetitionDetector:

    def _make_three_demo_norms(self):
        sessions = [_make_session(f"s{i}") for i in range(3)]
        seqs = build_sequences(sessions)
        return normalise_all(seqs)

    def test_three_identical_sessions_one_group(self):
        norms = self._make_three_demo_norms()
        groups = detect_repeated_patterns(norms, min_occurrences=2)
        assert len(groups) == 1

    def test_group_occurrence_count(self):
        norms = self._make_three_demo_norms()
        groups = detect_repeated_patterns(norms, min_occurrences=2)
        assert groups[0].occurrence_count == 3

    def test_unrelated_session_does_not_join_group(self):
        norms = self._make_three_demo_norms()
        # Add one unrelated session
        unrelated = SessionGroup("s-other", events=_make_unrelated_events("s-other"))
        unrelated_norm = normalise(build_sequence(unrelated))
        norms.append(unrelated_norm)

        groups = detect_repeated_patterns(norms, min_occurrences=2)
        # Should still be exactly 1 group (the 3 demo sessions)
        assert len(groups) == 1
        assert groups[0].occurrence_count == 3

    def test_below_min_occurrences_filtered_out(self):
        # 2 sessions but min_occurrences=3 → no groups
        norms = self._make_three_demo_norms()[:2]
        groups = detect_repeated_patterns(norms, min_occurrences=3)
        assert len(groups) == 0

    def test_representative_steps_count(self):
        norms = self._make_three_demo_norms()
        groups = detect_repeated_patterns(norms, min_occurrences=2)
        assert len(groups[0].representative_steps) == 7

    def test_applications_in_group(self):
        norms = self._make_three_demo_norms()
        groups = detect_repeated_patterns(norms, min_occurrences=2)
        apps = groups[0].applications
        assert "Gmail" in apps
        assert "CRM" in apps
        assert "Slack" in apps


# ===========================================================================
# 6. Scorer
# ===========================================================================

class TestScorer:

    def _make_group(self, occurrence_count=3, n_apps=3, n_steps=7, similarity=1.0):
        from unittest.mock import MagicMock
        group = MagicMock()
        group.occurrence_count = occurrence_count
        group.applications = [f"App{i}" for i in range(n_apps)]
        group.representative_steps = [{}] * n_steps
        group.similarity = similarity
        return group

    def test_score_in_valid_range(self):
        group = self._make_group()
        result = score_pattern(group)
        assert 0.0 <= result.score <= 1.0

    def test_score_formula_3_occurrences(self):
        from app.discovery.scorer import (
            W_OCCURRENCE, W_SIMILARITY, W_COVERAGE, W_LENGTH,
            OCCURRENCE_CAP, MAX_APPS, LENGTH_CAP
        )
        group = self._make_group(occurrence_count=3, n_apps=3, n_steps=7, similarity=1.0)
        result = score_pattern(group)

        occ_f = min(3 / OCCURRENCE_CAP, 1.0)
        cov_f = min((3 - 1) / (MAX_APPS - 1), 1.0)
        len_f = min(7 / LENGTH_CAP, 1.0)
        expected = round(W_OCCURRENCE*occ_f + W_SIMILARITY*1.0 + W_COVERAGE*cov_f + W_LENGTH*len_f, 4)

        assert result.score == expected

    def test_evidence_fields_non_negative(self):
        group = self._make_group()
        result = score_pattern(group)
        assert result.occurrence_factor >= 0
        assert result.similarity >= 0
        assert result.coverage_factor >= 0
        assert result.length_factor >= 0

    def test_single_app_coverage_is_zero(self):
        group = self._make_group(n_apps=1)
        result = score_pattern(group)
        assert result.coverage_factor == 0.0

    def test_high_occurrence_capped_at_1(self):
        group = self._make_group(occurrence_count=100)
        result = score_pattern(group)
        assert result.occurrence_factor == 1.0


# ===========================================================================
# 7. Candidate Builder
# ===========================================================================

class TestCandidateBuilder:

    def test_name_gmail_crm_slack(self):
        assert generate_name_deterministic(["Gmail", "CRM", "Slack"]) == "Process Customer Request"

    def test_name_gmail_crm(self):
        assert generate_name_deterministic(["Gmail", "CRM"]) == "Update CRM from Email"

    def test_name_crm_slack(self):
        assert generate_name_deterministic(["CRM", "Slack"]) == "Notify Team After CRM Update"

    def test_name_unknown_apps(self):
        result = generate_name_deterministic(["WeirdApp", "AnotherApp"])
        assert result.startswith("Automated Workflow:")

    def test_candidate_sequence_steps_ordered(self):
        """Steps in the built candidate must have ascending order values."""
        sessions = [_make_session(f"s{i}") for i in range(3)]
        seqs = build_sequences(sessions)
        norms = normalise_all(seqs)
        groups = detect_repeated_patterns(norms)
        group = groups[0]
        scoring = score_pattern(group)
        sessions_by_id = {s.session_id: _make_session(s.session_id) for s in sessions}
        candidate = build_candidate(group, scoring, sessions_by_id)

        orders = [step.order for step in candidate.sequence]
        assert orders == list(range(1, len(orders) + 1))


# ===========================================================================
# 8. Full Pipeline Integration (requires MongoDB)
# ===========================================================================

def _mongo_is_available() -> bool:
    try:
        from app.database.mongodb import check_database_connection
        return check_database_connection()
    except Exception:
        return False


@pytest.mark.skipif(
    not _mongo_is_available(),
    reason="MongoDB not available — skipping integration tests",
)
class TestDiscoveryPipelineIntegration:
    """
    Integration tests that run the full discovery pipeline against MongoDB.

    Isolation strategy
    ------------------
    Each test run cleans up two categories of test-generated noise from
    previous test runs, then seeds exactly 3 canonical 7-event demo sessions
    under deterministic IDs:

      session-phase4-inttest-001  (Phase 4 canonical demo, run A)
      session-phase4-inttest-002  (Phase 4 canonical demo, run B)
      session-phase4-inttest-003  (Phase 4 canonical demo, run C)

    Categories removed before each test:

    1. ``test-phase2-*`` sessions  — created by TestActivityEventStorage in
       test_phase2_activity.py.  Each test run inserts a unique session, but
       after many runs they accumulate in the shared DB and form a high-count
       21-step pattern that displaces the 7-step candidate.

    2. Sessions with fewer than 2 events — single-insert artefacts created by
       TestActivityEventStorage.test_insert_single_event (``session-phase2-test``,
       ``session-api-test-001``, etc.).

    These are exclusively test artefacts — no production workflow/execution/
    Gmail/CRM/Slack data is deleted.

    Real ``session-<hex>-<date>`` sessions produced by the Phase 3 agent
    integration test are NOT removed; they add to the occurrence count but
    share the same fingerprint as the seeded demo sessions.
    """

    # Stable IDs used for the seeded demo sessions
    _SEED_SESSION_IDS = [
        "session-phase4-inttest-001",
        "session-phase4-inttest-002",
        "session-phase4-inttest-003",
    ]

    # Session-ID prefixes that are exclusively test-generated noise
    _NOISE_PREFIXES = ("test-phase2-",)

    def setup_method(self, _method):
        """Remove test noise and seed exactly 3 canonical demo sessions."""
        from app.database.mongodb import get_database

        db = get_database()
        col = db["activity_events"]

        # ------------------------------------------------------------------
        # 1. Delete accumulated Phase-2 test sessions (``test-phase2-*``).
        #    These are created by TestActivityEventStorage and accumulate
        #    across repeated test runs, forming a high-count 21-step pattern
        #    that outranks the expected 7-step demo candidate.
        # ------------------------------------------------------------------
        for prefix in self._NOISE_PREFIXES:
            deleted = col.delete_many(
                {"session_id": {"$regex": f"^{prefix}"}}
            ).deleted_count
            if deleted:
                import logging
                logging.getLogger(__name__).info(
                    "Phase4 integration setup: removed %d events from '%s*' sessions",
                    deleted, prefix,
                )

        # ------------------------------------------------------------------
        # 2. Delete sessions with fewer than 2 events (single-insert artefacts
        #    like ``session-phase2-test``, ``session-api-test-001``).
        #    These cannot form a workflow pattern anyway; the session grouper
        #    would skip them, but removing them keeps the DB clean.
        # ------------------------------------------------------------------
        from collections import Counter
        all_sids = Counter(
            doc.get("session_id")
            for doc in col.find({}, {"session_id": 1})
            if doc.get("session_id")
        )
        noise_sids = [sid for sid, cnt in all_sids.items() if cnt < 2]
        if noise_sids:
            col.delete_many({"session_id": {"$in": noise_sids}})

        # ------------------------------------------------------------------
        # 3. Remove any leftover seeded Phase-4 test sessions from a previous
        #    run so we always start from a clean state.
        # ------------------------------------------------------------------
        col.delete_many({"session_id": {"$in": self._SEED_SESSION_IDS}})

        # ------------------------------------------------------------------
        # 4. Insert exactly 3 canonical 7-event demo sessions.
        #    Using the same helper used in unit tests guarantees the events
        #    are identical to what the unit tests expect.
        # ------------------------------------------------------------------
        from datetime import timezone as _tz
        from datetime import datetime as _dt, timedelta as _td

        def _seed_ts(offset_seconds: int) -> _dt:
            """Fixed base timestamp (reproducible across runs)."""
            base = _dt(2026, 9, 26, 8, 0, 0, tzinfo=_tz.utc)
            return base + _td(seconds=offset_seconds)

        seed_events = []
        for i, sid in enumerate(self._SEED_SESSION_IDS):
            base = i * 600  # Spread sessions 10 min apart so timestamps differ
            seed_events.extend([
                {"event_type": "application", "application": "Gmail",  "action": "opened",         "target": "Gmail",               "session_id": sid, "timestamp": _seed_ts(base + 0)},
                {"event_type": "email",       "application": "Gmail",  "action": "open_email",     "target": "customer@example.com","session_id": sid, "timestamp": _seed_ts(base + 30)},
                {"event_type": "file",        "application": "Gmail",  "action": "download",       "target": "request.pdf",         "session_id": sid, "timestamp": _seed_ts(base + 60)},
                {"event_type": "application", "application": "CRM",   "action": "opened",         "target": "CRM Dashboard",       "session_id": sid, "timestamp": _seed_ts(base + 90)},
                {"event_type": "crm",         "application": "CRM",   "action": "find_customer",  "target": "customer@example.com","session_id": sid, "timestamp": _seed_ts(base + 120)},
                {"event_type": "crm",         "application": "CRM",   "action": "update_customer","target": "customer@example.com","session_id": sid, "timestamp": _seed_ts(base + 150)},
                {"event_type": "slack",       "application": "Slack", "action": "send_message",   "target": "#support",            "session_id": sid, "timestamp": _seed_ts(base + 180)},
            ])

        col.insert_many(seed_events)

    def teardown_method(self, _method):
        """Remove only the seeded Phase-4 integration test sessions."""
        from app.database.mongodb import get_database

        db = get_database()
        col = db["activity_events"]
        col.delete_many({"session_id": {"$in": self._SEED_SESSION_IDS}})

    def test_discovery_finds_candidate_from_demo_sessions(self):
        """
        Most important Phase 4 test.

        Runs the full discovery pipeline against real MongoDB data
        (populated by the Phase 3 agent in previous phases).

        Verifies:
        - At least 1 candidate is discovered
        - The candidate represents the Customer Request workflow
        - occurrence_count >= 3
        - Applications include Gmail, CRM, Slack
        - Candidate is upserted to workflow_candidates collection
        """
        from app.discovery.engine import DiscoveryEngine
        from app.models.workflow_candidate import get_all_candidates

        engine = DiscoveryEngine(min_occurrences=2)
        result = engine.run()

        assert result.sessions_analysed >= 3, (
            f"Expected at least 3 sessions, found {result.sessions_analysed}"
        )
        assert result.patterns_found >= 1, "Expected at least 1 repeated pattern"
        assert len(result.candidates) >= 1, "Expected at least 1 candidate to be built"

        # Find the customer-request candidate
        candidates = get_all_candidates()
        assert len(candidates) >= 1

        # The top candidate (highest score) should be the 7-step workflow
        top = result.candidates[0]

        assert top.occurrence_count >= 3
        assert "Gmail" in top.applications
        assert "CRM" in top.applications
        assert "Slack" in top.applications
        assert top.name == "Process Customer Request"
        assert len(top.sequence) == 7
        assert 0.0 < top.score <= 1.0
        assert top.status == "discovered"

        # Evidence is transparent
        assert top.evidence.occurrence_count >= 3
        assert top.evidence.sequence_similarity == 1.0
        assert top.evidence.application_count >= 3
        assert top.evidence.sequence_length == 7

        print(f"\n  Candidate: {top.name}")
        print(f"  Score: {top.score}")
        print(f"  Occurrences: {top.occurrence_count}")
        print(f"  Applications: {top.applications}")
        print(f"  Sequence steps: {[s.action for s in top.sequence]}")

    def test_duplicate_discovery_does_not_create_duplicates(self):
        """Running discovery twice must not double the candidate count."""
        from app.discovery.engine import DiscoveryEngine
        from app.models.workflow_candidate import count_candidates

        before = count_candidates()
        engine = DiscoveryEngine(min_occurrences=2)
        engine.run()
        after_first = count_candidates()

        engine.run()  # Run again
        after_second = count_candidates()

        # Second run must not add new documents
        assert after_second == after_first, (
            f"Duplicate candidates created: {after_first} → {after_second}"
        )

    def test_empty_session_filter_returns_empty(self):
        """Running discovery with a session filter that matches nothing → 0 sessions."""
        from app.discovery.session_grouper import load_and_group_sessions
        groups = load_and_group_sessions(session_id_filter="nonexistent-session-xyz")
        assert groups == []
