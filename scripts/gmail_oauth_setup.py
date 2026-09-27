#!/usr/bin/env python3
"""
WorkFlowOS — Phase 8.4: Gmail OAuth Token Helper
=================================================
A secure local utility to perform OAuth 2.0 Installed Application authorization
for Gmail read-only access and obtain a refresh token.

Security & Safety Constraints:
- Uses ONLY scope: https://www.googleapis.com/auth/gmail.readonly
- NEVER prints Client Secret or Refresh Token to the console.
- NEVER commits credentials to Git (safeguarded by .gitignore).
- NEVER automatically modifies the active .env file.
- Saves generated tokens exclusively to an untracked local file (.gmail_token.local).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

# Hardcoded single read-only scope — NO modify or full access scopes permitted.
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [GMAIL_READONLY_SCOPE]

DEFAULT_OUTPUT_FILE = ".gmail_token.local"


def print_missing_credentials_guide(project_root: Path) -> None:
    """Print clear instructions explaining where to obtain and place credentials.json."""
    default_target = project_root / "credentials.json"
    guide = f"""
================================================================================
WorkFlowOS - Gmail OAuth Setup: Configuration File Missing
================================================================================
Google Desktop OAuth client credentials file was not found.

WHERE TO OBTAIN IT:
  1. Open Google Cloud Console:
     https://console.cloud.google.com/apis/credentials
  2. Ensure your WorkFlowOS project is selected.
  3. Under 'OAuth 2.0 Client IDs', locate your client:
     - Application type: Desktop app
  4. Click the 'Download JSON' icon on the right.

WHERE TO PLACE IT:
  Save the downloaded JSON file to your WorkFlowOS project root as:
    {default_target}

  OR pass the file path directly using the --credentials flag:
    python scripts/gmail_oauth_setup.py --credentials "path/to/client_secret.json"

SECURITY NOTE:
  Both credentials.json and generated token files are strictly ignored
  by .gitignore and will never be committed to source control.
================================================================================
"""
    print(guide, file=sys.stderr)


def find_credentials_file(project_root: Path, explicit_path: str | None) -> Path | None:
    """Locate the OAuth client secrets JSON file."""
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file():
            return p
        return None

    # Check default candidates in project root
    candidates = [
        project_root / "credentials.json",
        project_root / "client_secret.json",
    ]
    for c in candidates:
        if c.is_file():
            return c

    # Check for glob pattern client_secret*.json in project root
    matches = glob.glob(str(project_root / "client_secret*.json"))
    if matches:
        return Path(matches[0])

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WorkFlowOS - Gmail OAuth 2.0 Local Setup Helper (Read-Only Scope)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--credentials",
        "-c",
        dest="credentials_file",
        help="Path to downloaded Desktop OAuth client JSON (default: ./credentials.json or ./client_secret*.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        default=DEFAULT_OUTPUT_FILE,
        help="Untracked local output file to store generated tokens (default: .gmail_token.local)",
    )
    parser.add_argument(
        "--show-url",
        action="store_true",
        help="Display the authorization URL in terminal in addition to launching browser",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    # Locate credentials file
    cred_file = find_credentials_file(project_root, args.credentials_file)
    if not cred_file or not cred_file.is_file():
        print_missing_credentials_guide(project_root)
        sys.exit(1)

    # Check dependency
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Error: Required dependency 'google-auth-oauthlib' is not installed.\n"
            "Please install it using: pip install google-auth-oauthlib",
            file=sys.stderr,
        )
        sys.exit(1)

    # Initialize OAuth flow with ONLY gmail.readonly scope
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(cred_file),
            scopes=SCOPES,
        )
    except Exception as exc:
        print(f"Error: Failed to load OAuth client configuration: {exc}", file=sys.stderr)
        sys.exit(1)

    # Run installed-application local server flow
    auth_prompt = (
        "Please visit this URL to authorize this application: {url}"
        if args.show_url
        else None
    )

    try:
        flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
            authorization_prompt_message=auth_prompt,
            success_message="WorkFlowOS authorization complete! You may close this tab and return to your terminal.",
            open_browser=True,
        )
        creds = flow.credentials
    except Exception as exc:
        print(f"Error: OAuth authorization failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not creds or not creds.refresh_token:
        print(
            "Error: Google did not return an OAuth refresh token.\n"
            "Ensure you approved offline access on the Google consent screen.\n"
            "If you previously authorized this app, revoke access at:\n"
            "  https://myaccount.google.com/permissions\n"
            "and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Extract client identifiers safely
    client_id = creds.client_id or flow.client_config.get("client_id", "")
    client_secret = creds.client_secret or flow.client_config.get("client_secret", "")

    # Save to untracked local file (never committed to git)
    output_path = Path(args.output_file)
    if not output_path.is_absolute():
        output_path = project_root / output_path

    try:
        output_content = (
            "# =============================================================================\n"
            "# WorkFlowOS — Local Gmail OAuth Credentials (TEMPORARY)\n"
            "# =============================================================================\n"
            "# Generated by scripts/gmail_oauth_setup.py\n"
            "#\n"
            "# INSTRUCTIONS:\n"
            "# 1. Copy the values below into your local .env file:\n"
            "#\n"
            f"GOOGLE_CLIENT_ID={client_id}\n"
            f"GOOGLE_CLIENT_SECRET={client_secret}\n"
            f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}\n"
            "#\n"
            "# 2. Save your .env file.\n"
            "# 3. For security, delete this file (.gmail_token.local) after copying.\n"
            "# =============================================================================\n"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_content)

        # Set restrictive permissions if on POSIX
        try:
            os.chmod(output_path, 0o600)
        except Exception:
            pass
    except Exception as exc:
        print(f"Error: Failed to save refresh token to {output_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Output strictly the required confirmation lines
    print("Gmail OAuth authorization completed successfully.")
    print("Refresh token generated. Store it securely in your local .env.")


if __name__ == "__main__":
    main()
