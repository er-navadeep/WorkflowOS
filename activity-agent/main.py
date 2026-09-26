"""
WorkFlowOS — Activity Agent CLI Entry Point
=============================================
Simulates repeated user workflows and sends events to the backend API.

Usage (from project root):
    .venv\\Scripts\\python activity-agent/main.py

With options:
    .venv\\Scripts\\python activity-agent/main.py --repetitions 5
    .venv\\Scripts\\python activity-agent/main.py --repetitions 3 --event-delay 0.5
    .venv\\Scripts\\python activity-agent/main.py --backend http://127.0.0.1:8000

Environment variables (alternative to CLI flags):
    WORKFLOWOS_BACKEND_URL=http://127.0.0.1:8000
    AGENT_SIMULATION_REPETITIONS=3
    AGENT_EVENT_DELAY_SECONDS=0.3
    AGENT_SESSION_DELAY_SECONDS=0.5
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Path setup — must happen before any local imports
# ---------------------------------------------------------------------------

# Add the activity-agent directory itself to sys.path
_agent_dir = os.path.dirname(os.path.abspath(__file__))
if _agent_dir not in sys.path:
    sys.path.insert(0, _agent_dir)

# Add the backend directory so 'app.*' schemas are importable
_backend_dir = os.path.normpath(os.path.join(_agent_dir, "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# ---------------------------------------------------------------------------
# Now we can safely import local modules
# ---------------------------------------------------------------------------

from agent.config import AgentConfig  # noqa: E402
from agent.runner import AgentRunner  # noqa: E402
from sources.simulation.customer_request import CustomerRequestSource  # noqa: E402


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,  # Keep INFO/DEBUG quiet during demo; use WARNING+
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workflowos-agent",
        description="WorkFlowOS Activity Agent — simulates user workflows and sends events to backend.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--backend",
        metavar="URL",
        default=None,
        help="Backend API base URL (overrides WORKFLOWOS_BACKEND_URL env var).",
    )
    parser.add_argument(
        "--repetitions",
        metavar="N",
        type=int,
        default=None,
        help="Number of workflow repetitions to simulate (overrides AGENT_SIMULATION_REPETITIONS).",
    )
    parser.add_argument(
        "--event-delay",
        metavar="SECONDS",
        type=float,
        default=None,
        dest="event_delay",
        help="Delay between events in one session (overrides AGENT_EVENT_DELAY_SECONDS).",
    )
    parser.add_argument(
        "--session-delay",
        metavar="SECONDS",
        type=float,
        default=None,
        dest="session_delay",
        help="Delay between workflow repetitions (overrides AGENT_SESSION_DELAY_SECONDS).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (INFO level).",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Entry point.

    Returns:
        0 on success, 1 if any events failed to send.
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Apply CLI overrides to environment before building config
    if args.backend:
        os.environ["WORKFLOWOS_BACKEND_URL"] = args.backend
    if args.repetitions is not None:
        os.environ["AGENT_SIMULATION_REPETITIONS"] = str(args.repetitions)
    if args.event_delay is not None:
        os.environ["AGENT_EVENT_DELAY_SECONDS"] = str(args.event_delay)
    if args.session_delay is not None:
        os.environ["AGENT_SESSION_DELAY_SECONDS"] = str(args.session_delay)

    # Rebuild config after applying overrides
    config = AgentConfig()
    source = CustomerRequestSource()
    runner = AgentRunner(source=source, config=config)

    summary = runner.run()

    # Exit code: 0 if all events sent, 1 if any failed
    return 0 if summary.total_events_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
