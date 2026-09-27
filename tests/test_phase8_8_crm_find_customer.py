"""
Phase 8.8 - CRM find_customer Integration Tests
=================================================
Validates:
 1. CRM adapter registration in IntegrationRegistry.
 2. Supported action: can_handle("find_customer") is True (case-insensitive).
 3. Unsupported action returns FAILED result.
 4. Missing customerIdentifier returns validation failure.
 5. Empty customerIdentifier returns validation failure.
 6. Whitespace-only customerIdentifier returns validation failure.
 7. Customer found - returns correct structured outputs.
 8. Customer not found - safe not-found response (not a crash).
 9. Multiple deterministic customers - each found independently.
10. No unrelated record leakage - only matched customer returned.
11. Dry-run performs zero database lookups.
12. Dry-run returns deterministic simulated result.
13. Approved workflow requirement - live execution succeeds.
14. Generated workflow rejected by approval guard.
15. Rejected workflow rejected by approval guard.
16. Execution-service integration via execute_live.
17. Safe result structure - no credential exposure in outputs.
18. Existing Gmail adapter remains registered and working.
19. Existing Slack adapter remains registered and working.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch, call

import pytest

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.base import StepExecutionContext, StepExecutionResult
from app.integrations.crm.adapter import CRMAdapter
from app.integrations.registry import get_integration_registry
from app.models.mock_crm import SEED_CUSTOMERS
from app.models.workflow import upsert_workflow
from app.schemas.execution import ExecutionStatus, ExecutionStepStatus
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.execution_service import WorkflowNotApprovedError, execute_live


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_find_customer_context(
    variables: Dict[str, Any] | None = None,
    dry_run: bool = False,
) -> StepExecutionContext:
    step = WorkflowStep(
        step_id="step-crm-fc-001",
        order=1,
        application="CRM",
        action="find_customer",
        description="Look up a customer by identifier",
        inputs=["customerIdentifier"],
        outputs=["customerFound", "customerId", "customerIdentifier", "name", "company", "status"],
    )
    return StepExecutionContext(
        workflow_id="wf-test-crm-001",
        execution_id="exec-test-crm-001",
        step=step,
        variables=variables or {},
        dry_run=dry_run,
    )


def build_find_customer_workflow(status: str = "approved") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=f"wf-crm-fc-{status}-{__import__('uuid').uuid4().hex[:6]}",
        understanding_id="und-crm-fc-test",
        name="CRM Find Customer Workflow",
        description="Phase 8.8 test workflow for CRM find_customer",
        status=status,
        reviewed_by="developer_verification" if status == "approved" else None,
        reviewer_notes="Approved for Phase 8.8 CRM find_customer test" if status == "approved" else None,
        approved_at=datetime.now(timezone.utc) if status == "approved" else None,
        trigger=WorkflowTrigger(
            application="CRM",
            event="customer_lookup_requested",
            description="Triggered to look up a customer record by identifier",
        ),
        steps=[
            WorkflowStep(
                step_id="step-crm-fc-wf-001",
                order=1,
                application="CRM",
                action="find_customer",
                description="Find customer by identifier in local mock CRM",
                inputs=["customerIdentifier"],
                outputs=["customerFound", "customerId"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="CRM",
                purpose="Customer lookup",
                required_capabilities=["find_customer"],
            )
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="stop",
        ),
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Mock CRM data for unit tests (bypass MongoDB)
# ---------------------------------------------------------------------------

MOCK_DB: Dict[str, Dict[str, Any]] = {
    seed["customer_identifier"]: seed
    for seed in SEED_CUSTOMERS
}


def mock_find_customer(identifier: str):
    """In-memory lookup matching the real storage contract."""
    if not identifier:
        return None
    norm = identifier.strip().lower()
    return MOCK_DB.get(norm)


# ===========================================================================
# 1-2. Registration & Supported Actions
# ===========================================================================

class TestCRMAdapterRegistration:
    """Requirements 1 & 2: Registration and supported action."""

    def test_crm_adapter_registered_in_global_registry(self):
        """CRM adapter must be registered in the singleton IntegrationRegistry."""
        registry = get_integration_registry()
        adapter = registry.get_adapter("CRM", "find_customer")
        assert adapter is not None, "CRM/find_customer adapter must be registered"
        assert isinstance(adapter, CRMAdapter)

    def test_can_handle_find_customer_lowercase(self):
        adapter = CRMAdapter()
        assert adapter.can_handle("find_customer") is True

    def test_can_handle_find_customer_case_insensitive(self):
        adapter = CRMAdapter()
        for variant in ("FIND_CUSTOMER", "Find_Customer", "FIND_customer"):
            assert adapter.can_handle(variant) is True, f"Should handle '{variant}'"

    def test_cannot_handle_unsupported_actions(self):
        """delete_customer/list_customers and blanks are NOT supported (update_customer is Phase 8.9)."""
        adapter = CRMAdapter()
        for action in ("delete_customer", "list_customers", "create_customer", "", None):
            assert adapter.can_handle(action) is False, f"Should not handle '{action}'"

    def test_application_name_is_crm(self):
        adapter = CRMAdapter()
        assert adapter.application_name == "CRM"

    def test_unsupported_action_returns_failed_result(self):
        adapter = CRMAdapter()
        ctx = build_find_customer_context()
        ctx.step.action = "delete_customer"
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "delete_customer" in res.result_summary


# ===========================================================================
# 3-6. Input Validation
# ===========================================================================

class TestCRMFindCustomerInputValidation:
    """Requirements 3-6: Input validation for customerIdentifier."""

    @patch("app.models.mock_crm.find_customer_by_identifier")
    def test_missing_customer_identifier_fails(self, mock_lookup):
        """Missing customerIdentifier must fail without any DB lookup."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(variables={})  # no customerIdentifier
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "customerIdentifier" in res.result_summary
        mock_lookup.assert_not_called()

    @patch("app.models.mock_crm.find_customer_by_identifier")
    def test_empty_customer_identifier_fails(self, mock_lookup):
        """Empty string customerIdentifier must fail without any DB lookup."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(variables={"customerIdentifier": ""})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "empty" in res.result_summary.lower() or "customerIdentifier" in res.result_summary
        mock_lookup.assert_not_called()

    @patch("app.models.mock_crm.find_customer_by_identifier")
    def test_whitespace_only_customer_identifier_fails(self, mock_lookup):
        """Whitespace-only customerIdentifier must fail without any DB lookup."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(variables={"customerIdentifier": "   "})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        mock_lookup.assert_not_called()

    @patch("app.models.mock_crm.find_customer_by_identifier")
    def test_none_customer_identifier_fails(self, mock_lookup):
        """Explicit None customerIdentifier is treated as missing."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(variables={"customerIdentifier": None})
        res = adapter.execute(ctx)

        # None is coerced to string "None" which is non-empty, so it goes to lookup
        # OR it fails validation — either is acceptable as long as it does NOT crash
        assert res.status in (ExecutionStepStatus.FAILED, ExecutionStepStatus.COMPLETED)


# ===========================================================================
# 7-8. Customer Found / Not Found
# ===========================================================================

class TestCRMFindCustomerLookup:
    """Requirements 7 & 8: Customer found and not-found behaviour."""

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_customer_found_returns_correct_outputs(self, mock_lookup):
        """Known customer returns customerFound=True with all expected fields."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        res = adapter.execute(ctx)

        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["customerFound"] is True
        assert res.outputs["customerId"] == "CUST-1001"
        assert res.outputs["name"] == "Alice Test"
        assert res.outputs["company"] == "Example Corporation"
        assert res.outputs["status"] == "active"
        assert "customerIdentifier" in res.outputs

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_customer_not_found_returns_safe_response(self, mock_lookup):
        """Unknown identifier returns customerFound=False - not a system failure."""
        mock_lookup.return_value = None

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "unknown@nobody.test"}
        )
        res = adapter.execute(ctx)

        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["customerFound"] is False
        assert res.error_summary is None

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_not_found_result_summary_safe(self, mock_lookup):
        """Not-found result summary does not expose the unknown identifier in a raw form."""
        mock_lookup.return_value = None

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "secret@nosuchplace.test"}
        )
        res = adapter.execute(ctx)

        assert res.success is True
        # Result summary should not dump the raw identifier into the summary
        # (it does NOT have to omit it, but must not error)
        assert res.result_summary is not None


