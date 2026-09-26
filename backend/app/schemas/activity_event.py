"""
Activity Event Schema
=====================
Pydantic models for validating incoming activity events.

Every observed user action (opening an app, clicking a button,
downloading a file, updating CRM, sending a Slack message, etc.)
is normalized into a structured ActivityEvent before storage.

Event Types:
    application  - Application opened / closed / focused
    browser      - Browser navigation / tab events
    file         - File created / downloaded / moved / deleted
    ui           - Generic UI interaction (click, scroll, form fill)
    email        - Email opened / replied / forwarded
    crm          - CRM search / update / create
    slack        - Slack message sent / channel visited
    form         - Form filled / submitted
    system       - System-level events (login, shutdown, etc.)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Allowed event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    application = "application"
    browser = "browser"
    file = "file"
    ui = "ui"
    email = "email"
    crm = "crm"
    slack = "slack"
    form = "form"
    system = "system"


# ---------------------------------------------------------------------------
# Core ActivityEvent schema (used for both ingest and storage)
# ---------------------------------------------------------------------------

class ActivityEvent(BaseModel):
    """
    Structured representation of a single observed user activity.

    All fields marked Optional have sensible defaults so that simulated /
    demo events can omit them without breaking validation.
    """

    # --- Identity ---
    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique event identifier. Auto-generated if not provided.",
        examples=["evt-3f4a1b2c-0000-0000-0000-000000000001"],
    )

    # --- Classification ---
    event_type: EventType = Field(
        ...,
        description="Category of the observed event.",
        examples=["email", "crm", "slack"],
    )

    application: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Human-readable name of the application that produced this event.",
        examples=["Gmail", "CRM", "Slack"],
    )

    action: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Verb describing what happened.",
        examples=["open_email", "find_customer", "send_message"],
    )

    target: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="The entity the action was performed on.",
        examples=["customer@example.com", "#support", "request.pdf"],
    )

    # --- Session grouping ---
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "Groups all events belonging to one workflow execution attempt. "
            "All events from the same run of a pattern should share this ID."
        ),
        examples=["session-demo-001"],
    )

    # --- Time ---
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of when the event occurred. Auto-set if omitted.",
    )

    # --- Optional enrichment ---
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Arbitrary key-value pairs carrying application-specific context. "
            "e.g. {'email_subject': 'Customer Request', 'file_size_kb': 42}"
        ),
    )

    # --- Pydantic config ---
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "email",
                    "application": "Gmail",
                    "action": "open_email",
                    "target": "customer@example.com",
                    "session_id": "session-demo-001",
                    "metadata": {"subject": "Customer Request"},
                }
            ]
        }
    }

    # --- Validators ---

    @field_validator("application", "action", "target", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove accidental leading/trailing whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """
        Accept ISO-8601 strings or datetime objects.
        Always ensure the result is timezone-aware (UTC).
        """
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        elif isinstance(v, datetime):
            dt = v
        else:
            raise ValueError(f"Cannot parse timestamp from {type(v)}: {v!r}")

        if dt.tzinfo is None:
            # Treat naive datetimes as UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @model_validator(mode="after")
    def validate_event_id_format(self) -> "ActivityEvent":
        """Ensure event_id is a non-empty string (already guaranteed by Field)."""
        if not self.event_id or not self.event_id.strip():
            self.event_id = str(uuid4())
        return self


# ---------------------------------------------------------------------------
# Batch ingest schema
# ---------------------------------------------------------------------------

class ActivityEventBatch(BaseModel):
    """Wraps a list of events for the batch ingest endpoint."""

    events: List[ActivityEvent] = Field(
        ...,
        min_length=1,
        description="One or more activity events to ingest in a single request.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "events": [
                        {
                            "event_type": "email",
                            "application": "Gmail",
                            "action": "open_email",
                            "target": "customer@example.com",
                            "session_id": "session-demo-001",
                        },
                        {
                            "event_type": "file",
                            "application": "Gmail",
                            "action": "download",
                            "target": "request.pdf",
                            "session_id": "session-demo-001",
                        },
                    ]
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Query / filter schema (used by GET /api/v1/events)
# ---------------------------------------------------------------------------

class ActivityEventFilter(BaseModel):
    """Optional filters for listing stored activity events."""

    session_id: Optional[str] = Field(None, description="Filter by session ID.")
    event_type: Optional[EventType] = Field(None, description="Filter by event type.")
    application: Optional[str] = Field(None, description="Filter by application name.")
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Maximum number of events to return (1–1000).",
    )
    skip: int = Field(
        0,
        ge=0,
        description="Number of events to skip (for pagination).",
    )


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------

class ActivityEventResponse(BaseModel):
    """Single-event ingest response."""

    success: bool
    event_id: str
    message: str


class ActivityEventBatchResponse(BaseModel):
    """Batch ingest response."""

    success: bool
    inserted: int
    event_ids: List[str]
    message: str
