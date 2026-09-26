"""
Simulation Demo Data
=======================
Static, deterministic test data for the MVP demo.

IMPORTANT:
    This file contains ONLY demo/seed data.
    It must NEVER be imported by production logic.
    It exists solely to make the hackathon demonstration self-contained.

The data represents a realistic "Process Customer Request" scenario:
    - A customer sends an email with an attachment
    - The support worker reads the email
    - Downloads the attachment
    - Finds the customer in CRM
    - Updates the customer record
    - Notifies the support Slack channel
"""

from __future__ import annotations

from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# Demo customers
# ---------------------------------------------------------------------------

DEMO_CUSTOMERS: List[Dict[str, Any]] = [
    {
        "customer_id": "CUS-001",
        "name": "Acme Corp",
        "email": "support@acme.com",
        "plan": "Enterprise",
        "status": "active",
    },
    {
        "customer_id": "CUS-002",
        "name": "Globex Industries",
        "email": "contact@globex.io",
        "plan": "Pro",
        "status": "active",
    },
    {
        "customer_id": "CUS-003",
        "name": "Initech Solutions",
        "email": "hello@initech.dev",
        "plan": "Starter",
        "status": "trial",
    },
]


# ---------------------------------------------------------------------------
# Demo email requests (one per repetition cycle)
# ---------------------------------------------------------------------------

DEMO_EMAILS: List[Dict[str, Any]] = [
    {
        "email_id": "email-001",
        "customer_email": "support@acme.com",
        "customer_name": "Acme Corp",
        "subject": "Feature Request: Bulk Export",
        "body": "Hi, we need a bulk export feature for our monthly reports. Please advise.",
        "attachment": "acme_requirements.pdf",
        "attachment_size_kb": 128,
        "slack_channel": "#support",
        "slack_message": "[CRM Updated] Acme Corp — Feature Request: Bulk Export processed.",
    },
    {
        "email_id": "email-002",
        "customer_email": "contact@globex.io",
        "customer_name": "Globex Industries",
        "subject": "Integration Issue: Salesforce Sync",
        "body": "Our Salesforce sync stopped working after the last update. Logs attached.",
        "attachment": "globex_sync_logs.zip",
        "attachment_size_kb": 512,
        "slack_channel": "#support",
        "slack_message": "[CRM Updated] Globex Industries — Integration Issue: Salesforce Sync processed.",
    },
    {
        "email_id": "email-003",
        "customer_email": "hello@initech.dev",
        "customer_name": "Initech Solutions",
        "subject": "Onboarding Request: API Access",
        "body": "We would like API access enabled for our trial account. Request form enclosed.",
        "attachment": "initech_api_request.docx",
        "attachment_size_kb": 64,
        "slack_channel": "#support",
        "slack_message": "[CRM Updated] Initech Solutions — Onboarding Request: API Access processed.",
    },
]


def get_demo_email(index: int) -> Dict[str, Any]:
    """
    Return a demo email by repetition index.
    Cycles through DEMO_EMAILS if index exceeds the list length.
    """
    return DEMO_EMAILS[index % len(DEMO_EMAILS)]


def get_demo_customer(email: str) -> Dict[str, Any]:
    """
    Look up a demo customer by email address.
    Returns the first customer if not found (so the demo always works).
    """
    for c in DEMO_CUSTOMERS:
        if c["email"] == email:
            return c
    return DEMO_CUSTOMERS[0]
