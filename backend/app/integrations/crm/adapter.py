"""
CRM Adapter - Phase 8.8 / 8.9
==============================
Executes CRM actions for WorkFlowOS workflows against the local mock CRM.

Supported actions:
    - find_customer:   Look up a customer by customerIdentifier.
    - update_customer: Update allowed fields on an existing customer.

Security & Guardrails:
    - Local mock CRM ONLY - no external CRM (Salesforce, HubSpot, Zoho) connections.
    - No API keys, OAuth tokens, or external credentials required.
    - Zero database access during dry-run simulation.
    - Fails safely on missing/empty customerIdentifier.
    - update_customer uses an explicit field allowlist; raw MongoDB operators
      ($set, $push, $unset, etc.) in workflow input are always rejected.
    - Never exposes unrelated customer records.
    - Audit logs contain only the minimum safe result summary.
    - All synthetic test data uses .test domains.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.integrations.base import (
    BaseIntegrationAdapter,
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.schemas.execution import ExecutionStepStatus
from app.models.mock_crm import (
    find_customer_by_identifier,
    update_customer_by_identifier,
    CRMStorageError,
    ALLOWED_UPDATE_FIELDS,
    ALLOWED_STATUS_VALUES,
    MAX_NOTES_LENGTH,
)

logger = logging.getLogger(__name__)

# Supported actions for this adapter
_SUPPORTED_ACTIONS = frozenset({"find_customer", "update_customer"})


class CRMAdapter(BaseIntegrationAdapter):
    """
    Adapter for integrating WorkFlowOS with the local mock CRM.

    Phase 8.8: find_customer
    Phase 8.9: update_customer

    Does NOT connect to any external CRM system.
    """

    @property
    def application_name(self) -> str:
        return "CRM"

    def can_handle(self, action: str) -> bool:
        """Return True if this adapter supports the given action."""
        if not action or not isinstance(action, str):
            return False
        return action.strip().lower() in _SUPPORTED_ACTIONS

    def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute the CRM action for the given workflow step context.

        Dispatches to the appropriate action handler based on step.action.
        """
        action = context.step.action.strip().lower() if context.step.action else ""

        if not self.can_handle(action):
            error_msg = f"Unsupported action '{context.step.action}' for CRM adapter."
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=f"CRM adapter does not support action '{context.step.action}'.",
                error_summary=sanitize_text(error_msg),
            )

        if action == "find_customer":
            return self._find_customer(context)

        if action == "update_customer":
            return self._update_customer(context)

        # Fallthrough — should not be reachable given can_handle check above
        return StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary=f"CRM action '{action}' routing error.",
            error_summary="Internal routing error in CRM adapter.",
        )

    # -----------------------------------------------------------------------
    # find_customer
    # -----------------------------------------------------------------------

    def _find_customer(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute the find_customer action.

        Input contract (from context.variables):
            customerIdentifier (str, required): The identifier to search for.
                Supported values are the customer_identifier or email fields
                stored in the local mock CRM.

        Output (on success):
            If found:
                {
                    "customerFound": True,
                    "customerId": str,
                    "customerIdentifier": str,
                    "name": str,
                    "company": str,
                    "status": str,
                }
            If not found:
                {
                    "customerFound": False,
                }

        Dry-run:
            Returns a deterministic simulated result with dry_run=True.
            Zero database access.
        """
        # -------------------------------------------------------------------
        # Dry-run: zero database access, deterministic simulation
        # -------------------------------------------------------------------
        if context.dry_run:
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.DRY_RUN,
                outputs={
                    "customerFound": True,
                    "customerId": "CUST-DRY-0000",
                    "customerIdentifier": "dry-run@example.test",
                    "name": "Dry Run Customer",
                    "company": "Dry Run Corp",
                    "status": "active",
                    "dry_run": True,
                },
                result_summary=(
                    "CRM find_customer simulated (dry-run): "
                    "no database access performed."
                ),
                error_summary=None,
            )

        # -------------------------------------------------------------------
        # Input validation: customerIdentifier is required
        # -------------------------------------------------------------------
        raw_identifier = context.variables.get("customerIdentifier")

        if raw_identifier is None:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="CRM find_customer failed: missing required input 'customerIdentifier'.",
                error_summary=(
                    "Required input 'customerIdentifier' is absent from the execution variables. "
                    "Provide a valid customer email or identifier."
                ),
            )

        identifier = str(raw_identifier).strip()
        if not identifier:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="CRM find_customer failed: 'customerIdentifier' is empty.",
                error_summary=(
                    "Required input 'customerIdentifier' is empty or whitespace-only. "
                    "Provide a non-empty customer email or identifier."
                ),
            )


        try:
            customer_doc = find_customer_by_identifier(identifier)
        except CRMStorageError as exc:
            sanitized = sanitize_text(str(exc))
            logger.error(
                "CRM storage error for execution %s step %d: %s",
                context.execution_id,
                context.step.order,
                sanitized,
            )
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="CRM find_customer failed due to storage error.",
                error_summary=f"CRM storage error: {sanitized}",
            )

        # -------------------------------------------------------------------
        # Result: customer found
        # -------------------------------------------------------------------
        if customer_doc is not None:
            customer_id = customer_doc.get("customer_id", "UNKNOWN")
            name = customer_doc.get("name", "")
            company = customer_doc.get("company", "")
            status = customer_doc.get("status", "")
            cust_identifier = customer_doc.get("customer_identifier", identifier)

            logger.info(
                "CRM find_customer: found customer '%s' for identifier '%s' "
                "(execution %s, step %d).",
                customer_id,
                # Log only a truncated/safe version of the identifier
                identifier[:4] + "..." if len(identifier) > 4 else identifier,
                context.execution_id,
                context.step.order,
            )

            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={
                    "customerFound": True,
                    "customerId": customer_id,
                    "customerIdentifier": cust_identifier,
                    "name": name,
                    "company": company,
                    "status": status,
                },
                result_summary=(
                    f"CRM find_customer completed: customer '{customer_id}' found "
                    f"(status: {status})."
                ),
                error_summary=None,
            )

        # -------------------------------------------------------------------
        # Result: customer not found (not a failure - safe not-found response)
        # -------------------------------------------------------------------
        logger.info(
            "CRM find_customer: no customer found for identifier (execution %s, step %d).",
            context.execution_id,
            context.step.order,
        )

        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={"customerFound": False},
            result_summary=(
                "CRM find_customer completed: no customer found for the provided identifier."
            ),
            error_summary=None,
        )

    # -----------------------------------------------------------------------
    # update_customer (Phase 8.9)
    # -----------------------------------------------------------------------

    def _update_customer(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute the update_customer action.

        Input contract (from context.variables):
            customerIdentifier (str, required):
                The identifier (email) of the customer to update.
            updates (dict, required):
                A dict of field -> value pairs to update.
                ONLY fields in ALLOWED_UPDATE_FIELDS are accepted.
                MongoDB operators ($set, $push, etc.) are explicitly rejected.

        Allowed update fields:
            - status: one of ALLOWED_STATUS_VALUES
            - notes:  plain string, max MAX_NOTES_LENGTH characters

        Output (customer found & updated):
            {
                "customerFound": True,
                "updated": True,
                "customerId": str,
                "customerIdentifier": str,
                "updatedFields": List[str],
                "customer": { ...all mutable fields... },
            }

        Output (customer not found):
            {
                "customerFound": False,
                "updated": False,
            }

        Dry-run (context.dry_run == True):
            Zero database writes. Returns a deterministic simulated result
            showing which fields would be updated.
        """
        # -------------------------------------------------------------------
        # Input validation: customerIdentifier
        # -------------------------------------------------------------------
        raw_identifier = context.variables.get("customerIdentifier")

        if raw_identifier is None:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=(
                    "CRM update_customer failed: missing required input 'customerIdentifier'."
                ),
                error_summary=(
                    "Required input 'customerIdentifier' is absent from execution variables. "
                    "Provide a valid customer email or identifier."
                ),
            )

        identifier = str(raw_identifier).strip()
        if not identifier:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=(
                    "CRM update_customer failed: 'customerIdentifier' is empty."
                ),
                error_summary=(
                    "Required input 'customerIdentifier' is empty or whitespace-only."
                ),
            )

        # -------------------------------------------------------------------
        # Input validation: updates dict
        # -------------------------------------------------------------------
        raw_updates = context.variables.get("updates")

        if raw_updates is None:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=(
                    "CRM update_customer failed: missing required input 'updates'."
                ),
                error_summary=(
                    "Required input 'updates' is absent from execution variables. "
                    "Provide a dict of allowed fields to update."
                ),
            )

        if not isinstance(raw_updates, dict):
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=(
                    "CRM update_customer failed: 'updates' must be a dictionary."
                ),
                error_summary=(
                    f"'updates' must be a dict, got {type(raw_updates).__name__}."
                ),
            )

        if not raw_updates:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=(
                    "CRM update_customer failed: 'updates' dict is empty."
                ),
                error_summary=(
                    "Provide at least one field to update. "
                    f"Allowed fields: {sorted(ALLOWED_UPDATE_FIELDS)}."
                ),
            )

        # -------------------------------------------------------------------
        # Dry-run: zero database writes, deterministic simulation
        # -------------------------------------------------------------------
        if context.dry_run:
            simulated_fields = [
                f for f in raw_updates.keys()
                if isinstance(f, str) and not f.startswith("$")
            ]
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.DRY_RUN,
                outputs={
                    "customerFound": True,
                    "updated": False,
                    "customerId": "CUST-DRY-0000",
                    "customerIdentifier": "dry-run@example.test",
                    "updatedFields": simulated_fields,
                    "customer": {
                        "customerId": "CUST-DRY-0000",
                        "status": "active",
                        "notes": None,
                    },
                    "dry_run": True,
                    "database_write": False,
                },
                result_summary=(
                    f"CRM update_customer simulated (dry-run): "
                    f"fields {simulated_fields} would be updated. No database write performed."
                ),
                error_summary=None,
            )

        # -------------------------------------------------------------------
        # Live update via the mock CRM storage layer
        # (all operator injection and allowlist checks happen inside
        #  update_customer_by_identifier; we surface any ValueError as FAILED)
        # -------------------------------------------------------------------
        try:
            updated_doc = update_customer_by_identifier(identifier, raw_updates)
        except ValueError as exc:
            sanitized = sanitize_text(str(exc))
            logger.warning(
                "CRM update_customer validation error (execution %s step %d): %s",
                context.execution_id,
                context.step.order,
                sanitized,
            )
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=f"CRM update_customer failed: {sanitized}",
                error_summary=sanitized,
            )
        except CRMStorageError as exc:
            sanitized = sanitize_text(str(exc))
            logger.error(
                "CRM storage error for execution %s step %d: %s",
                context.execution_id,
                context.step.order,
                sanitized,
            )
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="CRM update_customer failed due to storage error.",
                error_summary=f"CRM storage error: {sanitized}",
            )

        # -------------------------------------------------------------------
        # Customer not found
        # -------------------------------------------------------------------
        if updated_doc is None:
            logger.info(
                "CRM update_customer: no customer found for identifier "
                "(execution %s, step %d).",
                context.execution_id,
                context.step.order,
            )
            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs={"customerFound": False, "updated": False},
                result_summary=(
                    "CRM update_customer completed: no customer found for the provided identifier."
                ),
                error_summary=None,
            )

        # -------------------------------------------------------------------
        # Customer found and updated
        # -------------------------------------------------------------------
        customer_id = updated_doc.get("customer_id", "UNKNOWN")
        cust_identifier = updated_doc.get("customer_identifier", identifier)
        updated_fields = sorted(raw_updates.keys())

        logger.info(
            "CRM update_customer: updated customer '%s' fields %s "
            "(execution %s, step %d).",
            customer_id,
            updated_fields,
            context.execution_id,
            context.step.order,
        )

        # Build a safe, minimal customer snapshot for downstream steps
        customer_snapshot = {
            "customerId": customer_id,
            "customerIdentifier": cust_identifier,
            "name": updated_doc.get("name", ""),
            "company": updated_doc.get("company", ""),
            "status": updated_doc.get("status", ""),
            "notes": updated_doc.get("notes"),
        }

        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs={
                "customerFound": True,
                "updated": True,
                "customerId": customer_id,
                "customerIdentifier": cust_identifier,
                "updatedFields": updated_fields,
                "customer": customer_snapshot,
            },
            result_summary=(
                f"CRM update_customer completed: customer '{customer_id}' updated "
                f"(fields: {updated_fields})."
            ),
            error_summary=None,
        )

