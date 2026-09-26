"""
Workflow Validator — Phase 6
==============================
Deterministic validation of a WorkflowDefinition, independent of Gemini.

Validation is performed AFTER AI generation and BEFORE MongoDB persistence.
It acts as a safety net to catch structural errors, invented data, and
policy violations that the AI might introduce.

Rules validated:
    1.  Workflow name is non-empty.
    2.  Workflow description is non-empty.
    3.  Trigger exists with non-empty application and event.
    4.  At least one step exists.
    5.  Step ordering values are unique.
    6.  Step ordering is sequential from 1..N.
    7.  Every step has a non-empty application.
    8.  Every step has a non-empty action.
    9.  Integration applications are consistent with the understanding.
    10. No secret values are present (API key patterns, credential words).
    11. No executable code is present in description/action fields.
    12. Conditions are structurally valid (non-empty expression, on_true).
    13. status is "generated".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set

from app.schemas.workflow import WorkflowDefinition
from app.schemas.workflow_understanding import WorkflowUnderstanding


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of deterministic workflow validation."""

    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# Secret / code detection patterns
# ---------------------------------------------------------------------------

# Patterns that suggest API keys, tokens, or credentials
_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),          # AWS access key
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),       # OpenAI / generic sk- key
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),    # Google API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),       # GitHub personal access token
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]+"),# Slack token
    re.compile(r"(?i)password\s*[:=]\s*\S+"), # password = ...
    re.compile(r"(?i)api[_\-]?key\s*[:=]\s*\S+"),  # api_key = ...
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),   # secret = ...
    re.compile(r"(?i)token\s*[:=]\s*\S+"),    # token = ...
]

# Patterns suggesting executable code was injected
_CODE_PATTERNS = [
    re.compile(r"import\s+\w+"),              # Python import
    re.compile(r"require\s*\("),              # Node.js require
    re.compile(r"def\s+\w+\s*\("),            # Python function def
    re.compile(r"function\s+\w+\s*\("),       # JS function
    re.compile(r"<script"),                   # HTML script tag
    re.compile(r"eval\s*\("),                 # eval()
    re.compile(r"exec\s*\("),                 # exec()
    re.compile(r"subprocess\."),              # subprocess module
    re.compile(r"os\.system"),                # os.system
    re.compile(r"\$\(.*\)"),                  # shell command substitution
]


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------


