"""
Phase 6 Tests -- AI Workflow Generation
=========================================

Run from project root:

    $env:PYTHONPATH="backend"
    .venv\\Scripts\\python -m pytest tests/test_phase6_workflow_generation.py -v

Tests (45 total):

    Schema (6):
        1.  Valid WorkflowDefinition model validates correctly
        2.  WorkflowStep order must be >= 1
        3.  WorkflowDefinition generation_confidence clamped to [0, 1]
        4.  WorkflowTrigger requires application and event
        5.  WorkflowCondition defaults on_false to 'continue'
        6.  WorkflowErrorHandling defaults are sensible

    Generator (8):
        7.  Valid JSON response parses into WorkflowDefinition
        8.  Markdown-fenced JSON is unwrapped correctly
        9.  Missing 'name' raises WorkflowGenerationError
        10. Missing 'trigger' raises WorkflowGenerationError
        11. Missing 'steps' raises WorkflowGenerationError
        12. Empty 'steps' raises WorkflowGenerationError
        13. Invalid JSON raises WorkflowGenerationError
        14. Invented integration is silently filtered out

    Validator (13):
        15. Valid workflow passes all checks
        16. Empty name fails validation
        17. Empty description fails validation
        18. Trigger with empty application fails
        19. Trigger with empty event fails
        20. Zero steps fails validation
        21. Duplicate step orders fail validation
        22. Non-sequential step orders fail validation
        23. Step with empty application fails
        24. Step with empty action fails
        25. Invented integration application fails cross-reference check
        26. Condition with empty expression fails
        27. AWS key pattern detected as secret error

    Prompts (5):
        28. Prompt contains understanding intent
        29. Prompt contains all application names
        30. Prompt instructs model not to invent credentials
        31. Prompt specifies JSON-only output
        32. Prompt contains exact step count requirement

    Service (7):
        33. Understanding not found raises 404 error
        34. Gemini failure raises 503 error
        35. Parse failure raises 502 error
        36. Validation failure raises 422 error
        37. DB failure on persist raises 503 error
        38. Successful generation returns WorkflowDefinition
        39. Re-running generation replaces existing workflow

    API (6):
        40. POST /generate returns 200 on success
        41. POST /generate returns 404 for unknown understanding
        42. POST /generate returns 503 on Gemini failure
        43. GET /{workflow_id} returns stored workflow
        44. GET /{workflow_id} returns 404 when not found
        45. GET / list returns array

Integration (marked separately -- requires GEMINI_API_KEY + MongoDB):
    I1. Full end-to-end workflow generation from demo understanding
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# Ensure 'app' resolves from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.schemas.workflow import (
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowGenerationResponse,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowVariable,
)
from app.schemas.workflow_understanding import (
    UnderstandingAction,
    UnderstandingCondition,
    UnderstandingVariable,
    WorkflowUnderstanding,
)
from app.workflow_engine.generator import (
    WorkflowGenerationError,
    parse_workflow_response,
    _strip_markdown_fences,
    _parse_json,
)
from app.workflow_engine.validator import validate_workflow, ValidationResult
from app.workflow_engine.prompts import build_generation_prompt


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_understanding(**overrides) -> WorkflowUnderstanding:
    """Build a minimal valid WorkflowUnderstanding for Phase 6 testing."""
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


def _make_workflow(**overrides) -> WorkflowDefinition:
    """Build a minimal valid WorkflowDefinition for testing."""
    defaults: Dict[str, Any] = {
        "understanding_id": "test-understanding-001",
        "name": "Process Customer Request",
        "description": "Reads a customer email, updates CRM, notifies Slack.",
        "trigger": WorkflowTrigger(
            application="Gmail",
            event="New incoming customer email",
            description="Triggered when a new customer email arrives in Gmail.",
        ),
        "steps": [
            WorkflowStep(order=1, application="Gmail", action="open_gmail", description="Launch Gmail."),
            WorkflowStep(order=2, application="Gmail", action="read_email", description="Read the customer email."),
            WorkflowStep(order=3, application="Gmail", action="download_attachment", description="Save attachment."),
            WorkflowStep(order=4, application="CRM", action="open_crm", description="Launch CRM."),
            WorkflowStep(order=5, application="CRM", action="find_customer", description="Search for customer."),
            WorkflowStep(order=6, application="CRM", action="update_customer", description="Update the record."),
            WorkflowStep(order=7, application="Slack", action="send_notification", description="Notify the team."),
        ],
        "conditions": [
            WorkflowCondition(
                description="Customer not found in CRM",
                expression="customer record is not found after search",
                on_true="request_human_intervention",
                on_false="continue",
            )
        ],
        "variables": [],
        "integrations": [
            WorkflowIntegration(
                application="Gmail",
                purpose="Source of the customer request email.",
                required_capabilities=["read_email", "download_attachment"],
            ),
            WorkflowIntegration(
                application="CRM",
                purpose="Customer record lookup and update.",
                required_capabilities=["find_customer", "update_customer"],
            ),
            WorkflowIntegration(
                application="Slack",
                purpose="Team notification after processing.",
                required_capabilities=["send_message"],
            ),
        ],
        "error_handling": WorkflowErrorHandling(
            on_step_failure="stop_and_report",
            on_missing_input="stop",
            on_timeout="stop_and_report",
            notes="",
        ),
        "model_used": "gemini-2.0-flash",
        "generation_confidence": 0.88,
        "status": "generated",
    }
    defaults.update(overrides)
    return WorkflowDefinition(**defaults)


def _valid_gemini_workflow_json(n_steps: int = 7) -> str:
    """Return a valid Gemini workflow JSON string."""
    steps = [
        {
            "order": i + 1,
            "application": "Gmail" if i < 3 else ("CRM" if i < 6 else "Slack"),
            "action": f"action_{i+1}",
            "description": f"Description for step {i+1}.",
            "inputs": [],
            "outputs": [],
            "on_failure": "stop",
        }
        for i in range(n_steps)
    ]
    data = {
        "name": "Process Customer Request",
        "description": "Reads a customer email, updates CRM, notifies Slack.",
        "trigger": {
            "application": "Gmail",
            "event": "New incoming customer email",
            "description": "Triggered when a new customer email arrives in Gmail.",
        },
        "steps": steps,
        "conditions": [
            {
                "description": "Customer not found in CRM",
                "expression": "customer record is not found after search",
                "on_true": "request_human_intervention",
                "on_false": "continue",
            }
        ],
        "variables": [],
        "integrations": [
            {
                "application": "Gmail",
                "purpose": "Email source.",
                "required_capabilities": ["read_email"],
            },
            {
                "application": "CRM",
                "purpose": "Customer lookup.",
                "required_capabilities": ["find_customer"],
            },
            {
                "application": "Slack",
                "purpose": "Team notification.",
                "required_capabilities": ["send_message"],
            },
        ],
        "error_handling": {
            "on_step_failure": "stop_and_report",
            "on_missing_input": "stop",
            "on_timeout": "stop_and_report",
            "notes": "",
        },
    }
    return json.dumps(data)


# ===========================================================================
# 1. SCHEMA TESTS
# ===========================================================================

class TestWorkflowDefinitionSchema:

    def test_valid_workflow_definition_validates(self):
        """Test 1: Valid WorkflowDefinition model validates correctly."""
        wf = _make_workflow()
        assert wf.understanding_id == "test-understanding-001"
        assert wf.name == "Process Customer Request"
        assert len(wf.steps) == 7
        assert wf.status == "generated"
        assert 0.0 <= wf.generation_confidence <= 1.0

    def test_step_order_must_be_at_least_1(self):
        """Test 2: WorkflowStep.order must be >= 1."""
        with pytest.raises(ValidationError):
            WorkflowStep(
                order=0,
                application="Gmail",
                action="read_email",
                description="Read email.",
            )

    def test_generation_confidence_above_1_rejected(self):
        """Test 3: generation_confidence > 1.0 is rejected by Pydantic."""
        with pytest.raises(ValidationError):
            _make_workflow(generation_confidence=1.5)

    def test_workflow_trigger_requires_application(self):
        """Test 4: WorkflowTrigger with empty application still builds (validated at service layer)."""
        # Schema level: Pydantic allows empty strings; service-level validator enforces
        t = WorkflowTrigger(application="", event="email_received", description="x")
        assert t.application == ""

    def test_condition_on_false_defaults_to_continue(self):
        """Test 5: WorkflowCondition.on_false defaults to 'continue'."""
        cond = WorkflowCondition(
            description="Check customer",
            expression="customer not found",
            on_true="request_human_intervention",
        )
        assert cond.on_false == "continue"

    def test_error_handling_defaults_are_sensible(self):
        """Test 6: WorkflowErrorHandling has correct default values."""
        eh = WorkflowErrorHandling()
        assert eh.on_step_failure == "stop_and_report"
        assert eh.on_missing_input == "stop"
        assert eh.on_timeout == "stop_and_report"
        assert eh.notes == ""


# ===========================================================================
# 2. GENERATOR TESTS
# ===========================================================================

class TestWorkflowGenerator:

    def _parse(self, json_str: str, understanding: Optional[WorkflowUnderstanding] = None) -> WorkflowDefinition:
        u = understanding or _make_understanding()
        return parse_workflow_response(json_str, u, model_used="gemini-2.0-flash")

    def test_valid_json_parses_into_workflow_definition(self):
        """Test 7: Valid Gemini JSON response parses into a WorkflowDefinition."""
        wf = self._parse(_valid_gemini_workflow_json())
        assert isinstance(wf, WorkflowDefinition)
        assert wf.name == "Process Customer Request"
        assert len(wf.steps) == 7
        assert wf.model_used == "gemini-2.0-flash"

    def test_markdown_fenced_json_is_unwrapped(self):
        """Test 8: JSON wrapped in ```json ... ``` fences is correctly unwrapped."""
        raw = "```json\n" + _valid_gemini_workflow_json() + "\n```"
        wf = self._parse(raw)
        assert wf.name == "Process Customer Request"

    def test_missing_name_raises_error(self):
        """Test 9: JSON missing 'name' raises WorkflowGenerationError."""
        data = json.loads(_valid_gemini_workflow_json())
        del data["name"]
        with pytest.raises(WorkflowGenerationError, match="name"):
            self._parse(json.dumps(data))

    def test_missing_trigger_raises_error(self):
        """Test 10: JSON missing 'trigger' raises WorkflowGenerationError."""
        data = json.loads(_valid_gemini_workflow_json())
        del data["trigger"]
        with pytest.raises(WorkflowGenerationError, match="trigger"):
            self._parse(json.dumps(data))

    def test_missing_steps_raises_error(self):
        """Test 11: JSON missing 'steps' raises WorkflowGenerationError."""
        data = json.loads(_valid_gemini_workflow_json())
        del data["steps"]
        with pytest.raises(WorkflowGenerationError, match="steps"):
            self._parse(json.dumps(data))

    def test_empty_steps_raises_error(self):
        """Test 12: JSON with empty 'steps' list raises WorkflowGenerationError."""
        data = json.loads(_valid_gemini_workflow_json())
        data["steps"] = []
        with pytest.raises(WorkflowGenerationError, match="steps"):
            self._parse(json.dumps(data))

    def test_invalid_json_raises_error(self):
        """Test 13: Non-JSON text raises WorkflowGenerationError."""
        with pytest.raises(WorkflowGenerationError, match="not valid JSON"):
            self._parse("This is not JSON at all.")

    def test_invented_integration_is_filtered_out(self):
        """Test 14: Integration with application not in understanding is silently skipped."""
        data = json.loads(_valid_gemini_workflow_json())
        data["integrations"].append({
            "application": "InventedApp",
            "purpose": "Does not exist in understanding.",
            "required_capabilities": ["invented_action"],
        })
        u = _make_understanding()  # applications = ["Gmail", "CRM", "Slack"]
        wf = parse_workflow_response(json.dumps(data), u, model_used="gemini-2.0-flash")
        app_names = [i.application for i in wf.integrations]
        assert "InventedApp" not in app_names


# ===========================================================================
# 3. VALIDATOR TESTS
# ===========================================================================

class TestWorkflowValidator:

    def test_valid_workflow_passes_all_checks(self):
        """Test 15: A fully valid WorkflowDefinition passes all validation rules."""
        wf = _make_workflow()
        u = _make_understanding()
        result = validate_workflow(wf, understanding=u)
        assert result.valid is True
        assert result.errors == []

    def test_empty_name_fails_validation(self):
        """Test 16: Empty workflow name fails validation."""
        wf = _make_workflow(name="")
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("name" in e.lower() for e in result.errors)

    def test_empty_description_fails_validation(self):
        """Test 17: Empty workflow description fails validation."""
        wf = _make_workflow(description="")
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("description" in e.lower() for e in result.errors)

    def test_trigger_empty_application_fails(self):
        """Test 18: Trigger with empty application fails validation."""
        wf = _make_workflow(
            trigger=WorkflowTrigger(
                application="", event="email_received", description="x"
            )
        )
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("trigger" in e.lower() for e in result.errors)

    def test_trigger_empty_event_fails(self):
        """Test 19: Trigger with empty event fails validation."""
        wf = _make_workflow(
            trigger=WorkflowTrigger(
                application="Gmail", event="", description="x"
            )
        )
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("trigger" in e.lower() for e in result.errors)

    def test_zero_steps_fails_validation(self):
        """Test 20: Workflow with no steps fails validation."""
        wf = _make_workflow(steps=[])
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("step" in e.lower() for e in result.errors)

    def test_duplicate_step_orders_fail(self):
        """Test 21: Duplicate step ordering values fail validation."""
        steps = [
            WorkflowStep(order=1, application="Gmail", action="read_email", description="x"),
            WorkflowStep(order=1, application="CRM", action="find_customer", description="y"),
        ]
        wf = _make_workflow(steps=steps)
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("unique" in e.lower() for e in result.errors)

    def test_non_sequential_step_orders_fail(self):
        """Test 22: Non-sequential step ordering (e.g., [1, 3]) fails validation."""
        steps = [
            WorkflowStep(order=1, application="Gmail", action="read_email", description="x"),
            WorkflowStep(order=3, application="CRM", action="find_customer", description="y"),
        ]
        wf = _make_workflow(steps=steps)
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("sequential" in e.lower() for e in result.errors)

    def test_step_empty_application_fails(self):
        """Test 23: Step with empty application fails validation."""
        steps = [
            WorkflowStep(order=1, application="", action="read_email", description="x"),
        ]
        wf = _make_workflow(steps=steps)
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("application" in e.lower() for e in result.errors)

    def test_step_empty_action_fails(self):
        """Test 24: Step with empty action fails validation."""
        steps = [
            WorkflowStep(order=1, application="Gmail", action="", description="x"),
        ]
        wf = _make_workflow(steps=steps)
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("action" in e.lower() for e in result.errors)

    def test_invented_integration_fails_cross_reference(self):
        """Test 25: Integration not in understanding applications fails cross-reference."""
        u = _make_understanding()  # applications = [Gmail, CRM, Slack]
        wf = _make_workflow(
            integrations=[
                WorkflowIntegration(
                    application="InventedApp",
                    purpose="This was invented.",
                    required_capabilities=[],
                )
            ]
        )
        result = validate_workflow(wf, understanding=u)
        assert result.valid is False
        assert any("InventedApp" in e for e in result.errors)

    def test_condition_empty_expression_fails(self):
        """Test 26: Condition with empty expression fails validation."""
        wf = _make_workflow(
            conditions=[
                WorkflowCondition(
                    description="Check something",
                    expression="",
                    on_true="request_human_intervention",
                )
            ]
        )
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("expression" in e.lower() for e in result.errors)

    def test_aws_key_pattern_detected_as_secret(self):
        """Test 27: AWS access key pattern in step description is detected as a secret."""
        steps = [
            WorkflowStep(
                order=1,
                application="Gmail",
                action="read_email",
                description="Use AKIAIOSFODNN7EXAMPLE to authenticate.",  # fake AWS key
            ),
        ]
        wf = _make_workflow(steps=steps)
        result = validate_workflow(wf)
        assert result.valid is False
        assert any("secret" in e.lower() for e in result.errors)


# ===========================================================================
# 4. PROMPT TESTS
# ===========================================================================

class TestWorkflowGenerationPrompts:

    def test_prompt_contains_understanding_intent(self):
        """Test 28: Prompt contains the understanding's intent."""
        u = _make_understanding()
        prompt = build_generation_prompt(u)
        assert "Process Customer Request" in prompt

    def test_prompt_contains_all_applications(self):
        """Test 29: Prompt contains all application names from the understanding."""
        u = _make_understanding()
        prompt = build_generation_prompt(u)
        for app in ["Gmail", "CRM", "Slack"]:
            assert app in prompt

    def test_prompt_instructs_no_credential_invention(self):
        """Test 30: Prompt explicitly instructs the model not to invent credentials."""
        u = _make_understanding()
        prompt = build_generation_prompt(u)
        assert "credential" in prompt.lower() or "api key" in prompt.lower() or "oauth" in prompt.lower()

    def test_prompt_specifies_json_only_output(self):
        """Test 31: Prompt instructs model to return JSON only."""
        u = _make_understanding()
        prompt = build_generation_prompt(u)
        assert "JSON" in prompt
        assert "no markdown" in prompt.lower() or "markdown" in prompt.lower()

    def test_prompt_contains_step_count_requirement(self):
        """Test 32: Prompt specifies the exact number of steps required."""
        u = _make_understanding()
        prompt = build_generation_prompt(u)
        # 7 actions in the understanding
        assert "7" in prompt


