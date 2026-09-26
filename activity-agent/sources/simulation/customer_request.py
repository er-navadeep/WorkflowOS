"""
Simulation Source — Customer Request Processing
================================================
Generates the exact MVP demo workflow sequence:

    1. Gmail opened                         [application]
    2. Customer email opened                [email]
    3. Attachment downloaded                [file]
    4. CRM application opened               [application]
    5. Customer searched in CRM             [crm]
    6. Customer record updated in CRM       [crm]
    7. Slack notification sent              [slack]

This source is PURELY generative — it yields ActivityEvent objects
with realistic timestamps and metadata. It has no network I/O.

The Runner is responsible for sending events to the backend.

Implements: BaseActivitySource
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone
from typing import Iterator

# Ensure backend schemas are importable
_backend_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")
)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from app.schemas.activity_event import ActivityEvent, EventType  # noqa: E402

from sources.base import BaseActivitySource  # noqa: E402
from sources.simulation.demo_data import get_demo_email, get_demo_customer  # noqa: E402


class CustomerRequestSource(BaseActivitySource):
    """
    Simulates a knowledge worker processing a customer request email.

    Each call to generate_events() yields 7 ordered ActivityEvent objects
    representing one complete execution of the workflow pattern.

    The timestamps are spaced realistically (seconds apart) starting from
    'now', so the discovery engine sees a believable timeline.
    """

    # Seconds between each simulated step within a session
    # (overridden by the runner's configurable delay, but also embedded
    #  in the event timestamps for realistic ordering)
    _STEP_INTERVAL_SECONDS: int = 30

    @property
    def name(self) -> str:
        return "CustomerRequestSimulation"

    def generate_events(self, session_id: str, repetition_index: int = 0) -> Iterator[ActivityEvent]:
        """
        Yield 7 ActivityEvents for one 'Process Customer Request' workflow run.

        Args:
            session_id:        Unique session identifier for this run.
            repetition_index:  Which demo email/customer to use (cycles modulo 3).

        Yields:
            ActivityEvent objects, oldest first, with ordered timestamps.
        """
        email_data = get_demo_email(repetition_index)
        customer = get_demo_customer(email_data["customer_email"])

        # Base timestamp — we spread events across realistic intervals
        base_ts = datetime.now(timezone.utc)

        def ts(step: int) -> datetime:
            """Return a timestamp 'step * interval' seconds after base."""
            return base_ts + timedelta(seconds=step * self._STEP_INTERVAL_SECONDS)

        # ------------------------------------------------------------------
        # Step 1: Gmail application opened
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.application,
            application="Gmail",
            action="opened",
            target="Gmail",
            session_id=session_id,
            timestamp=ts(0),
            metadata={
                "window_title": "Gmail - Inbox",
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 2: Customer email opened
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.email,
            application="Gmail",
            action="open_email",
            target=email_data["customer_email"],
            session_id=session_id,
            timestamp=ts(1),
            metadata={
                "email_id": email_data["email_id"],
                "subject": email_data["subject"],
                "from": email_data["customer_email"],
                "customer_name": email_data["customer_name"],
                "has_attachment": True,
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 3: Attachment downloaded
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.file,
            application="Gmail",
            action="download",
            target=email_data["attachment"],
            session_id=session_id,
            timestamp=ts(2),
            metadata={
                "email_id": email_data["email_id"],
                "file_name": email_data["attachment"],
                "file_size_kb": email_data["attachment_size_kb"],
                "download_path": f"~/Downloads/{email_data['attachment']}",
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 4: CRM application opened
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.application,
            application="CRM",
            action="opened",
            target="CRM Dashboard",
            session_id=session_id,
            timestamp=ts(3),
            metadata={
                "window_title": "CRM - Dashboard",
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 5: Customer searched in CRM
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.crm,
            application="CRM",
            action="find_customer",
            target=email_data["customer_email"],
            session_id=session_id,
            timestamp=ts(4),
            metadata={
                "search_query": email_data["customer_email"],
                "customer_id": customer["customer_id"],
                "customer_name": customer["name"],
                "customer_found": True,
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 6: Customer record updated in CRM
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.crm,
            application="CRM",
            action="update_customer",
            target=email_data["customer_email"],
            session_id=session_id,
            timestamp=ts(5),
            metadata={
                "customer_id": customer["customer_id"],
                "customer_name": customer["name"],
                "update_fields": ["last_request", "request_status", "attachment"],
                "request_subject": email_data["subject"],
                "attachment": email_data["attachment"],
                "source": "simulation",
            },
        )

        # ------------------------------------------------------------------
        # Step 7: Slack notification sent
        # ------------------------------------------------------------------
        yield ActivityEvent(
            event_type=EventType.slack,
            application="Slack",
            action="send_message",
            target=email_data["slack_channel"],
            session_id=session_id,
            timestamp=ts(6),
            metadata={
                "channel": email_data["slack_channel"],
                "message": email_data["slack_message"],
                "customer_id": customer["customer_id"],
                "triggered_by": "customer_request_workflow",
                "source": "simulation",
            },
        )
