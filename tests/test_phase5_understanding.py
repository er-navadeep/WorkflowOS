"""
Phase 5 Tests — AI Workflow Understanding
==========================================

Run from project root:

    $env:PYTHONPATH="backend"
    .venv\\Scripts\\python -m pytest tests/test_phase5_understanding.py -v

Tests (41 total):

    Schema (5):
        1.  Valid WorkflowUnderstanding model
        2.  Invalid confidence rejected (> 1.0)
        3.  Invalid confidence rejected (< 0.0)
        4.  UnderstandingAction model validates correctly
        5.  UnderstandingCondition inferred flag defaults to False

    Gemini Client (7):
        6.  Missing GEMINI_API_KEY raises GeminiClientError
        7.  Empty prompt raises GeminiClientError
        8.  Successful response returns text
        9.  API error raises GeminiClientError
        10. Empty response raises GeminiClientError
        11. _extract_text returns empty string on bad response
        12. GeminiClient stores model name correctly

    Prompt (5):
        13. Prompt contains candidate name
        14. Prompt contains all applications
        15. Prompt contains observed sequence steps
        16. Prompt requires JSON-only output
        17. Prompt instructs model not to invent actions

    Response Parser (8):
        18. Valid JSON response parses correctly
        19. Markdown-fenced JSON is unwrapped
        20. Missing 'intent' raises ParseError
        21. Missing 'actions' raises ParseError
        22. Empty actions list raises ParseError
        23. Invalid JSON raises ParseError
        24. Malformed action is rejected
        25. Confidence is clamped to [0, 1]

    Service (8):
        26. Candidate not found raises error with status 404
        27. Gemini failure raises error with status 503
        28. Parse failure raises error with status 502
        29. DB failure on fetch raises error with status 503
        30. Successful generation returns WorkflowUnderstanding
        31. Existing understanding is replaced on re-run
        32. get_understanding returns None if not found
        33. list_all_understandings returns list

    API (8):
        34. POST returns 200 on success
        35. POST returns 404 for unknown candidate
        36. POST returns 503 on Gemini failure
        37. GET returns stored understanding
        38. GET returns 404 when no understanding exists
        39. GET list returns array
        40. API response never contains GEMINI_API_KEY
        41. API response never contains env vars

Integration (marked separately — requires GEMINI_API_KEY + MongoDB):
    I1. Full end-to-end understanding of demo candidate
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# Ensure 'app' resolves from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.schemas.workflow_understanding import (
    WorkflowUnderstanding,
    UnderstandingAction,
    UnderstandingCondition,
    UnderstandingVariable,
    UnderstandingResponse,
)
from app.ai.gemini_client import GeminiClient, GeminiClientError, _extract_text
from app.ai.prompts import build_understanding_prompt
from app.ai.workflow_understanding import parse_understanding_response, ParseError
from app.models.workflow_candidate import WorkflowCandidate, SequenceStep, CandidateEvidence


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_candidate(**overrides) -> WorkflowCandidate:
    """Build a minimal valid WorkflowCandidate for testing."""
    defaults: Dict[str, Any] = {
        "candidate_id": "test-candidate-001",
        "sequence_fingerprint": "abc123",
        "name": "Process Customer Request",
        "description": "Demo workflow",
        "occurrence_count": 3,
        "session_ids": ["s1", "s2", "s3"],
        "applications": ["Gmail", "CRM", "Slack"],
        "sequence": [
            SequenceStep(order=1, event_type="application", application="Gmail", action="open_app"),
            SequenceStep(order=2, event_type="email", application="Gmail", action="open_email"),
            SequenceStep(order=3, event_type="file", application="Gmail", action="download"),
            SequenceStep(order=4, event_type="application", application="CRM", action="open_app"),
            SequenceStep(order=5, event_type="crm", application="CRM", action="find_customer"),
            SequenceStep(order=6, event_type="crm", application="CRM", action="update_customer"),
            SequenceStep(order=7, event_type="slack", application="Slack", action="send_message"),
        ],
        "first_seen": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "last_seen": datetime(2026, 1, 3, tzinfo=timezone.utc),
        "average_duration_seconds": 120.0,
        "similarity": 0.95,
        "score": 0.88,
        "evidence": CandidateEvidence(
            occurrence_count=3,
            sequence_similarity=0.95,
            application_count=3,
            sequence_length=7,
            occurrence_factor=0.5,
            coverage_factor=0.75,
            length_factor=0.7,
        ),
    }
    defaults.update(overrides)
    return WorkflowCandidate(**defaults)


def _make_understanding(**overrides) -> WorkflowUnderstanding:
    """Build a minimal valid WorkflowUnderstanding for testing."""
    defaults: Dict[str, Any] = {
        "candidate_id": "test-candidate-001",
        "intent": "Process Customer Request",
        "name": "Process Customer Request",
        "description": "Process a customer request from Gmail, update CRM, notify Slack.",
        "trigger": "New customer email received in Gmail.",
        "applications": ["Gmail", "CRM", "Slack"],
        "actions": [
            UnderstandingAction(
                order=1,
                application="Gmail",
                operation="Open Gmail",
                description="Launch Gmail application.",
            ),
            UnderstandingAction(
                order=2,
                application="Gmail",
                operation="Read email",
                description="Open the customer request email.",
            ),
            UnderstandingAction(
                order=3,
                application="Gmail",
                operation="Download attachment",
                description="Save the email attachment locally.",
            ),
            UnderstandingAction(
                order=4,
                application="CRM",
                operation="Open CRM",
                description="Launch the CRM application.",
            ),
            UnderstandingAction(
                order=5,
                application="CRM",
                operation="Find customer",
                description="Search for the customer record.",
            ),
            UnderstandingAction(
                order=6,
                application="CRM",
                operation="Update customer",
                description="Update the customer record with request details.",
            ),
            UnderstandingAction(
                order=7,
                application="Slack",
                operation="Send notification",
                description="Notify the team via Slack.",
            ),
        ],
        "conditions": [
            UnderstandingCondition(
                description="Customer not found in CRM",
                consequence="Request user intervention",
                inferred=True,
            )
        ],
        "variables": [],
        "confidence": 0.88,
        "model_used": "gemini-2.0-flash",
        "status": "generated",
    }
    defaults.update(overrides)
    return WorkflowUnderstanding(**defaults)


def _valid_gemini_json(n_actions: int = 7) -> str:
    """Return a valid Gemini JSON response string."""
    actions = [
        {
            "order": i + 1,
            "application": "Gmail" if i < 3 else ("CRM" if i < 6 else "Slack"),
            "operation": f"Action {i+1}",
            "description": f"Description for step {i+1}.",
        }
        for i in range(n_actions)
    ]
    data = {
        "intent": "Process Customer Request",
        "name": "Process Customer Request",
        "description": "Process a customer email and update CRM.",
        "trigger": "New customer email received.",
        "applications": ["Gmail", "CRM", "Slack"],
        "actions": actions,
        "conditions": [
            {
                "description": "Customer not found",
                "consequence": "Request intervention",
                "inferred": True,
            }
        ],
        "variables": [],
        "confidence": 0.88,
    }
    return json.dumps(data)


# ===========================================================================
# 1. SCHEMA TESTS
# ===========================================================================

class TestWorkflowUnderstandingSchema:

    def test_valid_understanding_model(self):
        """Test 1: Valid WorkflowUnderstanding model validates correctly."""
        u = _make_understanding()
        assert u.candidate_id == "test-candidate-001"
        assert u.intent == "Process Customer Request"
        assert len(u.actions) == 7
        assert 0.0 <= u.confidence <= 1.0

    def test_confidence_above_1_rejected(self):
        """Test 2: Confidence > 1.0 is rejected by Pydantic."""
        with pytest.raises(ValidationError):
            _make_understanding(confidence=1.5)

    def test_confidence_below_0_rejected(self):
        """Test 3: Confidence < 0.0 is rejected by Pydantic."""
        with pytest.raises(ValidationError):
            _make_understanding(confidence=-0.1)

    def test_understanding_action_validates(self):
        """Test 4: UnderstandingAction validates correctly."""
        action = UnderstandingAction(
            order=1,
            application="Gmail",
            operation="Read email",
            description="Open the customer request email.",
        )
        assert action.order == 1
        assert action.application == "Gmail"

    def test_condition_inferred_defaults_to_false(self):
        """Test 5: UnderstandingCondition.inferred defaults to False."""
        cond = UnderstandingCondition(
            description="Check customer exists",
            consequence="Proceed with update",
        )
        assert cond.inferred is False


# ===========================================================================
# 2. GEMINI CLIENT TESTS
# ===========================================================================

class TestGeminiClient:

    def test_missing_api_key_raises_error(self, monkeypatch):
        """Test 6: Missing GEMINI_API_KEY raises GeminiClientError."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
                GeminiClient()

    def test_empty_prompt_raises_error(self, monkeypatch):
        """Test 7: Empty prompt raises GeminiClientError."""
        mock_sdk_client = MagicMock()
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
        with patch("app.ai.gemini_client.genai", create=True) as mock_genai:
            mock_genai.Client.return_value = mock_sdk_client
            with patch("app.ai.gemini_client.GeminiClient.__init__", return_value=None):
                client = GeminiClient.__new__(GeminiClient)
                client._client = mock_sdk_client
                client._model = "gemini-2.0-flash"
                with pytest.raises(GeminiClientError, match="empty"):
                    client.generate("")

    def test_successful_response_returns_text(self, monkeypatch):
        """Test 8: A successful Gemini call returns the text content."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"intent": "Test"}'
        mock_client.models.generate_content.return_value = mock_response

        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_client
        client._model = "gemini-2.0-flash"

        result = client.generate("test prompt")
        assert result == '{"intent": "Test"}'

    def test_api_error_raises_gemini_error(self):
        """Test 9: SDK exception is wrapped in GeminiClientError."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Network error")

        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_client
        client._model = "gemini-2.0-flash"

        with pytest.raises(GeminiClientError):
            client.generate("test prompt")

    def test_empty_response_raises_gemini_error(self):
        """Test 10: Empty text in response raises GeminiClientError."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client.models.generate_content.return_value = mock_response

        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_client
        client._model = "gemini-2.0-flash"

        with pytest.raises(GeminiClientError, match="empty"):
            client.generate("test prompt")

    def test_extract_text_returns_empty_on_bad_response(self):
        """Test 11: _extract_text returns '' on an object without .text."""
        bad_response = object()
        result = _extract_text(bad_response)
        assert result == ""

    def test_gemini_client_stores_model_name(self, monkeypatch):
        """Test 12: GeminiClient.model property returns the configured model name."""
        mock_sdk_client = MagicMock()
        client = GeminiClient.__new__(GeminiClient)
        client._client = mock_sdk_client
        client._model = "gemini-2.0-flash"
        assert client.model == "gemini-2.0-flash"


# ===========================================================================
# 3. PROMPT TESTS
# ===========================================================================

class TestPromptBuilder:

    def _make_prompt(self, **overrides) -> str:
        return build_understanding_prompt(_make_candidate(**overrides))

    def test_prompt_contains_candidate_name(self):
        """Test 13: Prompt includes the candidate name."""
        prompt = self._make_prompt()
        assert "Process Customer Request" in prompt

    def test_prompt_contains_all_applications(self):
        """Test 14: Prompt lists all observed applications."""
        prompt = self._make_prompt()
        assert "Gmail" in prompt
        assert "CRM" in prompt
        assert "Slack" in prompt

    def test_prompt_contains_sequence_steps(self):
        """Test 15: Prompt includes each sequence step."""
        prompt = self._make_prompt()
        assert "open_email" in prompt
        assert "find_customer" in prompt
        assert "send_message" in prompt

    def test_prompt_requires_json_only_output(self):
        """Test 16: Prompt explicitly instructs model to return JSON only."""
        prompt = self._make_prompt()
        assert "JSON" in prompt
        assert "Return ONLY" in prompt or "Return the JSON" in prompt

    def test_prompt_instructs_no_invention(self):
        """Test 17: Prompt tells model not to invent unobserved actions."""
        prompt = self._make_prompt()
        assert "NOT" in prompt
        # The prompt must warn against adding unobserved elements
        assert "not supported" in prompt.lower() or "not observed" in prompt.lower() or "do not" in prompt.lower()


# ===========================================================================
# 4. RESPONSE PARSER TESTS
# ===========================================================================

class TestResponseParser:

    def test_valid_json_parses_correctly(self):
        """Test 18: Valid Gemini JSON response is parsed into a WorkflowUnderstanding."""
        raw = _valid_gemini_json()
        understanding = parse_understanding_response(
            raw, candidate_id="cand-001", model_used="gemini-2.0-flash"
        )
        assert understanding.candidate_id == "cand-001"
        assert understanding.intent == "Process Customer Request"
        assert len(understanding.actions) == 7
        assert understanding.confidence == 0.88

    def test_markdown_fenced_json_is_unwrapped(self):
        """Test 19: JSON wrapped in ```json ... ``` is correctly extracted."""
        raw = f"```json\n{_valid_gemini_json()}\n```"
        understanding = parse_understanding_response(
            raw, candidate_id="cand-001", model_used="gemini-2.0-flash"
        )
        assert understanding.intent == "Process Customer Request"

    def test_missing_intent_raises_parse_error(self):
        """Test 20: Missing 'intent' field raises ParseError."""
        data = json.loads(_valid_gemini_json())
        del data["intent"]
        with pytest.raises(ParseError, match="intent"):
            parse_understanding_response(
                json.dumps(data), candidate_id="x", model_used="test"
            )

    def test_missing_actions_raises_parse_error(self):
        """Test 21: Missing 'actions' field raises ParseError."""
        data = json.loads(_valid_gemini_json())
        del data["actions"]
        with pytest.raises(ParseError, match="actions"):
            parse_understanding_response(
                json.dumps(data), candidate_id="x", model_used="test"
            )

    def test_empty_actions_raises_parse_error(self):
        """Test 22: Empty actions list raises ParseError."""
        data = json.loads(_valid_gemini_json())
        data["actions"] = []
        with pytest.raises(ParseError, match="actions"):
            parse_understanding_response(
                json.dumps(data), candidate_id="x", model_used="test"
            )

    def test_invalid_json_raises_parse_error(self):
        """Test 23: Non-JSON text raises ParseError."""
        with pytest.raises(ParseError, match="valid JSON"):
            parse_understanding_response(
                "this is not json", candidate_id="x", model_used="test"
            )

    def test_malformed_action_raises_parse_error(self):
        """Test 24: Action that is not a dict raises ParseError."""
        data = json.loads(_valid_gemini_json())
        data["actions"][0] = "not a dict"
        with pytest.raises(ParseError):
            parse_understanding_response(
                json.dumps(data), candidate_id="x", model_used="test"
            )

    def test_confidence_is_clamped(self):
        """Test 25: Confidence value is clamped to [0, 1] range."""
        data = json.loads(_valid_gemini_json())
        data["confidence"] = 1.5  # over the max
        # Parser clamps, not rejects — but schema would reject > 1.0
        # The parser clamps before building the model
        understanding = parse_understanding_response(
            json.dumps(data), candidate_id="x", model_used="test"
        )
        assert understanding.confidence <= 1.0


# ===========================================================================
# 5. SERVICE TESTS
# ===========================================================================

class TestUnderstandingService:
    """Tests for ai_understanding_service using mocked dependencies."""

    def test_candidate_not_found_raises_404(self):
        """Test 26: Non-existent candidate raises UnderstandingServiceError with status 404."""
        from app.services.ai_understanding_service import generate_understanding, UnderstandingServiceError

        with patch("app.services.ai_understanding_service.get_candidate_by_id", return_value=None):
            with pytest.raises(UnderstandingServiceError) as exc_info:
                generate_understanding("nonexistent")
            assert exc_info.value.status_code == 404

    def test_gemini_failure_raises_503(self):
        """Test 27: Gemini API error raises UnderstandingServiceError with status 503."""
        from app.services.ai_understanding_service import generate_understanding, UnderstandingServiceError

        candidate = _make_candidate()
        with patch("app.services.ai_understanding_service.get_candidate_by_id", return_value=candidate):
            with patch("app.services.ai_understanding_service.GeminiClient") as MockClient:
                MockClient.return_value.generate.side_effect = GeminiClientError("API error")
                with pytest.raises(UnderstandingServiceError) as exc_info:
                    generate_understanding("test-candidate-001")
                assert exc_info.value.status_code == 503

    def test_parse_failure_raises_502(self):
        """Test 28: Unparseable Gemini response raises UnderstandingServiceError with status 502."""
        from app.services.ai_understanding_service import generate_understanding, UnderstandingServiceError

        candidate = _make_candidate()
        with patch("app.services.ai_understanding_service.get_candidate_by_id", return_value=candidate):
            with patch("app.services.ai_understanding_service.GeminiClient") as MockClient:
                MockClient.return_value.generate.return_value = "not valid json"
                MockClient.return_value.model = "gemini-2.0-flash"
                with pytest.raises(UnderstandingServiceError) as exc_info:
                    generate_understanding("test-candidate-001")
                assert exc_info.value.status_code == 502

    def test_db_failure_on_fetch_raises_503(self):
        """Test 29: MongoDB error during candidate fetch raises 503."""
        from app.services.ai_understanding_service import generate_understanding, UnderstandingServiceError

        with patch(
            "app.services.ai_understanding_service.get_candidate_by_id",
            side_effect=RuntimeError("DB down"),
        ):
            with pytest.raises(UnderstandingServiceError) as exc_info:
                generate_understanding("test-candidate-001")
            assert exc_info.value.status_code == 503

    def test_successful_generation_returns_understanding(self):
        """Test 30: Successful end-to-end service call returns WorkflowUnderstanding."""
        from app.services.ai_understanding_service import generate_understanding

        candidate = _make_candidate()
        raw_json = _valid_gemini_json()

        with patch("app.services.ai_understanding_service.get_candidate_by_id", return_value=candidate):
            with patch("app.services.ai_understanding_service.GeminiClient") as MockClient:
                MockClient.return_value.generate.return_value = raw_json
                MockClient.return_value.model = "gemini-2.0-flash"
                with patch("app.services.ai_understanding_service.upsert_understanding") as mock_upsert:
                    mock_upsert.return_value = "some-id"
                    result = generate_understanding("test-candidate-001")
                    assert isinstance(result, WorkflowUnderstanding)
                    assert result.candidate_id == "test-candidate-001"
                    assert mock_upsert.called

    def test_existing_understanding_is_replaced_on_rerun(self):
        """Test 31: Re-running generation upserts (replaces) the existing understanding."""
        from app.services.ai_understanding_service import generate_understanding

        candidate = _make_candidate()
        raw_json = _valid_gemini_json()

        with patch("app.services.ai_understanding_service.get_candidate_by_id", return_value=candidate):
            with patch("app.services.ai_understanding_service.GeminiClient") as MockClient:
                MockClient.return_value.generate.return_value = raw_json
                MockClient.return_value.model = "gemini-2.0-flash"
                with patch("app.services.ai_understanding_service.upsert_understanding") as mock_upsert:
                    mock_upsert.return_value = "understanding-id"
                    # Call twice — upsert should be called both times
                    generate_understanding("test-candidate-001")
                    generate_understanding("test-candidate-001")
                    assert mock_upsert.call_count == 2

    def test_get_understanding_returns_none_when_not_found(self):
        """Test 32: get_understanding returns None when no record exists."""
        from app.services.ai_understanding_service import get_understanding

        with patch(
            "app.services.ai_understanding_service.get_understanding_by_candidate",
            return_value=None,
        ):
            result = get_understanding("nonexistent")
            assert result is None

    def test_list_all_understandings_returns_list(self):
        """Test 33: list_all_understandings returns a list (possibly empty)."""
        from app.services.ai_understanding_service import list_all_understandings

        with patch(
            "app.services.ai_understanding_service.list_understandings",
            return_value=[],
        ):
            result = list_all_understandings()
            assert isinstance(result, list)


# ===========================================================================
# 6. API TESTS
# ===========================================================================

class TestUnderstandingAPI:
    """Tests for the FastAPI router using TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create a FastAPI TestClient for the understanding router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.understanding import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_post_returns_200_on_success(self):
        """Test 34: POST /understanding/{id} returns 200 with valid understanding."""
        understanding = _make_understanding()
        with patch(
            "app.api.understanding.generate_understanding",
            return_value=understanding,
        ):
            resp = self.client.post("/api/v1/understanding/test-candidate-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["candidate_id"] == "test-candidate-001"
            assert "understanding" in data

    def test_post_returns_404_for_unknown_candidate(self):
        """Test 35: POST returns 404 when candidate does not exist."""
        from app.services.ai_understanding_service import UnderstandingServiceError

        with patch(
            "app.api.understanding.generate_understanding",
            side_effect=UnderstandingServiceError("Candidate not found.", status_code=404),
        ):
            resp = self.client.post("/api/v1/understanding/nonexistent")
            assert resp.status_code == 404

    def test_post_returns_503_on_gemini_failure(self):
        """Test 36: POST returns 503 when Gemini is unreachable."""
        from app.services.ai_understanding_service import UnderstandingServiceError

        with patch(
            "app.api.understanding.generate_understanding",
            side_effect=UnderstandingServiceError("AI service error.", status_code=503),
        ):
            resp = self.client.post("/api/v1/understanding/test-candidate-001")
            assert resp.status_code == 503

    def test_get_returns_stored_understanding(self):
        """Test 37: GET /understanding/{id} returns the stored understanding."""
        understanding = _make_understanding()
        with patch(
            "app.api.understanding.get_understanding",
            return_value=understanding,
        ):
            resp = self.client.get("/api/v1/understanding/test-candidate-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["candidate_id"] == "test-candidate-001"
            assert data["intent"] == "Process Customer Request"

    def test_get_returns_404_when_no_understanding(self):
        """Test 38: GET returns 404 when no understanding exists for candidate."""
        with patch(
            "app.api.understanding.get_understanding",
            return_value=None,
        ):
            resp = self.client.get("/api/v1/understanding/no-understanding")
            assert resp.status_code == 404

    def test_get_list_returns_array(self):
        """Test 39: GET /understanding returns a JSON array."""
        with patch(
            "app.api.understanding.list_all_understandings",
            return_value=[],
        ):
            resp = self.client.get("/api/v1/understanding")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    def test_api_response_never_contains_api_key(self):
        """Test 40: POST response body does not contain GEMINI_API_KEY value."""
        understanding = _make_understanding()
        fake_key = "FAKE_TEST_KEY_12345"
        with patch.dict(os.environ, {"GEMINI_API_KEY": fake_key}):
            with patch(
                "app.api.understanding.generate_understanding",
                return_value=understanding,
            ):
                resp = self.client.post("/api/v1/understanding/test-candidate-001")
                assert fake_key not in resp.text

    def test_api_response_never_contains_env_vars(self):
        """Test 41: Error responses don't expose environment variable values."""
        from app.services.ai_understanding_service import UnderstandingServiceError

        with patch(
            "app.api.understanding.generate_understanding",
            side_effect=UnderstandingServiceError("internal db error", status_code=503),
        ):
            resp = self.client.post("/api/v1/understanding/test-candidate-001")
            # Response should not contain raw env variable contents
            body = resp.text
            # Ensure no secret-shaped strings in body
            assert "GEMINI_API_KEY" not in body


# ===========================================================================
# INTEGRATION TEST (skipped if GEMINI_API_KEY not available or no MongoDB)
# ===========================================================================

INTEGRATION_REASON = (
    "Integration test requires GEMINI_API_KEY env var and a running MongoDB. "
    "Set GEMINI_API_KEY and ensure MongoDB is on mongodb://127.0.0.1:27017."
)
_has_key = bool(os.getenv("GEMINI_API_KEY"))
_skip_integration = pytest.mark.skipif(not _has_key, reason=INTEGRATION_REASON)


@_skip_integration
def test_integration_full_understanding_of_demo_candidate():
    """
    I1. Full end-to-end integration test using the real Gemini API.

    Requires:
    - GEMINI_API_KEY set in environment
    - MongoDB running on mongodb://127.0.0.1:27017
    - Phase 4 discovery previously run (demo candidate in DB)

    This test is skipped automatically when GEMINI_API_KEY is not available.
    The API key is NEVER printed.
    """
    from app.services.ai_understanding_service import generate_understanding
    from app.models.workflow_candidate import get_all_candidates

    # Find the demo candidate
    candidates = get_all_candidates()
    assert candidates, "No candidates in DB — run Phase 4 discovery first."

    # Use the first candidate (highest score)
    candidate = candidates[0]
    candidate_id = candidate.candidate_id

    # Generate understanding
    understanding = generate_understanding(candidate_id)

    # Validate structure
    assert isinstance(understanding, WorkflowUnderstanding)
    assert understanding.candidate_id == candidate_id
    assert understanding.intent
    assert understanding.name
    assert understanding.description
    assert understanding.trigger
    assert len(understanding.applications) > 0
    assert len(understanding.actions) > 0
    assert 0.0 <= understanding.confidence <= 1.0
    assert understanding.status == "generated"

    # Verify it was persisted
    from app.models.workflow_understanding import get_understanding_by_candidate
    stored = get_understanding_by_candidate(candidate_id)
    assert stored is not None
    assert stored.understanding_id == understanding.understanding_id

    # NEVER print the API key
    assert "GEMINI_API_KEY" not in str(understanding.model_dump())