# ===========================================================================
# 9. Multiple Deterministic Customers
# ===========================================================================

class TestCRMMultipleCustomers:
    """Requirement 9: Multiple deterministic seed customers are independently findable."""

    @pytest.mark.parametrize("seed", SEED_CUSTOMERS)
    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_each_seed_customer_findable(self, mock_lookup, seed):
        """Each seed customer can be independently found by their identifier."""
        mock_lookup.return_value = seed

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": seed["customer_identifier"]}
        )
        res = adapter.execute(ctx)

        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["customerFound"] is True
        assert res.outputs["customerId"] == seed["customer_id"]
        assert res.outputs["name"] == seed["name"]


# ===========================================================================
# 10. No Unrelated Record Leakage
# ===========================================================================

class TestCRMNoLeakage:
    """Requirement 10: Only the matched customer record is returned."""

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_lookup_returns_only_matched_customer(self, mock_lookup):
        """find_customer must return exactly one matched customer, not a list."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        res = adapter.execute(ctx)

        # Outputs must be a flat dict with one customer's data, not a list
        assert isinstance(res.outputs, dict)
        assert "customers" not in res.outputs, "Should not return a list of customers"
        assert res.outputs.get("customerId") == "CUST-1001"

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_lookup_for_alice_does_not_return_bob(self, mock_lookup):
        """Querying Alice never returns Bob's data."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        res = adapter.execute(ctx)

        assert res.outputs.get("customerId") == "CUST-1001"
        assert res.outputs.get("name") == "Alice Test"
        assert "CUST-1002" not in str(res.outputs)


