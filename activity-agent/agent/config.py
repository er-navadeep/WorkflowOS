"""
Activity Agent — Configuration
================================
Loads all agent settings from environment variables / .env file.
Every value has a sensible default so the agent works out-of-the-box
for local development without any extra setup.

Priority:
    1. Explicit env var
    2. .env file (loaded by python-dotenv)
    3. Hard-coded default
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load the project-level .env (one directory up from activity-agent/)
_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(dotenv_path=os.path.normpath(_env_path), override=False)


@dataclass(frozen=True)
class AgentConfig:
    """
    Immutable configuration for the Activity Agent.

    All values are read once at construction time from environment variables,
    making the config cheap to pass around and safe to share across threads.
    """

    # ------------------------------------------------------------------
    # Backend API
    # ------------------------------------------------------------------
    backend_url: str = field(
        default_factory=lambda: os.getenv(
            "WORKFLOWOS_BACKEND_URL", "http://127.0.0.1:8000"
        )
    )

    # ------------------------------------------------------------------
    # Simulation behaviour
    # ------------------------------------------------------------------

    # How many full workflow repetitions to simulate
    simulation_repetitions: int = field(
        default_factory=lambda: int(
            os.getenv("AGENT_SIMULATION_REPETITIONS", "3")
        )
    )

    # Seconds to wait between individual events within a single session
    event_delay_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("AGENT_EVENT_DELAY_SECONDS", "0.3")
        )
    )

    # Seconds to wait between complete workflow repetitions
    session_delay_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("AGENT_SESSION_DELAY_SECONDS", "0.5")
        )
    )

    # ------------------------------------------------------------------
    # HTTP sender
    # ------------------------------------------------------------------

    # Request timeout in seconds for each POST to the backend
    http_timeout_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("AGENT_HTTP_TIMEOUT_SECONDS", "10.0")
        )
    )

    # Number of retry attempts on transient HTTP failures
    http_max_retries: int = field(
        default_factory=lambda: int(
            os.getenv("AGENT_HTTP_MAX_RETRIES", "3")
        )
    )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def events_endpoint(self) -> str:
        """Full URL for the single-event ingest endpoint."""
        return f"{self.backend_url.rstrip('/')}/api/v1/events"

    @property
    def batch_endpoint(self) -> str:
        """Full URL for the batch ingest endpoint."""
        return f"{self.backend_url.rstrip('/')}/api/v1/events/batch"

    @property
    def health_endpoint(self) -> str:
        """Full URL for the health check endpoint."""
        return f"{self.backend_url.rstrip('/')}/health"


# Module-level singleton — import this in other modules
config = AgentConfig()
