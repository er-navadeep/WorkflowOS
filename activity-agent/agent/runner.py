"""
Activity Agent — Runner
=========================
The Runner orchestrates the complete simulation loop:

    For each repetition:
        1. Generate a unique session_id
        2. Ask the source for events
        3. Send each event to the backend (with configurable delay)
        4. Print progress to terminal
        5. Wait before next repetition

The Runner knows about:
    - config (how many reps, delays, backend URL)
    - source (what events to generate)
    - sender (how to deliver events)

The Runner does NOT know about:
    - MongoDB
    - AI / discovery
    - specific workflow content
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List

from agent.config import AgentConfig
from agent.session import new_session_id
from sender.http_sender import HttpEventSender
from sources.base import BaseActivitySource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Run summary (returned by run())
# ---------------------------------------------------------------------------

@dataclass
class SessionSummary:
    """Result of one complete workflow repetition."""
    session_id: str
    events_sent: int
    events_failed: int
    repetition_index: int


@dataclass
class RunSummary:
    """Aggregate result of the full simulation run."""
    total_sessions: int
    total_events_sent: int
    total_events_failed: int
    sessions: List[SessionSummary] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.total_events_sent + self.total_events_failed
        return (self.total_events_sent / total * 100) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

BANNER = """
+----------------------------------------------------------+
|         WorkFlowOS - Activity Agent                      |
|         Simulation Mode                                  |
+----------------------------------------------------------+
"""

STEP_ICONS = {
    "application": "[APP]",
    "email":       "[EML]",
    "file":        "[FIL]",
    "crm":         "[CRM]",
    "slack":       "[SLK]",
    "browser":     "[WEB]",
    "ui":          "[UI ]",
    "form":        "[FRM]",
    "system":      "[SYS]",
}


class AgentRunner:
    """
    Drives one or more repetitions of a source through the sender.

    Args:
        source:  A BaseActivitySource implementation (e.g. CustomerRequestSource)
        config:  AgentConfig with backend URL, delays, repetition count
    """

    def __init__(self, source: BaseActivitySource, config: AgentConfig) -> None:
        self._source = source
        self._config = config
        self._sender = HttpEventSender(config)

    def run(self, repetitions: int | None = None) -> RunSummary:
        """
        Execute the full simulation loop.

        Args:
            repetitions: Override config.simulation_repetitions if provided.

        Returns:
            RunSummary with per-session and aggregate statistics.
        """
        reps = repetitions if repetitions is not None else self._config.simulation_repetitions

        print(BANNER)
        print(f"  Source      : {self._source.name}")
        print(f"  Backend     : {self._config.backend_url}")
        print(f"  Repetitions : {reps}")
        print(f"  Event delay : {self._config.event_delay_seconds}s")
        print()

        # --- Health check before starting ---
        ok, msg = self._sender.check_backend_health()
        if ok:
            print(f"  [OK] Backend reachable: {msg}")
        else:
            print(f"  [!!] Backend UNREACHABLE: {msg}")
            print("       Events will be attempted but may fail.")
        print()

        summary = RunSummary(total_sessions=0, total_events_sent=0, total_events_failed=0)

        for rep_idx in range(reps):
            session_id = new_session_id()
            session_summary = self._run_session(
                session_id=session_id,
                repetition_index=rep_idx,
                rep_number=rep_idx + 1,
                total_reps=reps,
            )
            summary.sessions.append(session_summary)
            summary.total_sessions += 1
            summary.total_events_sent += session_summary.events_sent
            summary.total_events_failed += session_summary.events_failed

            # Wait between sessions (but not after the last one)
            if rep_idx < reps - 1:
                time.sleep(self._config.session_delay_seconds)

        self._print_final_summary(summary)
        self._sender.close()
        return summary

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _run_session(
        self,
        session_id: str,
        repetition_index: int,
        rep_number: int,
        total_reps: int,
    ) -> SessionSummary:
        """Execute one complete workflow repetition."""

        print(f"  {'='*54}")
        print(f"  Repetition {rep_number}/{total_reps}")
        print(f"  Session ID : {session_id}")
        print(f"  {'='*54}")

        sent = 0
        failed = 0

        # CustomerRequestSource.generate_events accepts repetition_index
        # Other sources only need session_id — we handle both via try/except
        try:
            events = list(self._source.generate_events(session_id, repetition_index))
        except TypeError:
            events = list(self._source.generate_events(session_id))

        for step_num, event in enumerate(events, start=1):
            icon = STEP_ICONS.get(event.event_type.value, "[???]")
            label = f"{event.application:8} | {event.action}"

            result = self._sender.send(event)

            if result.success:
                sent += 1
                print(f"    {icon} Step {step_num:02d}: {label}")
                print(f"           target={event.target!r}")
                print(f"           event_id={result.event_id}")
                print(f"           [SENT OK]")
            else:
                failed += 1
                print(f"    {icon} Step {step_num:02d}: {label}")
                print(f"           [FAILED] {result.error}")

            # Delay between events within the session
            if step_num < len(events):
                time.sleep(self._config.event_delay_seconds)

        print()
        print(f"  Session complete: {sent} sent, {failed} failed")
        print()

        return SessionSummary(
            session_id=session_id,
            events_sent=sent,
            events_failed=failed,
            repetition_index=repetition_index,
        )

    def _print_final_summary(self, summary: RunSummary) -> None:
        print()
        print("  " + "=" * 54)
        print("  SIMULATION COMPLETE")
        print("  " + "=" * 54)
        print(f"  Sessions run    : {summary.total_sessions}")
        print(f"  Total events    : {summary.total_events_sent + summary.total_events_failed}")
        print(f"  Sent OK         : {summary.total_events_sent}")
        print(f"  Failed          : {summary.total_events_failed}")
        print(f"  Success rate    : {summary.success_rate:.1f}%")
        print()
        print("  Session IDs stored in MongoDB:")
        for s in summary.sessions:
            status = "OK" if s.events_failed == 0 else f"{s.events_failed} failed"
            print(f"    [{status:8}] {s.session_id}")
        print()
        print("  WorkFlowOS Discovery Engine can now detect the repeated")
        print("  workflow pattern across these sessions.")
        print()