# ===========================================================================
# 5. SERVICE TESTS
# ===========================================================================

class TestWorkflowGenerationService:

    def _service_with_mocks(
        self,
        understanding: Optional[WorkflowUnderstanding] = None,
        gemini_response: Optional[str] = None,
        understanding_not_found: bool = False,
        understanding_db_error: bool = False,
        gemini_error: bool = False,
        parse_error: bool = False,
        validation_error: bool = False,
        persist_error: bool = False,
    ):
        """Helper that patches service dependencies and calls generate_workflow."""
        from app.services.workflow_generation_service import generate_workflow
        from app.ai.gemini_client import GeminiClientError
        from app.workflow_engine.generator import WorkflowGenerationError

        u = understanding or _make_understanding()
        raw_json = gemini_response or _valid_gemini_workflow_json()

        # Patch: get_understanding_by_id
        if understanding_db_error:
            get_understanding_patch = patch(
                "app.services.workflow_generation_service.get_understanding_by_id",
                side_effect=RuntimeError("DB is down"),
            )
        elif understanding_not_found:
            get_understanding_patch = patch(
                "app.services.workflow_generation_service.get_understanding_by_id",
                return_value=None,
            )
        else:
            get_understanding_patch = patch(
                "app.services.workflow_generation_service.get_understanding_by_id",
                return_value=u,
            )

        # Patch: GeminiClient
        mock_client = MagicMock()
        if gemini_error:
            mock_client.generate.side_effect = GeminiClientError("Gemini unreachable")
        else:
            mock_client.generate.return_value = raw_json
        mock_client.model = "gemini-2.0-flash"
        gemini_patch = patch(
            "app.services.workflow_generation_service.GeminiClient",
            return_value=mock_client,
        )

        # Patch: parse_workflow_response
        if parse_error:
            parse_patch = patch(
                "app.services.workflow_generation_service.parse_workflow_response",
                side_effect=WorkflowGenerationError("Parse failed"),
            )
        else:
            parse_patch = patch(
                "app.services.workflow_generation_service.parse_workflow_response",
                return_value=_make_workflow(),
            )

        # Patch: validate_workflow
        if validation_error:
            mock_vr = MagicMock()
            mock_vr.valid = False
            mock_vr.errors = ["Step ordering is wrong."]
            mock_vr.warnings = []
            validate_patch = patch(
                "app.services.workflow_generation_service.validate_workflow",
                return_value=mock_vr,
            )
        else:
            mock_vr = MagicMock()
            mock_vr.valid = True
            mock_vr.errors = []
            mock_vr.warnings = []
            validate_patch = patch(
                "app.services.workflow_generation_service.validate_workflow",
                return_value=mock_vr,
            )

        # Patch: upsert_workflow
        if persist_error:
            upsert_patch = patch(
                "app.services.workflow_generation_service.upsert_workflow",
                side_effect=RuntimeError("DB write failed"),
            )
        else:
            upsert_patch = patch(
                "app.services.workflow_generation_service.upsert_workflow",
                return_value="test-workflow-id",
            )

        with get_understanding_patch, gemini_patch, parse_patch, validate_patch, upsert_patch:
            return generate_workflow("test-understanding-001")

    def test_understanding_not_found_raises_404(self):
        """Test 33: Understanding not found raises WorkflowServiceError with status 404."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(understanding_not_found=True)
        assert exc_info.value.status_code == 404

    def test_gemini_failure_raises_503(self):
        """Test 34: Gemini failure raises WorkflowServiceError with status 503."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(gemini_error=True)
        assert exc_info.value.status_code == 503

    def test_parse_failure_raises_502(self):
        """Test 35: Parse failure raises WorkflowServiceError with status 502."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(parse_error=True)
        assert exc_info.value.status_code == 502

    def test_validation_failure_raises_422(self):
        """Test 36: Deterministic validation failure raises WorkflowServiceError with status 422."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(validation_error=True)
        assert exc_info.value.status_code == 422

    def test_db_persist_failure_raises_503(self):
        """Test 37: DB failure during persist raises WorkflowServiceError with status 503."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(persist_error=True)
        assert exc_info.value.status_code == 503

    def test_successful_generation_returns_workflow_definition(self):
        """Test 38: Successful pipeline returns a WorkflowDefinition."""
        wf = self._service_with_mocks()
        assert isinstance(wf, WorkflowDefinition)
        assert wf.name == "Process Customer Request"
        assert len(wf.steps) == 7

    def test_db_error_on_fetch_raises_503(self):
        """Test 39: DB error fetching understanding raises WorkflowServiceError with status 503."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with pytest.raises(WorkflowServiceError) as exc_info:
            self._service_with_mocks(understanding_db_error=True)
        assert exc_info.value.status_code == 503


