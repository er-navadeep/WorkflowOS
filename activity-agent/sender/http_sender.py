"""
Activity Agent — HTTP Event Sender
=====================================
Responsible for POSTing ActivityEvent objects to the WorkFlowOS backend API.

Supports:
    - Single event send  → POST /api/v1/events
    - Batch send         → POST /api/v1/events/batch
    - Retry with backoff on transient failures (connection error, 5xx)
    - Health check before sending
    - Structured error reporting (never crashes the agent on network errors)

Dependencies:
    - requests (already in requirements.txt as a common Python package)
    - AgentConfig (from agent.config)
"""

from __future__ import annotations

import logging
import sys
import os
import time
from typing import List, Optional, Tuple

import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

# Ensure backend schemas are importable
_backend_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from app.schemas.activity_event import ActivityEvent  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class SendResult:
    """Encapsulates the result of a send attempt."""

    __slots__ = ("success", "event_id", "status_code", "error")

    def __init__(
        self,
        success: bool,
        event_id: str = "",
        status_code: int = 0,
        error: str = "",
    ) -> None:
        self.success = success
        self.event_id = event_id
        self.status_code = status_code
        self.error = error

    def __repr__(self) -> str:
        if self.success:
            return f"SendResult(OK, event_id={self.event_id})"
        return f"SendResult(FAIL, status={self.status_code}, error={self.error!r})"


# ---------------------------------------------------------------------------
# HTTP Sender
# ---------------------------------------------------------------------------

class HttpEventSender:
    """
    Sends ActivityEvent objects to the WorkFlowOS backend via HTTP.

    Usage:
        sender = HttpEventSender(config)
        result = sender.send(event)
        if not result.success:
            print(f"Send failed: {result.error}")
    """

    def __init__(self, config) -> None:  # config: AgentConfig
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "WorkFlowOS-ActivityAgent/0.1",
        })

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def check_backend_health(self) -> Tuple[bool, str]:
        """
        Ping the backend health endpoint.

        Returns:
            (True, status_message) if reachable and healthy
            (False, error_message) if unreachable or unhealthy
        """
        try:
            resp = self._session.get(
                self._config.health_endpoint,
                timeout=self._config.http_timeout_seconds,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, f"Backend healthy — DB: {data.get('database', 'unknown')}"
            return False, f"Backend returned HTTP {resp.status_code}"
        except (ConnectionError, Timeout) as exc:
            return False, f"Cannot reach backend: {exc}"
        except RequestException as exc:
            return False, f"Request error: {exc}"

    def send(self, event: ActivityEvent) -> SendResult:
        """
        Send a single ActivityEvent to POST /api/v1/events.

        Retries on transient failures (connection errors, 5xx).

        Returns:
            SendResult with success flag and event_id or error.
        """
        payload = self._event_to_payload(event)
        return self._post_with_retry(
            url=self._config.events_endpoint,
            payload=payload,
            event_id=event.event_id,
        )

    def send_batch(self, events: List[ActivityEvent]) -> Tuple[int, int]:
        """
        Send a list of ActivityEvents as a batch to POST /api/v1/events/batch.

        Returns:
            (inserted_count, failed_count) tuple
        """
        if not events:
            return 0, 0

        payload = {
            "events": [self._event_to_payload(e) for e in events]
        }

        try:
            resp = self._session.post(
                self._config.batch_endpoint,
                json=payload,
                timeout=self._config.http_timeout_seconds,
            )
            if resp.status_code == 201:
                data = resp.json()
                inserted = data.get("inserted", 0)
                logger.info("Batch send: %d events inserted.", inserted)
                return inserted, len(events) - inserted
            else:
                logger.error(
                    "Batch send failed HTTP %d: %s", resp.status_code, resp.text[:200]
                )
                return 0, len(events)
        except RequestException as exc:
            logger.error("Batch send request error: %s", exc)
            return 0, len(events)

    def close(self) -> None:
        """Release the underlying requests.Session."""
        self._session.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _event_to_payload(self, event: ActivityEvent) -> dict:
        """Convert an ActivityEvent to a JSON-serialisable dict."""
        data = event.model_dump()
        # Serialise the EventType enum to its string value
        if hasattr(data.get("event_type"), "value"):
            data["event_type"] = data["event_type"].value
        # Serialise datetime to ISO-8601 string
        if hasattr(data.get("timestamp"), "isoformat"):
            data["timestamp"] = data["timestamp"].isoformat()
        return data

    def _post_with_retry(
        self,
        url: str,
        payload: dict,
        event_id: str,
    ) -> SendResult:
        """POST payload to url with exponential backoff retry."""
        max_retries = self._config.http_max_retries
        timeout = self._config.http_timeout_seconds

        for attempt in range(1, max_retries + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=timeout)

                if resp.status_code == 201:
                    data = resp.json()
                    return SendResult(
                        success=True,
                        event_id=data.get("event_id", event_id),
                        status_code=201,
                    )

                # 4xx errors are client errors — do not retry
                if 400 <= resp.status_code < 500:
                    logger.error(
                        "Client error %d for event %s: %s",
                        resp.status_code,
                        event_id,
                        resp.text[:300],
                    )
                    return SendResult(
                        success=False,
                        event_id=event_id,
                        status_code=resp.status_code,
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )

                # 5xx — retry with backoff
                logger.warning(
                    "Server error %d (attempt %d/%d) for event %s",
                    resp.status_code,
                    attempt,
                    max_retries,
                    event_id,
                )

            except (ConnectionError, Timeout) as exc:
                logger.warning(
                    "Network error attempt %d/%d for event %s: %s",
                    attempt,
                    max_retries,
                    event_id,
                    exc,
                )
                if attempt == max_retries:
                    return SendResult(
                        success=False,
                        event_id=event_id,
                        error=f"Network error after {max_retries} retries: {exc}",
                    )

            except RequestException as exc:
                return SendResult(
                    success=False,
                    event_id=event_id,
                    error=f"Unexpected request error: {exc}",
                )

            # Exponential backoff: 1s, 2s, 4s ...
            if attempt < max_retries:
                sleep_time = 2 ** (attempt - 1)
                logger.debug("Retrying in %ds...", sleep_time)
                time.sleep(sleep_time)

        return SendResult(
            success=False,
            event_id=event_id,
            error=f"Failed after {max_retries} attempts",
        )