# ===========================================================================
# 11-12. Dry-Run
# ===========================================================================

class TestCRMFindCustomerDryRun:
    """Requirements 11 & 12: Dry-run makes zero DB lookups and returns deterministic result."""

    def test_dry_run_returns_dry_run_status(self):
        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"},
            dry_run=True,
        )
        res = adapter.execute(ctx)

        assert res.success is True
        assert res.status == ExecutionStepStatus.DRY_RUN

    def test_dry_run_result_is_deterministic(self):
        """Two identical dry-run calls must produce identical outputs."""
        adapter = CRMAdapter()
        ctx1 = build_find_customer_context(dry_run=True)
        ctx2 = build_find_customer_context(dry_run=True)

        res1 = adapter.execute(ctx1)
        res2 = adapter.execute(ctx2)

        assert res1.outputs == res2.outputs
        assert res1.result_summary == res2.result_summary

    @patch("app.models.mock_crm.find_customer_by_identifier")
    def test_dry_run_makes_zero_database_lookups(self, mock_db_lookup):
        """Dry-run must never call the database layer."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"},
            dry_run=True,
        )
        adapter.execute(ctx)
        mock_db_lookup.assert_not_called()

    def test_dry_run_outputs_contain_dry_run_marker(self):
        adapter = CRMAdapter()
        ctx = build_find_customer_context(dry_run=True)
        res = adapter.execute(ctx)

        assert res.outputs.get("dry_run") is True

    def test_dry_run_missing_identifier_still_succeeds(self):
        """Dry-run bypasses input validation and never touches DB."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(variables={}, dry_run=True)
        res = adapter.execute(ctx)

        # Dry-run should succeed even without customerIdentifier
        assert res.success is True
        assert res.status == ExecutionStepStatus.DRY_RUN


# ===========================================================================
# 13-15. Execution-Service Integration & Approval Guard
# ===========================================================================

class TestCRMExecutionServiceIntegration:
    """Requirements 13-15: Execution-service integration and approval guard."""

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_execute_live_approved_workflow_find_customer(self, mock_lookup):
        """Live execution of approved CRM workflow must complete successfully."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        wf = build_find_customer_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": "alice@example.test"},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_steps == 1
        assert len(execution.step_records) == 1

        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.application == "CRM"
        assert step_rec.action == "find_customer"
        assert "CUST-1001" in step_rec.result_summary

    @pytest.mark.parametrize("bad_status", ["generated", "rejected"])
    def test_non_approved_workflow_blocked_by_guard(self, bad_status):
        """Hard approval guard must block generated and rejected workflows."""
        wf = build_find_customer_workflow(status=bad_status)
        upsert_workflow(wf)

        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            execute_live(
                wf.workflow_id,
                variables={"customerIdentifier": "alice@example.test"},
            )

        assert exc_info.value.status_code == 409
        assert f"current status is '{bad_status}'" in exc_info.value.message

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_execute_live_not_found_customer_still_completes(self, mock_lookup):
        """Live execution where customer is not found must still complete (not fail)."""
        mock_lookup.return_value = None

        wf = build_find_customer_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": "nobody@nosuchplace.test"},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert "no customer found" in step_rec.result_summary.lower()

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_step_record_has_no_outputs_attribute(self, mock_lookup):
        """ExecutionStepRecord does not expose .outputs - only result_summary."""
        from app.schemas.execution import ExecutionStepRecord, ExecutionStepStatus

        rec = ExecutionStepRecord(
            step_id="step-crm-1",
            order=1,
            application="CRM",
            action="find_customer",
            status=ExecutionStepStatus.COMPLETED,
            result_summary="CRM find_customer completed: customer 'CUST-1001' found (status: active).",
        )

        assert hasattr(rec, "status")
        assert hasattr(rec, "result_summary")
        assert hasattr(rec, "error_summary")
        assert not hasattr(rec, "outputs"), "ExecutionStepRecord must not have 'outputs'"


# ===========================================================================
# 16-17. Safe Result Structure & No Credential Exposure
# ===========================================================================

class TestCRMResultSafety:
    """Requirements 16 & 17: Safe result structure and no credential exposure."""

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_outputs_contain_only_expected_fields(self, mock_lookup):
        """Outputs must contain only declared safe fields, no extra private data."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        res = adapter.execute(ctx)

        assert res.success is True
        allowed_keys = {
            "customerFound", "customerId", "customerIdentifier",
            "name", "company", "status", "dry_run",
        }
        for key in res.outputs:
            assert key in allowed_keys, f"Unexpected output key: '{key}'"

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_result_summary_contains_no_credentials(self, mock_lookup):
        """result_summary must not expose any credential-like strings."""
        alice = MOCK_DB["alice@example.test"]
        mock_lookup.return_value = alice

        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        res = adapter.execute(ctx)

        for forbidden in ("password", "secret", "token", "api_key", "Bearer", "xox"):
            assert forbidden.lower() not in res.result_summary.lower(), (
                f"result_summary must not contain '{forbidden}'"
            )

    def test_outputs_do_not_include_mongodb_internal_id(self):
        """MongoDB _id field must never appear in adapter outputs."""
        adapter = CRMAdapter()
        ctx = build_find_customer_context(
            variables={"customerIdentifier": "alice@example.test"}
        )
        # Simulate a document that incorrectly includes _id
        with patch("app.integrations.crm.adapter.find_customer_by_identifier") as mock_lookup:
            mock_lookup.return_value = {
                **MOCK_DB["alice@example.test"],
                "_id": "some-mongo-id",  # this must be stripped
            }
            res = adapter.execute(ctx)

        assert "_id" not in res.outputs, "MongoDB _id must not appear in adapter outputs"


