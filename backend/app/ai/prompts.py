"""
AI Prompts — Workflow Understanding
=====================================
Builds the prompt sent to Gemini for Phase 5 AI understanding.

Design rules:
- Evidence-first: the model must derive output from the observed sequence only.
- No invention: the model must NOT add applications, APIs, or actions
  that were not observed.
- Structured output only: the model must return valid JSON matching our schema.
- Uncertainty-aware: when the model cannot confidently infer something,
  it must say so (inferred=true on conditions, low confidence value).
- No execution: the model must not generate executable code or scripts.
"""

from __future__ import annotations

from typing import List

from app.models.workflow_candidate import WorkflowCandidate, SequenceStep


# ---------------------------------------------------------------------------
# JSON schema description embedded in the prompt
# ---------------------------------------------------------------------------

_OUTPUT_SCHEMA = """
{
  "intent": "<short noun-phrase: user's goal>",
  "name": "<human-readable workflow name>",
  "description": "<one-paragraph explanation of what the workflow accomplishes>",
  "trigger": "<what starts this workflow — based on the first observed event>",
  "applications": ["<app1>", "<app2>", "..."],
  "actions": [
    {
      "order": 1,
      "application": "<app name>",
      "operation": "<short verb-noun phrase>",
      "description": "<one sentence derived from observed evidence>"
    }
  ],
  "conditions": [
    {
      "description": "<what the condition checks>",
      "consequence": "<what happens>",
      "inferred": true
    }
  ],
  "variables": [
    {
      "name": "<variableName>",
      "description": "<what this variable holds>",
      "observed_in": "<application or step where first seen>"
    }
  ],
  "confidence": 0.85
}
"""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def build_understanding_prompt(candidate: WorkflowCandidate) -> str:
    """
    Build the full Gemini prompt for workflow understanding.

    The prompt encodes all observed evidence from the WorkflowCandidate
    and instructs the model to produce structured JSON output.

    Args:
        candidate: The WorkflowCandidate to analyse.

    Returns:
        A complete prompt string ready to send to the Gemini API.
    """
    sequence_text = _format_sequence(candidate.sequence)
    applications_text = ", ".join(candidate.applications)

    prompt = f"""You are an AI analyst for WorkFlowOS, an OS-level workflow automation system.

Your task is to analyse a REPEATED COMPUTER WORKFLOW that was AUTOMATICALLY OBSERVED from a user's desktop activity.

You must:
1. Understand the user's likely intent from the observed evidence.
2. Convert low-level computer actions into higher-level semantic descriptions.
3. Preserve the exact applications that were observed — do NOT add applications that were not present.
4. Identify any conditions or decision points that are implied by the sequence.
5. Identify any data values (variables) that clearly flow between steps.
6. Report your confidence honestly. If the evidence is ambiguous, lower the confidence.
7. Return ONLY valid JSON — no markdown, no explanations, no code blocks.

You must NOT:
- Invent actions that are not supported by the observed sequence.
- Assume specific channel names, email addresses, API endpoints, or credentials.
- Generate executable code or scripts.
- Add applications or integrations that were not observed.
- Return any text outside of the JSON object.

---

OBSERVED WORKFLOW EVIDENCE
===========================

Candidate name (from discovery engine): {candidate.name}
Observed applications: {applications_text}
Occurrence count: {candidate.occurrence_count} times observed
Discovery confidence score: {candidate.score:.2f}

Observed sequence ({len(candidate.sequence)} steps):
{sequence_text}

---

DISTINCTION BETWEEN OBSERVATION AND INTERPRETATION
===================================================

Each step above is a LOW-LEVEL machine observation (event_type / application / action).

Your job is to lift these into SEMANTIC descriptions:

Example:
  Observed:  event_type=email, application=Gmail, action=open_email
  Interpret: "Read incoming customer email" (in Gmail)

  Observed:  event_type=crm, application=CRM, action=find_customer
  Interpret: "Look up customer record" (in CRM)

  Observed:  event_type=slack, application=Slack, action=send_message
  Interpret: "Notify team" (in Slack)
  NOT:       "Send message to #customer-support" (channel not observed)

---

CONFIDENCE GUIDANCE
===================

Set confidence between 0.0 and 1.0:
- 0.9–1.0: All steps are clear, intent is unambiguous.
- 0.7–0.89: Most steps are clear, minor ambiguity.
- 0.5–0.69: Significant ambiguity in intent or conditions.
- Below 0.5: Evidence is insufficient for a reliable understanding.

---

OUTPUT FORMAT
=============

Return ONLY a single JSON object with this exact structure:

{_OUTPUT_SCHEMA}

Rules:
- "applications" must list ONLY applications from the observed sequence above.
- "actions" must have exactly one entry per observed step (same count: {len(candidate.sequence)}).
- "conditions" may be empty [] if no conditions are evident.
- "variables" may be empty [] if no clear data flow is observed.
- "confidence" must be a float between 0.0 and 1.0.
- Do not wrap the JSON in markdown code fences.
- Do not add any text before or after the JSON.

Return the JSON now:"""

    return prompt


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_sequence(steps: List[SequenceStep]) -> str:
    """Format the observed sequence into a readable numbered list."""
    lines = []
    for step in steps:
        lines.append(
            f"  Step {step.order}: "
            f"event_type={step.event_type!r}, "
            f"application={step.application!r}, "
            f"action={step.action!r}"
        )
    return "\n".join(lines)
