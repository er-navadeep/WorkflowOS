"""
Phase 8.4 — Gmail OAuth Token Helper Unit & Integration Tests
=============================================================
Validates:
1. Strict read-only scope constraint (ONLY https://www.googleapis.com/auth/gmail.readonly).
2. Proper handling of credentials path resolution and missing configuration guidance.
3. OAuth flow execution with InstalledAppFlow mocking.
4. Security: No secrets in stdout/stderr, .env untouched, output saved to gitignored local file.
5. Verifies required confirmation messages.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure google_auth_oauthlib can be patched even if not locally installed
if "google_auth_oauthlib" not in sys.modules:
    try:
        import google_auth_oauthlib.flow  # noqa: F401
    except ImportError:
        _mock_oauthlib = MagicMock()
        sys.modules["google_auth_oauthlib"] = _mock_oauthlib
        sys.modules["google_auth_oauthlib.flow"] = _mock_oauthlib.flow

# Ensure scripts and backend are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import gmail_oauth_setup


class TestGmailOAuthSecurityRules:
    """Validate strict security and scope constraints."""

    def test_scope_is_strictly_gmail_readonly(self):
        """Rule: Request ONLY https://www.googleapis.com/auth/gmail.readonly."""
        assert len(gmail_oauth_setup.SCOPES) == 1
        assert gmail_oauth_setup.SCOPES[0] == "https://www.googleapis.com/auth/gmail.readonly"

    def test_no_dangerous_scopes_present(self):
        """Rule: Do NOT use Gmail modify or mail.google.com or full access scopes."""
        for scope in gmail_oauth_setup.SCOPES:
            assert "modify" not in scope
            assert "mail.google.com" not in scope
            assert "compose" not in scope
            assert "insert" not in scope


class TestCredentialsResolution:
    """Validate credential file discovery and missing-file guidance."""

    def test_explicit_valid_path(self, tmp_path):
        dummy_file = tmp_path / "custom_client.json"
        dummy_file.write_text("{}", encoding="utf-8")
        resolved = gmail_oauth_setup.find_credentials_file(tmp_path, str(dummy_file))
        assert resolved == dummy_file

    def test_explicit_missing_path_returns_none(self, tmp_path):
        missing_file = tmp_path / "does_not_exist.json"
        resolved = gmail_oauth_setup.find_credentials_file(tmp_path, str(missing_file))
        assert resolved is None

    def test_default_credentials_json_in_project_root(self, tmp_path):
        target = tmp_path / "credentials.json"
        target.write_text("{}", encoding="utf-8")
        resolved = gmail_oauth_setup.find_credentials_file(tmp_path, None)
        assert resolved == target

    def test_default_client_secret_pattern(self, tmp_path):
        target = tmp_path / "client_secret_12345.json"
        target.write_text("{}", encoding="utf-8")
        resolved = gmail_oauth_setup.find_credentials_file(tmp_path, None)
        assert resolved == target

    def test_missing_credentials_guide_output(self, tmp_path, capsys):
        """Rule 10: Explain exactly where the developer should place credentials.json."""
        gmail_oauth_setup.print_missing_credentials_guide(tmp_path)
        captured = capsys.readouterr()
        assert "Google Desktop OAuth client credentials file was not found" in captured.err
        assert "credentials.json" in captured.err
        assert "Desktop app" in captured.err
        assert "https://console.cloud.google.com/apis/credentials" in captured.err


class TestOAuthFlowExecution:
    """Validate OAuth execution, token output, and security isolation."""

    def test_successful_flow_execution(self, tmp_path, monkeypatch, capsys):
        # 1. Create a dummy client secrets file
        dummy_creds_file = tmp_path / "credentials.json"
        dummy_client_id = "test-client-id-12345.apps.googleusercontent.com"
        dummy_client_secret = "SECRET_VALUE_TEST_XYZ"
        dummy_refresh_token = "1//04_REFRESH_TOKEN_TEST_ABCD"

        secrets_data = {
            "installed": {
                "client_id": dummy_client_id,
                "project_id": "workflowos-test",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_secret": dummy_client_secret,
                "redirect_uris": ["http://localhost"],
            }
        }
        dummy_creds_file.write_text(json.dumps(secrets_data), encoding="utf-8")

        output_token_file = tmp_path / ".gmail_token.local"

        # 2. Mock google_auth_oauthlib.flow.InstalledAppFlow
        mock_flow = MagicMock()
        mock_flow.client_config = {
            "client_id": dummy_client_id,
            "client_secret": dummy_client_secret,
        }

        mock_creds = MagicMock()
        mock_creds.client_id = dummy_client_id
        mock_creds.client_secret = dummy_client_secret
        mock_creds.refresh_token = dummy_refresh_token
        mock_flow.credentials = mock_creds

        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow) as mock_from_file:
            # Set CLI args
            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "gmail_oauth_setup.py",
                    "--credentials",
                    str(dummy_creds_file),
                    "--output",
                    str(output_token_file),
                ],
            )

            # Record .env modification time / state before
            env_file = ROOT_DIR / ".env"
            env_mtime_before = env_file.stat().st_mtime if env_file.exists() else None

            # Execute
            gmail_oauth_setup.main()

            # Verify flow was created with the single strict scope
            mock_from_file.assert_called_once_with(
                str(dummy_creds_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

            # Verify run_local_server was called with prompt=consent, access_type=offline
            mock_flow.run_local_server.assert_called_once_with(
                port=0,
                prompt="consent",
                access_type="offline",
                authorization_prompt_message=None,
                success_message="WorkFlowOS authorization complete! You may close this tab and return to your terminal.",
                open_browser=True,
            )

            # Capture console output
            captured = capsys.readouterr()

            # Rule 7: Print ONLY the required confirmation lines
            expected_stdout = (
                "Gmail OAuth authorization completed successfully.\n"
                "Refresh token generated. Store it securely in your local .env.\n"
            )
            assert captured.out == expected_stdout

            # Rule 8: NEVER print the actual refresh token or client secret
            assert dummy_refresh_token not in captured.out
            assert dummy_refresh_token not in captured.err
            assert dummy_client_secret not in captured.out
            assert dummy_client_secret not in captured.err

            # Rule: .env was NOT modified
            if env_file.exists():
                assert env_file.stat().st_mtime == env_mtime_before

            # Output file was created with the values
            assert output_token_file.is_file()
            content = output_token_file.read_text(encoding="utf-8")
            assert dummy_refresh_token in content
            assert dummy_client_id in content
            assert dummy_client_secret in content


class TestGitIgnoreContainsOAuthRules:
    """Verify that credentials and tokens are protected in .gitignore."""

    def test_gitignore_protects_oauth_artifacts(self):
        gitignore_path = ROOT_DIR / ".gitignore"
        assert gitignore_path.is_file()
        content = gitignore_path.read_text(encoding="utf-8")
        assert "credentials.json" in content
        assert "client_secret*.json" in content
        assert "token.json" in content
        assert ".gmail_token.local" in content