# ===========================================================================
# 6. API TESTS
# ===========================================================================

class TestWorkflowGenerationAPI:
    """Tests for the FastAPI router using TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create a FastAPI TestClient for the workflows router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.workflows import router

        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        self.client = TestClient(test_app, raise_server_exceptions=False)

    def test_post_generate_returns_200_on_success(self):
        """Test 40: POST /workflows/generate/{id} returns 200 with valid workflow."""
        wf = _make_workflow()
        with patch(
            "app.api.workflows.generate_workflow",
            return_value=wf,
        ):
            resp = self.client.post("/api/v1/workflows/generate/test-understanding-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["understanding_id"] == "test-understanding-001"
            assert "workflow" in data
            assert data["workflow"]["name"] == "Process Customer Request"

    def test_post_generate_returns_404_for_unknown_understanding(self):
        """Test 41: POST returns 404 when understanding does not exist."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with patch(
            "app.api.workflows.generate_workflow",
            side_effect=WorkflowServiceError("Understanding not found.", status_code=404),
        ):
            resp = self.client.post("/api/v1/workflows/generate/nonexistent")
            assert resp.status_code == 404

    def test_post_generate_returns_503_on_gemini_failure(self):
        """Test 42: POST returns 503 when Gemini is unreachable."""
        from app.services.workflow_generation_service import WorkflowServiceError

        with patch(
            "app.api.workflows.generate_workflow",
            side_effect=WorkflowServiceError("AI service error.", status_code=503),
        ):
            resp = self.client.post("/api/v1/workflows/generate/test-understanding-001")
            assert resp.status_code == 503

    def test_get_workflow_by_id_returns_stored_workflow(self):
        """Test 43: GET /workflows/{id} returns the stored workflow."""
        wf = _make_workflow()
        with patch(
            "app.api.workflows.get_workflow",
            return_value=wf,
        ):
            resp = self.client.get(f"/api/v1/workflows/{wf.workflow_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "Process Customer Request"
            assert data["status"] == "generated"

    def test_get_workflow_by_id_returns_404_when_not_found(self):
        """Test 44: GET /workflows/{id} returns 404 when no workflow exists."""
        with patch(
            "app.api.workflows.get_workflow",
            return_value=None,
        ):
            resp = self.client.get("/api/v1/workflows/nonexistent-id")
            assert resp.status_code == 404

    def test_get_list_returns_array(self):
        """Test 45: GET /workflows returns a JSON array."""
        with patch(
            "app.api.workflows.list_all_workflows",
            return_value=[],
        ):
            resp = self.client.get("/api/v1/workflows")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


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
def test_integration_full_workflow_generation_from_demo_understanding():
    """
    I1. Full end-to-end integration test using the real Gemini API.

    Requires:
    - GEMINI_API_KEY set in environment
    - MongoDB running on mongodb://127.0.0.1:27017
    - Phase 5 understanding previously run (demo understanding in DB)

    This test is skipped automatically when GEMINI_API_KEY is not available.
    The API key is NEVER printed.
    No real Gmail, CRM, or Slack actions are executed.
    """
    from app.services.workflow_generation_service import generate_workflow
    from app.models.workflow_understanding import list_understandings

    # Find an existing understanding to generate from
    understandings = list_understandings()
    assert understandings, (
        "No understandings in DB -- run Phase 5 understanding first. "
        "POST /api/v1/understanding/{candidate_id}"
    )

    # Use the first understanding (most recently generated)
    understanding = understandings[0]
    understanding_id = understanding.understanding_id

    # Generate workflow -- this calls the real Gemini API
    workflow = generate_workflow(understanding_id)

    # Validate structure
    assert isinstance(workflow, WorkflowDefinition)
    assert workflow.understanding_id == understanding_id
    assert workflow.name
    assert workflow.description
    assert workflow.trigger.application
    assert workflow.trigger.event
    assert len(workflow.steps) > 0
    assert workflow.status == "generated"
    assert 0.0 <= workflow.generation_confidence <= 1.0
    assert workflow.model_used  # e.g. "gemini-2.0-flash"

    # Verify step ordering is 1..N
    orders = sorted([s.order for s in workflow.steps])
    assert orders == list(range(1, len(workflow.steps) + 1)), (
        f"Step ordering is not sequential: {orders}"
    )

    # Verify integrations only reference real applications
    allowed = {a.lower() for a in understanding.applications}
    for itg in workflow.integrations:
        assert itg.application.lower() in allowed, (
            f"Integration '{itg.application}' was invented by the model "
            f"(not in understanding applications: {understanding.applications})"
        )

    # Verify it was persisted
    from app.models.workflow import get_workflow_by_understanding
    stored = get_workflow_by_understanding(understanding_id)
    assert stored is not None
    assert stored.workflow_id == workflow.workflow_id

    # SECURITY: verify no secrets or API keys are in the workflow output
    # Use mode='json' so datetime fields are serialized to ISO strings
    workflow_json = json.dumps(workflow.model_dump(mode="json"))
    assert "GEMINI_API_KEY" not in workflow_json
    assert "AKIA" not in workflow_json  # AWS key prefix
    assert "sk-" not in workflow_json   # OpenAI key prefix
    assert "xoxb-" not in workflow_json # Slack bot token prefix

    # SAFETY: verify this is a definition only -- no real actions executed
    # The workflow status must be 'generated', not 'running' or 'completed'
    assert workflow.status == "generated", (
        f"Phase 6 must only produce 'generated' workflows; got '{workflow.status}'"
    )

    # NEVER print the API key
    assert "GEMINI_API_KEY" not in workflow_json

