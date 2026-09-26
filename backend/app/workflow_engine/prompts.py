"""
Workflow Generation Prompts — Phase 6
=======================================
Builds the Gemini prompt that converts a WorkflowUnderstanding into
a structured WorkflowDefinition.

Design rules (mirrored from Phase 5):
- Evidence-first: only data present in the WorkflowUnderstanding is used.
- No invention: no channel names, email addresses, API endpoints, credentials.
- Structured output only: valid JSON matching the WorkflowDefinition schema.
- No execution: no executable code, no real actions.
- Human-intervention paths must be preserved when present.
"""

from __future__ import annotations

from app.schemas.workflow_understanding import WorkflowUnderstanding


# ---------------------------------------------------------------------------
# JSON schema embedded in the prompt
# ---------------------------------------------------------------------------

_OUTPUT_SCHEMA = """
{
  "name": "<human-readable workflow name>",
  "description": "<one-paragraph explanation of the workflow>",
  "trigger": {
    "application": "<first application in the sequence>",
    "event": "<what event starts the workflow>",
    "description": "<one sentence describing the trigger>"
  },
  "steps": [
    {
      "order": 1,
      "application": "<app name — must exist in the understanding>",
      "action": "<short snake_case verb-noun, e.g. read_email>",
      "description": "<one sentence derived from the understanding>",
      "inputs": ["<variable_name>"],
      "outputs": ["<variable_name>"],
      "on_failure": "stop"
    }
  ],
  "conditions": [
    {
      "description": "<what the condition checks>",
      "expression": "<natural-language expression — no code>",
      "on_true": "<what happens, e.g. request_human_intervention>",
      "on_false": "continue"
    }
  ],
  "variables": [
    {
      "name": "<variableName>",
      "description": "<what this variable holds>",
      "source_step_order": 1
    }
  ],
  "integrations": [
    {
      "application": "<app name — must exist in the understanding>",
      "purpose": "<why this app is used>",
      "required_capabilities": ["<read_email>", "<send_message>"]
    }
  ],
  "error_handling": {
    "on_step_failure": "stop_and_report",
    "on_missing_input": "stop",
    "on_timeout": "stop_and_report",
    "notes": "<any additional error-handling notes>"
  }
}
"""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def build_generation_prompt(understanding: WorkflowUnderstanding) -> str:
    """
    Build the full Gemini prompt for Phase 6 workflow generation.

    Args:
        understanding: The Phase 5 WorkflowUnderstanding to convert.

    Returns:
        A complete prompt string ready to send to the Gemini API.
    """
    actions_text = _format_actions(understanding)
    conditions_text = _format_conditions(understanding)
    variables_text = _format_variables(understanding)
    applications_text = ", ".join(understanding.applications)

    prompt = f"""You are a workflow architect for WorkFlowOS, an OS-level workflow automation system.

Your task is to convert an ALREADY-UNDERSTOOD workflow into a structured WORKFLOW DEFINITION.

You are NOT analysing raw activity events.
You are converting a completed semantic understanding into a machine-readable workflow structure.

---

ABSOLUTE RULES
==============

1.  Use ONLY information present in the WorkflowUnderstanding below.
2.  Do NOT invent applications not listed in the understanding.
3.  Do NOT invent actions not described in the understanding.
4.  Do NOT invent credentials, API keys, or OAuth tokens.
5.  Do NOT invent URLs, endpoints, or hostnames.
6.  Do NOT invent Slack channels (e.g. #customer-support).
7.  Do NOT invent CRM field values (e.g. customer.status = "active").
8.  Do NOT invent email addresses or sender names.
9.  Do NOT generate executable code, scripts, or commands.
10. Do NOT execute anything — this is a definition only.
11. Preserve the exact application sequence from the understanding.
12. Represent uncertainty explicitly (use on_true: "request_human_intervention" when unsure).
13. Return ONLY valid JSON — no markdown, no explanations, no code blocks.
14. Follow the schema provided exactly.
15. Preserve human-intervention paths that are present in the conditions.

---

SOURCE WORKFLOW UNDERSTANDING
==============================

Intent: {understanding.intent}
Name: {understanding.name}
Description: {understanding.description}
Trigger: {understanding.trigger}
Applications: {applications_text}
Confidence: {understanding.confidence:.2f}

Actions ({len(understanding.actions)} steps):
{actions_text}

Conditions ({len(understanding.conditions)}):
{conditions_text}

Variables ({len(understanding.variables)}):
{variables_text}

---

CONVERSION GUIDANCE
====================

trigger:
  - application: use the application from step 1.
  - event: derive from the trigger field in the understanding.
  - description: one sentence summarising when the workflow starts.

steps:
  - Create one step per action in the understanding, preserving order.
  - action: convert the operation to snake_case (e.g. "Read email" → "read_email").
  - on_failure: use "stop" unless the understanding implies a different path.
  - inputs/outputs: only include variable names that are explicit in the understanding.

conditions:
  - Preserve every condition from the understanding.
  - If the consequence mentions "human intervention", set on_true = "request_human_intervention".
  - expression: natural language only — no code.

variables:
  - Include only variables mentioned in the understanding.
  - source_step_order: the order of the step that first produces this variable.

integrations:
  - One entry per application in the understanding.
  - required_capabilities: list only capabilities implied by the steps.

error_handling:
  - Use "stop_and_report" as the default unless the understanding implies otherwise.
  - Add a notes field only if the understanding contains specific error guidance.

---

OUTPUT FORMAT
=============

Return ONLY this JSON structure — no markdown fences, no extra text:

{_OUTPUT_SCHEMA}

Rules:
- "steps" must have exactly {len(understanding.actions)} entries (one per action above).
- "integrations" must list ONLY applications from: {applications_text}.
- All fields shown in the schema must be present.
- "conditions" may be [] if none are present in the understanding.
- "variables" may be [] if none are explicit in the understanding.
- Do not add any text before or after the JSON.

Return the JSON now:"""

    return prompt


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_actions(understanding: WorkflowUnderstanding) -> str:
    """Format the understanding's actions into a readable numbered list."""
    lines = []
    for action in understanding.actions:
        lines.append(
            f"  Step {action.order}: [{action.application}] "
            f"{action.operation} — {action.description}"
        )
    return "\n".join(lines) if lines else "  (none)"


def _format_conditions(understanding: WorkflowUnderstanding) -> str:
    """Format the understanding's conditions into a readable list."""
    if not understanding.conditions:
        return "  (none)"
    lines = []
    for i, cond in enumerate(understanding.conditions, 1):
        inferred = " [inferred]" if cond.inferred else ""
        lines.append(
            f"  {i}. {cond.description} → {cond.consequence}{inferred}"
        )
    return "\n".join(lines)


def _format_variables(understanding: WorkflowUnderstanding) -> str:
    """Format the understanding's variables into a readable list."""
    if not understanding.variables:
        return "  (none)"
    lines = []
    for v in understanding.variables:
        lines.append(
            f"  - {v.name}: {v.description} (first seen in: {v.observed_in})"
        )
    return "\n".join(lines)
