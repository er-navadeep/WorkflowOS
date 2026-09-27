"""
Phase 8.4 — Gmail OAuth Verification Unit Tests
===============================================
Validates:
1. Verification logic handles missing configuration gracefully.
2. Verification logic uses strict read-only scope (https://www.googleapis.com/auth/gmail.readonly).
3. Verification logic succeeds with mocked Google OAuth and Gmail API responses.
4. Security: No client secrets, refresh tokens, access tokens, or Authorization headers are printed.
5. Verification logic safely handles API/refresh failures without leaking credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts directory is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import verify_gmail_oauth


class TestGmailVerificationValidation:
    """Tests for parameter validation in verify_gmail_oauth."""

    def test_missing_client_id_raises_value_error(self):
        with pytest.raises(ValueError, match="Missing GOOGLE_CLIENT_ID"):
            verify_gmail_oauth.verify_gmail_oauth("", "secret", "refresh_token")

    def test_missing_client_secret_raises_value_error(self):
        with pytest.raises(ValueError, match="Missing GOOGLE_CLIENT_SECRET"):
            verify_gmail_oauth.verify_gmail_oauth("client_id", "", "refresh_token")

    def test_missing_refresh_token_raises_value_error(self):
        with pytest.raises(ValueError, match="Missing GOOGLE_REFRESH_TOKEN"):
            verify_gmail_oauth.verify_gmail_oauth("client_id", "secret", "")


class TestGmailVerificationMockedFlow:
    """Tests for OAuth refresh and Gmail API calls using mocks (no real network)."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_successful_mocked_verification(self, mock_creds_cls, mock_build):
        # Setup mock credentials
        mock_creds_instance = MagicMock()
        mock_creds_instance.token = "mock-access-token-12345"
        mock_creds_cls.return_value = mock_creds_instance

        # Setup mock Gmail service
        mock_service = MagicMock()
        mock_users = MagicMock()
        mock_profile_req = MagicMock()
        mock_profile_req.execute.return_value = {
            "emailAddress": "testuser@gmail.com",
            "messagesTotal": 150,
            "threadsTotal": 80,
            "historyId": "12345678",
        }
        mock_users.getProfile.return_value = mock_profile_req
        mock_service.users.return_value = mock_users
        mock_build.return_value = mock_service

        dummy_client_id = "test-client.apps.googleusercontent.com"
        dummy_secret = "TEST_SECRET_GOCSPX_ABC"
        dummy_refresh = "1//04_TEST_REFRESH_TOKEN_XYZ"

        result = verify_gmail_oauth.verify_gmail_oauth(
            client_id=dummy_client_id,
            client_secret=dummy_secret,
            refresh_token=dummy_refresh,
            user_id="me",
        )

        # 1. Assert Credentials initialized with exact read-only scope
        mock_creds_cls.assert_called_once_with(
            token=None,
            refresh_token=dummy_refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=dummy_client_id,
            client_secret=dummy_secret,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )

        # 2. Assert creds.refresh was called
        assert mock_creds_instance.refresh.called

        # 3. Assert build called for gmail v1
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds_instance, cache_discovery=False)
        mock_users.getProfile.assert_called_once_with(userId="me")

        # 4. Assert returned data is correct and safe
        assert result["status"] == "success"
        assert result["email_address"] == "testuser@gmail.com"
        assert result["messages_total"] == 150
        assert result["threads_total"] == 80
        assert result["scope"] == "https://www.googleapis.com/auth/gmail.readonly"

    @patch("google.oauth2.credentials.Credentials")
    def test_refresh_token_failure_raises_runtime_error(self, mock_creds_cls):
        mock_creds_instance = MagicMock()
        mock_creds_instance.refresh.side_effect = Exception("invalid_grant: Bad Request")
        mock_creds_cls.return_value = mock_creds_instance

        with pytest.raises(RuntimeError, match="OAuth refresh token exchange failed"):
            verify_gmail_oauth.verify_gmail_oauth(
                client_id="client_id",
                client_secret="secret",
                refresh_token="bad_token",
            )

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_gmail_api_call_failure_raises_runtime_error(self, mock_creds_cls, mock_build):
        mock_creds_instance = MagicMock()
        mock_creds_instance.token = "valid_token"
        mock_creds_cls.return_value = mock_creds_instance

        mock_service = MagicMock()
        mock_users = MagicMock()
        mock_profile_req = MagicMock()
        mock_profile_req.execute.side_effect = Exception("HttpError 403: Forbidden")
        mock_users.getProfile.return_value = mock_profile_req
        mock_service.users.return_value = mock_users
        mock_build.return_value = mock_service

        with pytest.raises(RuntimeError, match="Gmail API users.getProfile call failed"):
            verify_gmail_oauth.verify_gmail_oauth(
                client_id="client_id",
                client_secret="secret",
                refresh_token="valid_refresh",
            )


class TestMainCLISecurityAndOutput:
    """Test CLI execution and verify zero secret exposure in stdout/stderr."""

    @patch("verify_gmail_oauth.verify_gmail_oauth")
    def test_main_cli_success_output(self, mock_verify, monkeypatch, capsys):
        dummy_secret = "SECRET_SUPER_CONFIDENTIAL_XYZ"
        dummy_refresh = "REFRESH_SUPER_CONFIDENTIAL_123"

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", dummy_secret)
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", dummy_refresh)
        monkeypatch.setenv("GMAIL_USER_ID", "me")

        mock_verify.return_value = {
            "status": "success",
            "email_address": "verified_user@gmail.com",
            "messages_total": 42,
            "threads_total": 12,
            "history_id": "100",
            "scope": "https://www.googleapis.com/auth/gmail.readonly",
        }

        exit_code = verify_gmail_oauth.main()
        assert exit_code == 0

        captured = capsys.readouterr()
        # Verify safe outputs
        assert "OAuth authentication successful." in captured.out
        assert "Gmail API connection successful." in captured.out
        assert "Authenticated mailbox: verified_user@gmail.com" in captured.out
        assert "Total messages in mailbox: 42" in captured.out
        assert "Verification completed successfully." in captured.out

        # Verify NEVER prints secret, refresh token, or headers
        assert dummy_secret not in captured.out
        assert dummy_secret not in captured.err
        assert dummy_refresh not in captured.out
        assert dummy_refresh not in captured.err
        assert "Authorization:" not in captured.out
        assert "Bearer" not in captured.out

    def test_main_cli_missing_env_returns_code_1(self, monkeypatch, capsys):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)

        exit_code = verify_gmail_oauth.main()
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "Missing required environment variable(s)" in captured.err
