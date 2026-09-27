"""
Trigger Polling Scheduler — Phase 8.11 Step 3
=============================================
Lightweight asyncio background scheduler integrated with FastAPI lifespan.

Key Architectural Guarantees:
    - Zero heavy queue dependencies: No Celery, Redis, RQ, or external brokers.
    - Error isolation: One failing polling cycle or crashing workflow does not kill the scheduler loop.
    - Idempotent lifecycle: Prevents duplicate scheduler instances across hot-reloads.
    - Controlled concurrency: Sleeps between cycles, handles asyncio.CancelledError cleanly on shutdown.
    - Test-safe: Automatically stays inactive during pytest runs unless explicitly started.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from app.services.trigger_service import poll_triggers

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_INTERVAL_SECONDS = 30


class TriggerScheduler:
    """
    Lightweight background worker that periodically triggers polling
    for all active approved workflow triggers.
    """

    def __init__(self, interval_seconds: Optional[int] = None) -> None:
        if interval_seconds is None:
            env_interval = os.getenv("TRIGGER_POLL_INTERVAL_SECONDS", "").strip()
            interval_seconds = int(env_interval) if env_interval.isdigit() else DEFAULT_SCHEDULER_INTERVAL_SECONDS

        self.interval_seconds: int = max(interval_seconds, 5)
        self._task: Optional[asyncio.Task] = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the background polling loop if not already running."""
        if self.is_running:
            logger.info("TriggerScheduler is already running; skipping start.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(), name="workflowos_trigger_scheduler")
        logger.info(
            "TriggerScheduler started successfully (interval=%ds).",
            self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the background polling loop and await clean cancellation."""
        if not self._is_running or not self._task:
            return

        logger.info("TriggerScheduler stopping...")
        self._is_running = False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("TriggerScheduler encountered exception on shutdown: %s", exc)

        self._task = None
        logger.info("TriggerScheduler stopped cleanly.")

    async def _run_loop(self) -> None:
        """Core polling loop running in the background."""
        while self._is_running:
            try:
                # Run the synchronous polling cycle in a worker thread so the event loop is never blocked
                summary = await asyncio.to_thread(poll_triggers, dry_run=False)
                if summary.events_detected > 0:
                    logger.info(
                        "TriggerScheduler poll: %d detected, %d dispatched, %d skipped, %d errors.",
                        summary.events_detected,
                        summary.events_dispatched,
                        summary.events_skipped,
                        summary.errors_count,
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                # Error isolation: Never allow an unexpected error to kill the scheduler daemon
                logger.error("Unhandled error in TriggerScheduler loop: %s", exc, exc_info=True)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break


# ---------------------------------------------------------------------------
# Singleton Management
# ---------------------------------------------------------------------------

_scheduler_instance: Optional[TriggerScheduler] = None


def get_trigger_scheduler() -> TriggerScheduler:
    """Return the global TriggerScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TriggerScheduler()
    return _scheduler_instance


async def start_trigger_scheduler() -> None:
    """Helper called on FastAPI startup."""
    # Test-safe guard: Do not run automated polling loop during pytest runs
    if "PYTEST_CURRENT_TEST" in os.environ:
        logger.debug("Pytest environment detected; TriggerScheduler will not autostart.")
        return

    # Check env var if explicitly disabled
    if os.getenv("ENABLE_TRIGGER_SCHEDULER", "true").strip().lower() in ("false", "0", "no"):
        logger.info("TriggerScheduler is explicitly disabled via ENABLE_TRIGGER_SCHEDULER=false.")
        return

    scheduler = get_trigger_scheduler()
    await scheduler.start()


async def stop_trigger_scheduler() -> None:
    """Helper called on FastAPI shutdown."""
    global _scheduler_instance
    if _scheduler_instance is not None:
        await _scheduler_instance.stop()
        _scheduler_instance = None
