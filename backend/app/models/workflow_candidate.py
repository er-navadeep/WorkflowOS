"""
WorkflowCandidate Model
========================
Represents a workflow pattern that the Discovery Engine has detected
from repeated activity event sequences.

A candidate is NOT yet approved. It sits in status "discovered" until
the user reviews and approves or rejects it (Phase 7).

MongoDB collection: workflow_candidates

Uniqueness:
    Candidates are keyed on sequence_fingerprint — a deterministic hash of
    the normalised action sequence. Re-running discovery on the same data
    updates the existing candidate rather than inserting duplicates.

Scoring (fully deterministic — no AI):
    score = weighted average of:
        - occurrence_factor   (more occurrences = higher score, capped)
        - similarity          (average pairwise similarity of sessions)
        - coverage_factor     (more applications = more cross-app value)
        - length_factor       (longer sequences have more automation value)

    All factors are in [0, 1]. The weights are documented in scorer.py.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database

logger = logging.getLogger(__name__)

COLLECTION_NAME = "workflow_candidates"

# ------------------- index guard -------------------------------------------
_indexes_created: bool = False


def _get_collection() -> Collection:
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    global _indexes_created
    if not _indexes_created:
        try:
            col.create_index(
                [("sequence_fingerprint", ASCENDING)],
                name="idx_fingerprint",
                unique=True,
            )
            col.create_index([("status", ASCENDING)], name="idx_status")
            col.create_index([("score", ASCENDING)], name="idx_score")
            _indexes_created = True
        except PyMongoError as exc:
            logger.warning("Could not create workflow_candidates indexes: %s", exc)
    return col


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class SequenceStep(BaseModel):
    """One normalised step in a discovered sequence."""
    order: int
    event_type: str
    application: str
    action: str


class CandidateEvidence(BaseModel):
    """Transparent evidence used to derive the candidate score."""
    occurrence_count: int = Field(description="Number of sessions this pattern was observed.")
    sequence_similarity: float = Field(description="Average pairwise Jaccard similarity (0-1).")
    application_count: int = Field(description="Number of distinct applications involved.")
    sequence_length: int = Field(description="Number of steps in the sequence.")
    occurrence_factor: float = Field(description="Normalised occurrence weight (0-1).")
    coverage_factor: float = Field(description="Normalised application-count weight (0-1).")
    length_factor: float = Field(description="Normalised sequence-length weight (0-1).")


class WorkflowCandidate(BaseModel):
    """
    A workflow pattern detected by the Discovery Engine.

    Status lifecycle (controlled by later phases):
        discovered -> pending_approval -> approved | rejected
    """

    candidate_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique candidate identifier.",
    )
    sequence_fingerprint: str = Field(
        description=(
            "SHA-256 hash of the normalised step sequence. "
            "Used for upsert deduplication."
        ),
    )

    # --- Human-readable identity ---
    name: str = Field(description="Deterministic or AI-generated candidate name.")
    description: str = Field(default="", description="Optional explanation of the workflow.")

    # --- Pattern evidence ---
    occurrence_count: int = Field(description="How many sessions matched this pattern.")
    session_ids: List[str] = Field(default_factory=list, description="Session IDs that matched.")
    applications: List[str] = Field(description="Distinct applications involved (ordered).")
    sequence: List[SequenceStep] = Field(description="Normalised step sequence.")

    # --- Timing ---
    first_seen: datetime = Field(description="Timestamp of earliest matching event.")
    last_seen: datetime = Field(description="Timestamp of latest matching event.")
    average_duration_seconds: float = Field(
        description="Mean seconds from first to last event across sessions."
    )

    # --- Scoring ---
    similarity: float = Field(description="Average pairwise similarity across matching sessions.")
    score: float = Field(description="Composite discovery confidence score [0,1].")
    evidence: CandidateEvidence = Field(description="Transparent breakdown of scoring factors.")

    # --- Lifecycle ---
    status: str = Field(default="discovered")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"json_schema_extra": {"examples": []}}


# ---------------------------------------------------------------------------
# Fingerprint helper (public — used by discovery modules)
# ---------------------------------------------------------------------------

def build_fingerprint(steps: List[Dict[str, str]]) -> str:
    """
    Create a deterministic SHA-256 fingerprint for a normalised step sequence.

    Input format (each dict):
        {"event_type": "email", "application": "Gmail", "action": "open_email"}

    The fingerprint is stable across runs so that re-running discovery on the
    same pattern produces the same fingerprint and triggers an upsert.
    """
    canonical = "|".join(
        f"{s.get('event_type','')}/{s.get('application','')}/{s.get('action','')}"
        for s in steps
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# MongoDB storage operations
# ---------------------------------------------------------------------------

def upsert_candidate(candidate: WorkflowCandidate) -> str:
    """
    Insert or update a candidate keyed on sequence_fingerprint.

    If a candidate with the same fingerprint already exists:
        - update occurrence_count, session_ids, score, evidence, updated_at
        - preserve the original candidate_id and created_at
    If it is new:
        - insert the full document

    Returns:
        The candidate_id of the inserted / updated document.
    """
    col = _get_collection()
    doc = candidate.model_dump()

    # Serialise datetimes
    for key in ("first_seen", "last_seen", "created_at", "updated_at"):
        if isinstance(doc.get(key), datetime):
            pass  # pymongo handles datetime natively

    # Fields to update on match
    update_fields = {
        "occurrence_count": doc["occurrence_count"],
        "session_ids": doc["session_ids"],
        "applications": doc["applications"],
        "sequence": doc["sequence"],
        "first_seen": doc["first_seen"],
        "last_seen": doc["last_seen"],
        "average_duration_seconds": doc["average_duration_seconds"],
        "similarity": doc["similarity"],
        "score": doc["score"],
        "evidence": doc["evidence"],
        "updated_at": doc["updated_at"],
    }

    try:
        result = col.update_one(
            {"sequence_fingerprint": candidate.sequence_fingerprint},
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "candidate_id": doc["candidate_id"],
                    "sequence_fingerprint": doc["sequence_fingerprint"],
                    "name": doc["name"],
                    "description": doc["description"],
                    "status": doc["status"],
                    "created_at": doc["created_at"],
                },
            },
            upsert=True,
        )
        if result.upserted_id:
            logger.info("Inserted new candidate: %s (%s)", candidate.name, candidate.sequence_fingerprint)
        else:
            logger.info("Updated existing candidate: %s (%s)", candidate.name, candidate.sequence_fingerprint)
        return candidate.candidate_id
    except PyMongoError as exc:
        logger.error("Failed to upsert candidate: %s", exc)
        raise RuntimeError(f"Candidate upsert failed: {exc}") from exc


def get_all_candidates(status: Optional[str] = None) -> List[WorkflowCandidate]:
    """Return all stored candidates, optionally filtered by status."""
    col = _get_collection()
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    try:
        docs = list(col.find(query).sort("score", -1))
        candidates = []
        for doc in docs:
            doc.pop("_id", None)
            candidates.append(WorkflowCandidate.model_validate(doc))
        return candidates
    except PyMongoError as exc:
        logger.error("Failed to fetch candidates: %s", exc)
        raise RuntimeError(f"Candidate fetch failed: {exc}") from exc


def get_candidate_by_id(candidate_id: str) -> Optional[WorkflowCandidate]:
    """Return a single candidate by candidate_id."""
    col = _get_collection()
    try:
        doc = col.find_one({"candidate_id": candidate_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowCandidate.model_validate(doc)
    except PyMongoError as exc:
        logger.error("Failed to fetch candidate %s: %s", candidate_id, exc)
        raise RuntimeError(f"Candidate fetch failed: {exc}") from exc


def get_candidate_by_fingerprint(fingerprint: str) -> Optional[WorkflowCandidate]:
    """Return a candidate matching a sequence fingerprint."""
    col = _get_collection()
    try:
        doc = col.find_one({"sequence_fingerprint": fingerprint})
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowCandidate.model_validate(doc)
    except PyMongoError as exc:
        raise RuntimeError(f"Candidate fetch failed: {exc}") from exc


def count_candidates() -> int:
    """Return the total number of stored candidates."""
    return _get_collection().count_documents({})