def validate_workflow(
    workflow: WorkflowDefinition,
    understanding: Optional[WorkflowUnderstanding] = None,
) -> ValidationResult:
    """
    Run all deterministic checks against a WorkflowDefinition.

    Args:
        workflow:      The WorkflowDefinition to validate.
        understanding: Optional source understanding for cross-reference checks.

    Returns:
        A ValidationResult with valid=True when all checks pass,
        or valid=False with a list of error messages.
    """
    result = ValidationResult()

    _check_identity(workflow, result)
    _check_trigger(workflow, result)
    _check_steps(workflow, result)
    _check_conditions(workflow, result)
    _check_status(workflow, result)
    _check_secrets(workflow, result)
    _check_executable_code(workflow, result)

    if understanding is not None:
        _check_integration_consistency(workflow, understanding, result)

    return result


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_identity(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rule 1–2: name and description must be non-empty."""
    if not workflow.name or not workflow.name.strip():
        result.add_error("Workflow name is empty.")
    if not workflow.description or not workflow.description.strip():
        result.add_error("Workflow description is empty.")
    if not workflow.understanding_id:
        result.add_error("understanding_id is missing.")


def _check_trigger(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rule 3: trigger must exist with non-empty application and event."""
    t = workflow.trigger
    if not t.application or not t.application.strip():
        result.add_error("Trigger application is empty.")
    if not t.event or not t.event.strip():
        result.add_error("Trigger event is empty.")


def _check_steps(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rules 4–8: step count, uniqueness, ordering, application, action."""
    if not workflow.steps:
        result.add_error("Workflow has no steps.")
        return

    orders: List[int] = []
    for i, step in enumerate(workflow.steps):
        # Rule 7: application must be non-empty
        if not step.application or not step.application.strip():
            result.add_error(f"Step {i+1} has an empty 'application' field.")

        # Rule 8: action must be non-empty
        if not step.action or not step.action.strip():
            result.add_error(f"Step {i+1} has an empty 'action' field.")

        orders.append(step.order)

    # Rule 5: orders must be unique
    if len(orders) != len(set(orders)):
        result.add_error(
            f"Step ordering values are not unique: {sorted(orders)}."
        )

    # Rule 6: orders must be sequential 1..N
    expected = list(range(1, len(orders) + 1))
    if sorted(orders) != expected:
        result.add_error(
            f"Step ordering must be sequential 1..{len(orders)}, got {sorted(orders)}."
        )


def _check_conditions(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rule 12: conditions must have non-empty expression and on_true."""
    for i, cond in enumerate(workflow.conditions):
        if not cond.expression or not cond.expression.strip():
            result.add_error(f"Condition {i+1} has an empty 'expression'.")
        if not cond.on_true or not cond.on_true.strip():
            result.add_error(f"Condition {i+1} has an empty 'on_true'.")


def _check_status(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rule 13: status must be 'generated'."""
    if workflow.status != "generated":
        result.add_error(
            f"Workflow status must be 'generated', got '{workflow.status}'."
        )


def _check_secrets(workflow: WorkflowDefinition, result: ValidationResult) -> None:
    """Rule 10: no secret values may appear in any text field."""
    texts = _collect_text_fields(workflow)
    for label, text in texts:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                result.add_error(
                    f"Potential secret detected in field '{label}'. "
                    "Remove all credential values from the workflow definition."
                )
                break  # one error per field is enough


def _check_executable_code(
    workflow: WorkflowDefinition, result: ValidationResult
) -> None:
    """Rule 11: no executable code may appear in text fields."""
    texts = _collect_text_fields(workflow)
    for label, text in texts:
        for pattern in _CODE_PATTERNS:
            if pattern.search(text):
                result.add_warning(
                    f"Possible executable code pattern detected in field '{label}'. "
                    "Workflow definitions must not contain runnable code."
                )
                break


def _check_integration_consistency(
    workflow: WorkflowDefinition,
    understanding: WorkflowUnderstanding,
    result: ValidationResult,
) -> None:
    """Rule 9: integration applications must be a subset of understanding applications."""
    allowed: Set[str] = {a.lower() for a in understanding.applications}
    for itg in workflow.integrations:
        if itg.application.lower() not in allowed:
            result.add_error(
                f"Integration application '{itg.application}' was not present "
                f"in the source understanding (allowed: {list(understanding.applications)})."
            )


# ---------------------------------------------------------------------------
# Text collector
# ---------------------------------------------------------------------------


def _collect_text_fields(workflow: WorkflowDefinition) -> List[tuple]:
    """Collect all text fields from the workflow for pattern scanning."""
    texts = [
        ("name", workflow.name),
        ("description", workflow.description),
        ("trigger.application", workflow.trigger.application),
        ("trigger.event", workflow.trigger.event),
        ("trigger.description", workflow.trigger.description),
        ("error_handling.notes", workflow.error_handling.notes),
    ]
    for step in workflow.steps:
        texts.append((f"step[{step.order}].application", step.application))
        texts.append((f"step[{step.order}].action", step.action))
        texts.append((f"step[{step.order}].description", step.description))
    for i, cond in enumerate(workflow.conditions):
        texts.append((f"condition[{i+1}].description", cond.description))
        texts.append((f"condition[{i+1}].expression", cond.expression))
    for v in workflow.variables:
        texts.append((f"variable.{v.name}.description", v.description))
    for itg in workflow.integrations:
        texts.append((f"integration.{itg.application}.purpose", itg.purpose))
    return texts
