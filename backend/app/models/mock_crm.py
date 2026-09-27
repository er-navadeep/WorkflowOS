"""
Mock CRM Storage - Phase 8.8 / 8.9
=====================================
Local MongoDB persistence for the WorkFlowOS mock CRM.

Collection: mock_crm_customers

Indexes:
    - customer_id (unique)         - primary CRM identifier
    - customer_identifier (unique) - lookup key (usually email)
    - email (sparse)               - additional lookup field

Purpose:
    Provides a deterministic, controlled local CRM data source for
    integration testing of CRM adapter actions (find_customer, update_customer).

Security:
    - Contains only synthetic .test-domain records.
    - No real personal data, no passwords, no credentials.
    - Isolated from real user data via a dedicated collection.
    - update_customer uses an explicit field allowlist; MongoDB operators
      ($set, $push, $pull, etc.) in user input are always rejected.
"""


from __future__ import annotations


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.database.mongodb import get_database

logger = logging.getLogger(__name__)

COLLECTION_NAME = "mock_crm_customers"
_indexes_created: bool = False

# ---------------------------------------------------------------------------
# Update field allowlist (Phase 8.9)
# ---------------------------------------------------------------------------

# ONLY these fields may be modified by update_customer.
# Immutable identity fields (customer_id, customer_identifier, email,
# name, company, created_at) are never updated through the workflow input.
# Notes is added deliberately here for Phase 8.9 (stored as a string).
ALLOWED_UPDATE_FIELDS: frozenset = frozenset({"status", "notes"})

# Allowed status values - reject arbitrary strings
ALLOWED_STATUS_VALUES: frozenset = frozenset({
    "active",
    "inactive",
    "contacted",
    "processed",
    "pending",
    "closed",
})

# Maximum length for the notes field
MAX_NOTES_LENGTH: int = 500

# ---------------------------------------------------------------------------
# Deterministic synthetic test customers
# All use .test domains - never real personal information.
# ---------------------------------------------------------------------------

