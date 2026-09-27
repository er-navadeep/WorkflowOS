"""
Phase 8.9 - CRM update_customer Integration Tests
==================================================
Tests (24 total):
 1.  CRM update_customer registration in IntegrationRegistry
 2.  Supported action (case-insensitive)
 3.  Unsupported actions still rejected
 4.  Missing customerIdentifier -> FAILED
 5.  Empty customerIdentifier -> FAILED
 6.  Whitespace-only customerIdentifier -> FAILED
 7.  Missing updates -> FAILED
 8.  Empty updates dict -> FAILED
 9.  Non-dict updates -> FAILED
10.  Known customer update (status) -> COMPLETED, updated=True
11.  Known customer update (notes) -> COMPLETED, updated=True
12.  Multiple allowed fields (status + notes) -> COMPLETED
13.  Unknown field in updates -> FAILED
14.  MongoDB $set operator injection in key -> FAILED
15.  MongoDB $where operator injection in value -> FAILED
16.  Invalid status value -> FAILED
17.  Notes too long -> FAILED
18.  Unknown customer -> COMPLETED, customerFound=False
19.  Dry-run: zero database writes
20.  Dry-run: deterministic result with database_write=False
21.  Approved workflow required (live execution succeeds)
22.  Generated workflow rejected by approval guard
23.  Rejected workflow rejected by approval guard
24.  Output structure safety (no credentials, no _id, no unrelated records)
25.  find_customer still works (regression)
26.  Gmail integration still registered (regression)
27.  Slack integration still registered (regression)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.base import StepExecutionContext, StepExecutionResult
from app.integrations.crm.adapter import CRMAdapter
from app.integrations.registry import get_integration_registry
from app.models.mock_crm import (
    ALLOWED_UPDATE_FIELDS,
    ALLOWED_STATUS_VALUES,
    MAX_NOTES_LENGTH,
    SEED_CUSTOMERS,
)
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

def build_update_customer_context(
    variables: Dict[str, Any] | None = None,
    dry_run: bool = False,
) -> StepExecutionContext:
    step = WorkflowStep(
        step_id="step-crm-uc-001",
        order=1,
        application="CRM",
        action="update_customer",
        description="Update customer fields in local mock CRM",
        inputs=["customerIdentifier", "updates"],
        outputs=["customerFound", "updated", "customerId", "updatedFields", "customer"],
    )
    return StepExecutionContext(
        workflow_id="wf-test-crm-uc-001",
        execution_id="exec-test-crm-uc-001",
        step=step,
        variables=variables or {},
        dry_run=dry_run,
    )


def build_update_customer_workflow(status: str = "approved") -> WorkflowDefinition:
    import uuid
    return WorkflowDefinition(
        workflow_id=f"wf-crm-uc-{status}-{uuid.uuid4().hex[:6]}",
        understanding_id="und-crm-uc-test",
        name="CRM Update Customer Workflow",
        description="Phase 8.9 test workflow for CRM update_customer",
        status=status,
        reviewed_by="developer_verification" if status == "approved" else None,
        reviewer_notes="Approved for Phase 8.9 CRM update_customer test" if status == "approved" else None,
        approved_at=datetime.now(timezone.utc) if status == "approved" else None,
        trigger=WorkflowTrigger(
            application="CRM",
            event="customer_update_requested",
            description="Triggered to update a customer record",
        ),
        steps=[
            WorkflowStep(
                step_id=f"step-crm-uc-wf-{uuid.uuid4().hex[:6]}",
                order=1,
                application="CRM",
                action="update_customer",
                description="Update customer by identifier in local mock CRM",
                inputs=["customerIdentifier", "updates"],
                outputs=["customerFound", "updated", "customerId"],
                on_failure="stop",
            )
        ],
        integrations=[
            WorkflowIntegration(
                application="CRM",
                purpose="Customer update",
                required_capabilities=["update_customer"],
            )
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="stop",
        ),
        created_at=datetime.now(timezone.utc),
    )


# Synthetic seed doc used for unit tests (no real DB)
ALICE_DOC = {
    "customer_id": "CUST-1001",
    "customer_identifier": "alice@example.test",
    "name": "Alice Test",
    "email": "alice@example.test",
    "company": "Example Corporation",
    "status": "contacted",
    "notes": "Updated by test",
}


# ===========================================================================
# 1-3. Registration & Supported Actions
# ===========================================================================

class TestUpdateCustomerRegistration:

    def test_update_customer_registered_in_global_registry(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("CRM", "update_customer")
        assert adapter is not None
        assert isinstance(adapter, CRMAdapter)

    def test_can_handle_update_customer_lowercase(self):
        assert CRMAdapter().can_handle("update_customer") is True

    def test_can_handle_update_customer_case_insensitive(self):
        for variant in ("UPDATE_CUSTOMER", "Update_Customer", "UPDATE_customer"):
            assert CRMAdapter().can_handle(variant) is True

    def test_find_customer_still_registered(self):
        registry = get_integration_registry()
        assert registry.get_adapter("CRM", "find_customer") is not None

    def test_unsupported_actions_rejected(self):
        for action in ("delete_customer", "create_customer", "", None):
            assert CRMAdapter().can_handle(action) is False

    def test_unsupported_action_returns_failed_result(self):
        adapter = CRMAdapter()
        ctx = build_update_customer_context()
        ctx.step.action = "delete_customer"
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED


# ===========================================================================
# 4-9. Input Validation
# ===========================================================================

class TestUpdateCustomerInputValidation:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_missing_identifier_fails_without_db_call(self, mock_upd):
        res = CRMAdapter().execute(build_update_customer_context({}))
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "customerIdentifier" in res.result_summary
        mock_upd.assert_not_called()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_empty_identifier_fails(self, mock_upd):
        res = CRMAdapter().execute(
            build_update_customer_context({"customerIdentifier": "", "updates": {"status": "active"}})
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        mock_upd.assert_not_called()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_whitespace_identifier_fails(self, mock_upd):
        res = CRMAdapter().execute(
            build_update_customer_context({"customerIdentifier": "   ", "updates": {"status": "active"}})
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        mock_upd.assert_not_called()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_missing_updates_fails(self, mock_upd):
        res = CRMAdapter().execute(
            build_update_customer_context({"customerIdentifier": "alice@example.test"})
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "updates" in res.result_summary
        mock_upd.assert_not_called()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_empty_updates_fails(self, mock_upd):
        res = CRMAdapter().execute(
            build_update_customer_context({"customerIdentifier": "alice@example.test", "updates": {}})
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "empty" in res.result_summary.lower()
        mock_upd.assert_not_called()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_non_dict_updates_fails(self, mock_upd):
        for bad in ("status", ["status"], 42, True):
            res = CRMAdapter().execute(
                build_update_customer_context({"customerIdentifier": "alice@example.test", "updates": bad})
            )
            assert res.success is False, f"Should fail for updates={bad!r}"
            assert res.status == ExecutionStepStatus.FAILED
            mock_upd.assert_not_called()


# ===========================================================================
# 10-12. Known Customer Updates (mocked storage)
# ===========================================================================

class TestUpdateCustomerKnownCustomer:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_status_update_succeeds(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "status": "contacted"}
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "contacted"},
            })
        )
        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["customerFound"] is True
        assert res.outputs["updated"] is True
        assert res.outputs["customerId"] == "CUST-1001"
        assert "status" in res.outputs["updatedFields"]

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_notes_update_succeeds(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "notes": "Test note"}
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"notes": "Test note"},
            })
        )
        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["updated"] is True
        assert "notes" in res.outputs["updatedFields"]

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_multiple_fields_update_succeeds(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "status": "processed", "notes": "multi-field"}
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "processed", "notes": "multi-field"},
            })
        )
        assert res.success is True
        assert res.outputs["updated"] is True
        assert set(res.outputs["updatedFields"]) == {"status", "notes"}

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_result_summary_contains_customer_id(self, mock_upd):
        mock_upd.return_value = ALICE_DOC
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "active"},
            })
        )
        assert "CUST-1001" in res.result_summary

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_customer_snapshot_in_outputs(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "status": "contacted", "notes": "hi"}
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "contacted"},
            })
        )
        assert "customer" in res.outputs
        snap = res.outputs["customer"]
        assert snap["customerId"] == "CUST-1001"
        assert snap["status"] == "contacted"


# ===========================================================================
# 13-17. Validation Rejection (delegated to storage layer)
# ===========================================================================

class TestUpdateCustomerValidationRejection:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_unknown_field_rejected(self, mock_upd):
        mock_upd.side_effect = ValueError("Update contains disallowed field(s): ['company']")
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"company": "Evil Corp"},
            })
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "disallowed" in res.result_summary.lower() or "company" in res.result_summary

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_mongo_set_operator_in_key_rejected(self, mock_upd):
        mock_upd.side_effect = ValueError("MongoDB operator '$set' is not permitted")
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"$set": {"status": "active"}},
            })
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_mongo_where_operator_in_value_rejected(self, mock_upd):
        mock_upd.side_effect = ValueError("MongoDB operator in value for field 'status' is not permitted")
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "$where"},
            })
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_invalid_status_value_rejected(self, mock_upd):
        mock_upd.side_effect = ValueError("Invalid status value 'hacked'")
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "hacked"},
            })
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_notes_too_long_rejected(self, mock_upd):
        mock_upd.side_effect = ValueError(f"'notes' exceeds maximum length of {MAX_NOTES_LENGTH} characters")
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"notes": "x" * (MAX_NOTES_LENGTH + 1)},
            })
        )
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED


# ===========================================================================
# 18. Unknown Customer
# ===========================================================================

class TestUpdateCustomerNotFound:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_unknown_customer_safe_response(self, mock_upd):
        mock_upd.return_value = None
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "ghost@nobody.test",
                "updates": {"status": "active"},
            })
        )
        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["customerFound"] is False
        assert res.outputs["updated"] is False
        assert res.error_summary is None

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_not_found_result_summary_mentions_not_found(self, mock_upd):
        mock_upd.return_value = None
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "ghost@nobody.test",
                "updates": {"status": "active"},
            })
        )
        assert "no customer found" in res.result_summary.lower()


# ===========================================================================
# 19-20. Dry-Run
# ===========================================================================

class TestUpdateCustomerDryRun:

    @patch("app.models.mock_crm.update_customer_by_identifier")
    def test_dry_run_makes_zero_database_writes(self, mock_db_upd):
        res = CRMAdapter().execute(
            build_update_customer_context(
                {"customerIdentifier": "alice@example.test", "updates": {"status": "active"}},
                dry_run=True,
            )
        )
        mock_db_upd.assert_not_called()
        assert res.status == ExecutionStepStatus.DRY_RUN

    def test_dry_run_outputs_database_write_false(self):
        res = CRMAdapter().execute(
            build_update_customer_context(
                {"customerIdentifier": "alice@example.test", "updates": {"status": "contacted"}},
                dry_run=True,
            )
        )
        assert res.outputs.get("database_write") is False

    def test_dry_run_outputs_dry_run_true(self):
        res = CRMAdapter().execute(
            build_update_customer_context(
                {"customerIdentifier": "alice@example.test", "updates": {"status": "active"}},
                dry_run=True,
            )
        )
        assert res.outputs.get("dry_run") is True

    def test_dry_run_shows_which_fields_would_be_updated(self):
        res = CRMAdapter().execute(
            build_update_customer_context(
                {"customerIdentifier": "alice@example.test", "updates": {"status": "active", "notes": "hi"}},
                dry_run=True,
            )
        )
        assert set(res.outputs.get("updatedFields", [])) == {"status", "notes"}

    def test_dry_run_is_deterministic(self):
        ctx1 = build_update_customer_context(
            {"customerIdentifier": "alice@example.test", "updates": {"status": "active"}},
            dry_run=True,
        )
        ctx2 = build_update_customer_context(
            {"customerIdentifier": "alice@example.test", "updates": {"status": "active"}},
            dry_run=True,
        )
        r1 = CRMAdapter().execute(ctx1)
        r2 = CRMAdapter().execute(ctx2)
        assert r1.outputs == r2.outputs

    @patch("app.models.mock_crm.update_customer_by_identifier")
    def test_dry_run_missing_updates_still_checked_before_dry_run(self, mock_db_upd):
        """Dry-run should NOT bypass input validation for customerIdentifier."""
        res = CRMAdapter().execute(
            build_update_customer_context(
                {},  # no customerIdentifier
                dry_run=True,
            )
        )
        # Missing customerIdentifier must fail even in dry-run
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        mock_db_upd.assert_not_called()


# ===========================================================================
# 21-23. Execution-Service Integration & Approval Guard
# ===========================================================================

class TestUpdateCustomerExecutionService:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_execute_live_approved_workflow(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "status": "contacted"}
        wf = build_update_customer_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": "alice@example.test", "updates": {"status": "contacted"}},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_steps == 1
        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.application == "CRM"
        assert step_rec.action == "update_customer"

    @pytest.mark.parametrize("bad_status", ["generated", "rejected"])
    def test_non_approved_workflow_blocked(self, bad_status):
        wf = build_update_customer_workflow(status=bad_status)
        upsert_workflow(wf)

        with pytest.raises(WorkflowNotApprovedError) as exc_info:
            execute_live(
                wf.workflow_id,
                variables={"customerIdentifier": "alice@example.test", "updates": {"status": "active"}},
            )
        assert exc_info.value.status_code == 409

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_not_found_customer_still_completes_execution(self, mock_upd):
        mock_upd.return_value = None
        wf = build_update_customer_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"customerIdentifier": "nobody@nope.test", "updates": {"status": "active"}},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert "no customer found" in step_rec.result_summary.lower()


# ===========================================================================
# 24. Output Structure Safety
# ===========================================================================

class TestUpdateCustomerOutputSafety:

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_outputs_contain_no_credentials(self, mock_upd):
        mock_upd.return_value = ALICE_DOC
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "active"},
            })
        )
        for forbidden in ("password", "secret", "token", "api_key", "Bearer"):
            assert forbidden.lower() not in str(res.outputs).lower()

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_outputs_contain_no_mongodb_id(self, mock_upd):
        mock_upd.return_value = {**ALICE_DOC, "_id": "mongo-object-id"}
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "active"},
            })
        )
        assert "_id" not in res.outputs
        assert "_id" not in res.outputs.get("customer", {})

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_outputs_are_single_customer_not_list(self, mock_upd):
        mock_upd.return_value = ALICE_DOC
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "active"},
            })
        )
        assert isinstance(res.outputs, dict)
        assert "customers" not in res.outputs

    @patch("app.integrations.crm.adapter.update_customer_by_identifier")
    def test_error_summary_is_none_on_success(self, mock_upd):
        mock_upd.return_value = ALICE_DOC
        res = CRMAdapter().execute(
            build_update_customer_context({
                "customerIdentifier": "alice@example.test",
                "updates": {"status": "active"},
            })
        )
        assert res.error_summary is None


# ===========================================================================
# Storage Layer Unit Tests (no DB required — mock_crm.py logic)
# ===========================================================================

class TestStorageLayerAllowlist:
    """Directly tests update_customer_by_identifier validation logic."""

    def test_allowed_fields_constant_has_status_and_notes(self):
        assert "status" in ALLOWED_UPDATE_FIELDS
        assert "notes" in ALLOWED_UPDATE_FIELDS

    def test_allowed_status_values_populated(self):
        assert len(ALLOWED_STATUS_VALUES) >= 4
        for v in ("active", "inactive", "contacted", "processed"):
            assert v in ALLOWED_STATUS_VALUES

    def test_max_notes_length_is_positive(self):
        assert MAX_NOTES_LENGTH > 0

    @patch("app.models.mock_crm._get_collection")
    def test_empty_identifier_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="non-empty"):
            update_customer_by_identifier("", {"status": "active"})

    @patch("app.models.mock_crm._get_collection")
    def test_empty_updates_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="non-empty"):
            update_customer_by_identifier("alice@example.test", {})

    @patch("app.models.mock_crm._get_collection")
    def test_mongo_operator_key_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="MongoDB operator"):
            update_customer_by_identifier("alice@example.test", {"$set": {"status": "active"}})

    @patch("app.models.mock_crm._get_collection")
    def test_mongo_operator_value_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="MongoDB operator"):
            update_customer_by_identifier("alice@example.test", {"status": "$where: '1==1'"})

    @patch("app.models.mock_crm._get_collection")
    def test_unknown_field_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="disallowed"):
            update_customer_by_identifier("alice@example.test", {"company": "Evil Corp"})

    @patch("app.models.mock_crm._get_collection")
    def test_invalid_status_value_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="Invalid status value"):
            update_customer_by_identifier("alice@example.test", {"status": "hacked"})

    @patch("app.models.mock_crm._get_collection")
    def test_notes_too_long_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="exceeds maximum length"):
            update_customer_by_identifier("alice@example.test", {"notes": "x" * (MAX_NOTES_LENGTH + 1)})

    @patch("app.models.mock_crm._get_collection")
    def test_notes_must_be_string_raises_value_error(self, _):
        from app.models.mock_crm import update_customer_by_identifier
        with pytest.raises(ValueError, match="must be a string"):
            update_customer_by_identifier("alice@example.test", {"notes": 12345})


# ===========================================================================
# 25-27. Regression: Existing Integrations Unaffected
# ===========================================================================

class TestRegressionExistingIntegrations:

    def test_crm_find_customer_still_registered(self):
        registry = get_integration_registry()
        assert registry.get_adapter("CRM", "find_customer") is not None

    def test_gmail_read_email_still_registered(self):
        assert get_integration_registry().get_adapter("Gmail", "read_email") is not None

    def test_gmail_open_email_still_registered(self):
        assert get_integration_registry().get_adapter("Gmail", "open_email") is not None

    def test_gmail_download_file_still_registered(self):
        assert get_integration_registry().get_adapter("Gmail", "download_file") is not None

    def test_slack_send_message_still_registered(self):
        assert get_integration_registry().get_adapter("Slack", "send_message") is not None

    def test_all_five_integrations_simultaneously_registered(self):
        registry = get_integration_registry()
        assert registry.get_adapter("CRM", "find_customer") is not None
        assert registry.get_adapter("CRM", "update_customer") is not None
        assert registry.get_adapter("Gmail", "read_email") is not None
        assert registry.get_adapter("Gmail", "open_email") is not None
        assert registry.get_adapter("Gmail", "download_file") is not None
        assert registry.get_adapter("Slack", "send_message") is not None

    @patch("app.integrations.crm.adapter.find_customer_by_identifier")
    def test_find_customer_functional_after_phase_8_9(self, mock_find):
        from app.models.mock_crm import SEED_CUSTOMERS
        alice = next(c for c in SEED_CUSTOMERS if c["customer_id"] == "CUST-1001")
        mock_find.return_value = alice

        adapter = CRMAdapter()
        step = WorkflowStep(
            step_id="step-find",
            order=1,
            application="CRM",
            action="find_customer",
            description="find",
            inputs=["customerIdentifier"],
            outputs=["customerFound"],
        )
        ctx = StepExecutionContext(
            workflow_id="wf-reg",
            execution_id="exec-reg",
            step=step,
            variables={"customerIdentifier": "alice@example.test"},
            dry_run=False,
        )
        res = adapter.execute(ctx)
        assert res.success is True
        assert res.outputs["customerFound"] is True
        assert res.outputs["customerId"] == "CUST-1001"