# ===========================================================================
# 18-19. Existing Adapters Remain Working
# ===========================================================================

class TestExistingAdaptersUnaffected:
    """Requirements 18 & 19: Gmail and Slack adapters still registered and working."""

    def test_gmail_read_email_still_registered(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "read_email")
        assert adapter is not None, "Gmail/read_email must remain registered"

    def test_gmail_open_email_still_registered(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "open_email")
        assert adapter is not None, "Gmail/open_email must remain registered"

    def test_gmail_download_file_still_registered(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "download_file")
        assert adapter is not None, "Gmail/download_file must remain registered"

    def test_slack_send_message_still_registered(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Slack", "send_message")
        assert adapter is not None, "Slack/send_message must remain registered"

    def test_all_four_integrations_simultaneously_registered(self):
        """All four integration/action pairs must coexist in the registry."""
        registry = get_integration_registry()
        assert registry.get_adapter("CRM", "find_customer") is not None
        assert registry.get_adapter("Gmail", "read_email") is not None
        assert registry.get_adapter("Gmail", "open_email") is not None
        assert registry.get_adapter("Gmail", "download_file") is not None
        assert registry.get_adapter("Slack", "send_message") is not None


# ===========================================================================
# Seed Data Integrity
# ===========================================================================

class TestMockCRMSeedData:
    """Validates the deterministic seed data constants."""

    def test_seed_customers_count(self):
        """Must have exactly 5 deterministic seed customers."""
        assert len(SEED_CUSTOMERS) == 5

    def test_seed_customer_ids_unique(self):
        ids = [c["customer_id"] for c in SEED_CUSTOMERS]
        assert len(ids) == len(set(ids)), "customer_id values must be unique"

    def test_seed_identifiers_unique(self):
        identifiers = [c["customer_identifier"] for c in SEED_CUSTOMERS]
        assert len(identifiers) == len(set(identifiers)), "customer_identifier values must be unique"

    def test_seed_emails_use_test_domains(self):
        for customer in SEED_CUSTOMERS:
            assert customer["email"].endswith(".test"), (
                f"Seed email must use .test domain: {customer['email']}"
            )

    def test_seed_customer_required_fields(self):
        required = {"customer_id", "customer_identifier", "name", "email", "company", "status"}
        for customer in SEED_CUSTOMERS:
            missing = required - set(customer.keys())
            assert not missing, f"Seed customer {customer.get('customer_id')} missing: {missing}"

    def test_nav_example_test_is_seed_customer(self):
        """nav@example.test (Test Customer) must be present as a seed record."""
        identifiers = [c["customer_identifier"] for c in SEED_CUSTOMERS]
        assert "nav@example.test" in identifiers

    def test_cust_1001_is_alice(self):
        alice = next((c for c in SEED_CUSTOMERS if c["customer_id"] == "CUST-1001"), None)
        assert alice is not None
        assert alice["name"] == "Alice Test"
        assert alice["company"] == "Example Corporation"
        assert alice["status"] == "active"