SEED_CUSTOMERS: List[Dict[str, Any]] = [
    {
        "customer_id": "CUST-1001",
        "customer_identifier": "alice@example.test",
        "name": "Alice Test",
        "email": "alice@example.test",
        "company": "Example Corporation",
        "status": "active",
        "created_at": datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
    },
    {
        "customer_id": "CUST-1002",
        "customer_identifier": "bob@acme.test",
        "name": "Bob Mock",
        "email": "bob@acme.test",
        "company": "Acme Inc",
        "status": "active",
        "created_at": datetime(2024, 2, 20, 11, 30, 0, tzinfo=timezone.utc),
    },
    {
        "customer_id": "CUST-1003",
        "customer_identifier": "carol@widgets.test",
        "name": "Carol Dummy",
        "email": "carol@widgets.test",
        "company": "Widgets Ltd",
        "status": "inactive",
        "created_at": datetime(2024, 3, 5, 14, 0, 0, tzinfo=timezone.utc),
    },
    {
        "customer_id": "CUST-1004",
        "customer_identifier": "nav@example.test",
        "name": "Test Customer",
        "email": "nav@example.test",
        "company": "Example Corporation",
        "status": "active",
        "created_at": datetime(2024, 4, 10, 8, 0, 0, tzinfo=timezone.utc),
    },
    {
        "customer_id": "CUST-1005",
        "customer_identifier": "dave@enterprise.test",
        "name": "Dave Enterprise",
        "email": "dave@enterprise.test",
        "company": "Enterprise Solutions",
        "status": "active",
        "created_at": datetime(2024, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
    },
]


# ---------------------------------------------------------------------------
# Collection & Index Management
# ---------------------------------------------------------------------------

def _get_collection() -> Collection:
    """Return the mock_crm_customers collection, ensuring required indexes exist."""
    db = get_database()
    col: Collection = db[COLLECTION_NAME]
    global _indexes_created
    if not _indexes_created:
        try:
            col.create_index(
                [("customer_id", ASCENDING)],
                name="idx_crm_customer_id",
                unique=True,
            )
            col.create_index(
                [("customer_identifier", ASCENDING)],
                name="idx_crm_customer_identifier",
                unique=True,
            )
            col.create_index(
                [("email", ASCENDING)],
                name="idx_crm_email",
                sparse=True,
            )
            _indexes_created = True
            logger.info("Mock CRM indexes ensured on collection '%s'.", COLLECTION_NAME)
        except PyMongoError as exc:
            logger.warning("Could not create mock CRM indexes: %s", exc)
    return col


# ---------------------------------------------------------------------------
# Seed / Initialization
# ---------------------------------------------------------------------------

def ensure_seed_data() -> int:
    """
    Idempotently insert the deterministic synthetic test customers.

    Uses update_one with upsert=True keyed on customer_id so repeated
    calls are safe and do not create duplicate records.

    Returns the number of records upserted (new inserts only).
    """
    col = _get_collection()
    upserted = 0
    for customer in SEED_CUSTOMERS:
        try:
            result = col.update_one(
                {"customer_id": customer["customer_id"]},
                {"$setOnInsert": customer},
                upsert=True,
            )
            if result.upserted_id is not None:
                upserted += 1
        except PyMongoError as exc:
            logger.warning(
                "Could not upsert seed customer %s: %s",
                customer.get("customer_id"),
                exc,
            )
    logger.info(
        "Mock CRM seed: %d new records inserted (%d total seed records).",
        upserted,
        len(SEED_CUSTOMERS),
    )
    return upserted


# ---------------------------------------------------------------------------
# Query Operations
# ---------------------------------------------------------------------------

def find_customer_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Find a single customer by their customer_identifier (or email).

    Performs an exact-match lookup - no fuzzy search, no wildcard.
    Returns the customer document (without MongoDB _id) or None if not found.
    """
    if not identifier or not identifier.strip():
        return None

    normalized = identifier.strip().lower()
    col = _get_collection()

    try:
        doc = col.find_one(
            {
                "$or": [
                    {"customer_identifier": normalized},
                    {"email": normalized},
                    {"customer_id": identifier.strip().upper()},
                ]
            },
            {"_id": 0},
        )
        return doc
    except PyMongoError as exc:
        logger.error("Mock CRM lookup failed for identifier '%s': %s", normalized, exc)
        raise CRMStorageError(f"Database error during customer lookup: {exc}") from exc


def list_all_customers() -> List[Dict[str, Any]]:
    """Return all mock CRM customers (without _id). For admin/testing only."""
    col = _get_collection()
    try:
        return list(col.find({}, {"_id": 0}))
    except PyMongoError as exc:
        logger.error("Mock CRM list_all failed: %s", exc)
        raise CRMStorageError(f"Database error listing customers: {exc}") from exc


def get_customer_count() -> int:
    """Return the total number of customers in the mock CRM collection."""
    col = _get_collection()
    try:
        return col.count_documents({})
    except PyMongoError as exc:
        logger.error("Mock CRM count failed: %s", exc)
        return 0


def update_customer_by_identifier(
    identifier: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Safely update a customer record identified by customer_identifier or email.

    Security invariants:
      - Only fields listed in ALLOWED_UPDATE_FIELDS may be written.
      - No MongoDB operators ($set, $push, $unset, etc.) are accepted in field
        names or values — they are explicitly rejected before any DB call.
      - status values are validated against ALLOWED_STATUS_VALUES.
      - notes values are validated as plain strings within MAX_NOTES_LENGTH.
      - Immutable fields (customer_id, email, name, company, created_at,
        customer_identifier) are never overwritten.

    Returns:
        The updated customer document (without _id) if the customer was found
        and the update succeeded.
        None if no customer matches the identifier.

    Raises:
        CRMStorageError on database errors.
        ValueError on invalid field names, MongoDB operators, or bad values.
    """
    if not identifier or not identifier.strip():
        raise ValueError("identifier must be non-empty")
    if not updates:
        raise ValueError("updates dict must be non-empty")

    # ------------------------------------------------------------------
    # Injection prevention: reject any key or value that looks like a
    # MongoDB operator ($anything) before touching the database.
    # ------------------------------------------------------------------
    for field, value in updates.items():
        if not isinstance(field, str):
            raise ValueError(f"Update field names must be strings, got: {type(field).__name__}")
        if field.startswith("$"):
            raise ValueError(
                f"MongoDB operator '{field}' is not permitted as an update field."
            )
        if isinstance(value, str) and value.startswith("$"):
            raise ValueError(
                f"MongoDB operator in value for field '{field}' is not permitted."
            )
        # Reject dict values that are MongoDB expressions
        if isinstance(value, dict):
            for k in value:
                if isinstance(k, str) and k.startswith("$"):
                    raise ValueError(
                        f"MongoDB operator '{k}' in nested value for '{field}' is not permitted."
                    )

    # ------------------------------------------------------------------
    # Allowlist check: only ALLOWED_UPDATE_FIELDS accepted
    # ------------------------------------------------------------------
    unknown_fields = set(updates.keys()) - ALLOWED_UPDATE_FIELDS
    if unknown_fields:
        raise ValueError(
            f"Update contains disallowed field(s): {sorted(unknown_fields)}. "
            f"Allowed fields are: {sorted(ALLOWED_UPDATE_FIELDS)}."
        )

    # ------------------------------------------------------------------
    # Per-field value validation
    # ------------------------------------------------------------------
    validated: Dict[str, Any] = {}
    for field, value in updates.items():
        if field == "status":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("'status' must be a non-empty string.")
            normalized_status = value.strip().lower()
            if normalized_status not in ALLOWED_STATUS_VALUES:
                raise ValueError(
                    f"Invalid status value '{value}'. "
                    f"Allowed values: {sorted(ALLOWED_STATUS_VALUES)}."
                )
            validated["status"] = normalized_status

        elif field == "notes":
            if not isinstance(value, str):
                raise ValueError("'notes' must be a string.")
            if len(value) > MAX_NOTES_LENGTH:
                raise ValueError(
                    f"'notes' exceeds maximum length of {MAX_NOTES_LENGTH} characters."
                )
            validated["notes"] = value

    # ------------------------------------------------------------------
    # Database update (targeted single-document update only)
    # ------------------------------------------------------------------
    normalized_id = identifier.strip().lower()
    col = _get_collection()

    # Add update timestamp
    validated["updated_at"] = datetime.now(timezone.utc)

    try:
        result = col.find_one_and_update(
            {
                "$or": [
                    {"customer_identifier": normalized_id},
                    {"email": normalized_id},
                    {"customer_id": identifier.strip().upper()},
                ]
            },
            {"$set": validated},       # we construct $set ourselves — never from user input
            return_document=True,      # return the updated document
            projection={"_id": 0},
        )
        return result  # None if no document matched
    except PyMongoError as exc:
        logger.error(
            "Mock CRM update_customer failed for identifier '%s': %s", normalized_id, exc
        )
        raise CRMStorageError(f"Database error during customer update: {exc}") from exc


def restore_customer_to_seed(customer_id: str) -> bool:
    """
    Restore a single customer to its deterministic seed state.

    Looks up the seed record by customer_id and replaces the mutable fields
    (status, notes, updated_at) with the original seed values.

    Used by the Phase 8.9 verification script to clean up after the test run.
    Returns True if the record was found and restored, False otherwise.
    """
    seed = next(
        (
            s for s in SEED_CUSTOMERS
            if s["customer_id"] == customer_id
            or s["customer_identifier"] == customer_id
            or s.get("email") == customer_id
        ),
        None,
    )
    if seed is None:
        logger.warning("restore_customer_to_seed: no seed record for '%s'.", customer_id)
        return False

    col = _get_collection()
    reset_doc = {
        "status": seed.get("status", "active"),
        "notes": None,        # notes field did not exist in original seed
        "updated_at": None,   # clear the Phase 8.9 update timestamp
    }
    try:
        target_id = seed["customer_id"]
        result = col.update_one(
            {"customer_id": target_id},
            {
                "$set": {"status": reset_doc["status"]},
                "$unset": {"notes": "", "updated_at": ""},
            },
        )
        if result.matched_count == 0:
            logger.warning("restore_customer_to_seed: no document matched '%s'.", target_id)
            return False
        logger.info("Restored customer '%s' to seed state.", target_id)
        return True
    except PyMongoError as exc:
        logger.error("restore_customer_to_seed failed for '%s': %s", customer_id, exc)
        return False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CRMStorageError(Exception):
    """Raised when the mock CRM storage layer encounters an unrecoverable error."""
