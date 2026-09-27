#!/usr/bin/env python3
"""
WorkFlowOS — Phase 8.4: Gmail OAuth Verification Script
======================================================
Verifies OAuth 2.0 credentials and read-only connectivity to Gmail.

Security Constraints:
- Read-only verification ONLY (calls users.getProfile).
- Does NOT read email messages, subjects, or bodies.
- Does NOT send, modify, delete, archive, or alter any emails.
- NEVER prints client secret, refresh token, access token, or credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment from root .env and backend/.env
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "backend" / ".env")

REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def verify_gmail_oauth(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    user_id: str = "me",
) -> Dict[str, Any]:
    """
    Authenticate using refresh token and call Gmail users.getProfile.

    Returns a dictionary of safe profile metadata.
    Raises ValueError, RuntimeError, or GoogleAuthError on failure.
    """
    if not client_id or not client_id.strip():
        raise ValueError("Missing GOOGLE_CLIENT_ID")
    if not client_secret or not client_secret.strip():
        raise ValueError("Missing GOOGLE_CLIENT_SECRET")
    if not refresh_token or not refresh_token.strip():
        raise ValueError("Missing GOOGLE_REFRESH_TOKEN")

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            f"Required Google library missing: {e}. "
            "Please ensure google-auth and google-api-python-client are installed."
        ) from e

    # Create credentials instance with strict read-only scope
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[REQUIRED_SCOPE],
    )

    # Force refresh token exchange
    try:
        request = Request()
        creds.refresh(request)
    except Exception as exc:
        raise RuntimeError(f"OAuth refresh token exchange failed: {type(exc).__name__}: {exc}") from exc

    if not creds.token:
        raise RuntimeError("OAuth refresh succeeded but no access token was acquired.")

    # Call Gmail profile endpoint (minimal safe read-only call)
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId=user_id).execute()
    except Exception as exc:
        raise RuntimeError(f"Gmail API users.getProfile call failed: {type(exc).__name__}: {exc}") from exc

    return {
        "status": "success",
        "email_address": profile.get("emailAddress", "unknown"),
        "messages_total": profile.get("messagesTotal", 0),
        "threads_total": profile.get("threadsTotal", 0),
        "history_id": profile.get("historyId", ""),
        "scope": REQUIRED_SCOPE,
    }


def main() -> int:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    user_id = os.getenv("GMAIL_USER_ID", "me").strip() or "me"

    missing = []
    if not client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not refresh_token:
        missing.append("GOOGLE_REFRESH_TOKEN")

    if missing:
        print("================================================================================", file=sys.stderr)
        print("WorkFlowOS - Gmail OAuth Verification: Missing Configuration", file=sys.stderr)
        print("================================================================================", file=sys.stderr)
        print(f"Error: Missing required environment variable(s): {', '.join(missing)}", file=sys.stderr)
        print("Please ensure your .env or backend/.env contains these variables.", file=sys.stderr)
        return 1

    try:
        result = verify_gmail_oauth(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            user_id=user_id,
        )
    except Exception as exc:
        # Sanitize any accidental secret leakage
        err_msg = str(exc)
        if client_secret:
            err_msg = err_msg.replace(client_secret, "[REDACTED_CLIENT_SECRET]")
        if refresh_token:
            err_msg = err_msg.replace(refresh_token, "[REDACTED_REFRESH_TOKEN]")

        print("================================================================================", file=sys.stderr)
        print("WorkFlowOS - Gmail OAuth Verification FAILED", file=sys.stderr)
        print("================================================================================", file=sys.stderr)
        print(f"Error details: {err_msg}", file=sys.stderr)
        return 1

    print("================================================================================")
    print("WorkFlowOS - Gmail OAuth Verification")
    print("================================================================================")
    print("OAuth authentication successful.")
    print("Gmail API connection successful.")
    print(f"Authenticated mailbox: {result['email_address']}")
    print(f"Total messages in mailbox: {result['messages_total']}")
    print(f"Verified Scope: {result['scope']}")
    print("================================================================================")
    print("Verification completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
