"""
Integration Registry — Phase 8 Step 8.3
========================================
Central registry for resolving (application, action) pairs to their
concrete integration adapters.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.integrations.base import BaseIntegrationAdapter

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """
    Registry that maintains and resolves application integration adapters.
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, BaseIntegrationAdapter] = {}

    def register(self, adapter: BaseIntegrationAdapter) -> None:
        """Register an adapter under its normalized application name."""
        key = adapter.application_name.strip().lower()
        self._adapters[key] = adapter
        logger.info(
            "Registered integration adapter for application: '%s'",
            adapter.application_name,
        )

    def get_adapter(
        self, application: str, action: str
    ) -> Optional[BaseIntegrationAdapter]:
        """
        Find an adapter capable of handling the specified application and action.

        Returns None if no adapter is registered or if the adapter cannot handle the action.
        """
        if not application or not action:
            return None

        key = application.strip().lower()
        adapter = self._adapters.get(key)
        if adapter is not None and adapter.can_handle(action):
            return adapter

        return None

    def is_supported(self, application: str, action: str) -> bool:
        """Return True if an adapter exists that can handle the action."""
        return self.get_adapter(application, action) is not None

    def list_supported_applications(self) -> List[str]:
        """Return list of registered application names."""
        return [adapter.application_name for adapter in self._adapters.values()]


_global_registry: Optional[IntegrationRegistry] = None


def get_integration_registry() -> IntegrationRegistry:
    """
    Return the singleton IntegrationRegistry instance, lazily registering
    built-in adapters.
    """
    global _global_registry
    if _global_registry is None:
        registry = IntegrationRegistry()
        # Register Phase 8.3 Slack adapter
        from app.integrations.slack.adapter import SlackAdapter
        registry.register(SlackAdapter())
        # Register Phase 8.5 Gmail adapter
        from app.integrations.gmail.adapter import GmailAdapter
        registry.register(GmailAdapter())
        # Register Phase 8.8 CRM adapter
        from app.integrations.crm.adapter import CRMAdapter
        registry.register(CRMAdapter())
        _global_registry = registry

    return _global_registry
