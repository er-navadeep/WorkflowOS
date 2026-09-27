"""
Integrations Package — WorkFlowOS Phase 8.3
============================================
Provides integration adapter interfaces, adapter registry, and
third-party service adapters (Slack, and in future phases Gmail, CRM).
"""

from __future__ import annotations

from app.integrations.base import (
    BaseIntegrationAdapter,
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.integrations.registry import IntegrationRegistry, get_integration_registry
from app.integrations.gmail.adapter import GmailAdapter
from app.integrations.slack.adapter import SlackAdapter
from app.integrations.crm.adapter import CRMAdapter

__all__ = [
    "BaseIntegrationAdapter",
    "StepExecutionContext",
    "StepExecutionResult",
    "IntegrationRegistry",
    "get_integration_registry",
    "sanitize_text",
    "GmailAdapter",
    "SlackAdapter",
    "CRMAdapter",
]
