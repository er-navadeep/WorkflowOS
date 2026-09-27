"""
Phase 8.7 — Gmail download_file Integration Tests
=================================================
Validates:
1. Adapter registration for 'download_file' in IntegrationRegistry.
2. Supported action inspection (can_handle('download_file') is True, case-insensitive).
3. Missing messageId returns safe validation failure.
4. Missing attachmentId returns safe validation failure.
5. Missing filename returns safe validation failure.
6. Empty / whitespace inputs return validation failures.
7. Path traversal attempt '../' rejected.
8. Windows path traversal '..\\' rejected.
9. Absolute paths and drive letters (e.g. 'C:\\file.pdf', '/etc/passwd') rejected.
10. Unsupported file extensions (e.g. '.exe', '.sh', '.bin') rejected.
11. File size limit rejection (before disk write).
12. Dry-run makes zero Gmail API calls.
13. Dry-run creates zero real files on the filesystem.
14. Successful mocked attachment download.
15. Base64 URL-safe decoding verification.
16. Malformed base64 attachment data handling.
17. Gmail 404 attachment/message not found handling.
18. Gmail 401/403 authorization error handling.
19. Gmail API/network socket timeout handling.
20. OAuth refresh failure handling.
21. Credential and refresh token redaction in logs/errors.
22. Zero Gmail mutation methods called (no send, modify, delete, trash).
23. Existing file collision handling (non-destructive collision-safe rename).
24. Execution-service integration (live approved workflow path).
25. Approved workflow requirement (hard approval guard).
26. Existing read_email remains working.
27. Existing open_email remains working.
28. Opt-in live test isolation.
"""

from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.base import (
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.integrations.gmail.adapter import (
    DEFAULT_MAX_ATTACHMENT_SIZE_BYTES,
    GmailAdapter,
)
from app.integrations.registry import get_integration_registry
from app.models.workflow import upsert_workflow
from app.schemas.execution import ExecutionMode, ExecutionStatus, ExecutionStepStatus
from app.schemas.workflow import (
    WorkflowDefinition,
    WorkflowErrorHandling,
    WorkflowIntegration,
    WorkflowStep,
    WorkflowTrigger,
)
from app.services.execution_service import (
    WorkflowNotApprovedError,
    execute_dry_run,
    execute_live,
)


def build_download_context(
    variables: Dict[str, Any] | None = None,
    dry_run: bool = False,
    inputs: list[str] | None = None,
) -> StepExecutionContext:
    step = WorkflowStep(
        step_id="step-gmail-dl-001",
        order=1,
        application="Gmail",
        action="download_file",
        description="Download email attachment",
        inputs=inputs or ["messageId", "attachmentId", "filename"],
        outputs=["filename", "path", "size_bytes", "content_type", "message_id", "attachment_id"],
    )
    return StepExecutionContext(
        workflow_id="wf-test-dl-001",
        execution_id="exec-test-dl-001",
        step=step,
        variables=variables or {},
        dry_run=dry_run,
    )


def build_download_workflow(status: str = "approved") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=f"wf-download-{status}-001",
        understanding_id="und-download-001",
        name="Gmail Download File Workflow",
        description="Workflow to download attachment",
        status=status,
        trigger=WorkflowTrigger(
            application="Gmail",
            event="attachment_received",
            description="Trigger on attachment",
        ),
        steps=[
            WorkflowStep(
                step_id="step-1",
                order=1,
                application="Gmail",
                action="download_file",
                description="Download invoice attachment",
                inputs=["messageId", "attachmentId", "filename"],
                outputs=["filename", "path", "size_bytes", "content_type", "message_id", "attachment_id"],
            ),
        ],
        integrations=[
            WorkflowIntegration(
                application="Gmail",
                purpose="Email attachment download",
                required_capabilities=["download_file"],
            ),
        ],
        error_handling=WorkflowErrorHandling(
            fallback_strategy="abort",
            on_step_failure="stop",
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestGmailDownloadFileRegistrationAndCapabilities:
    """Requirement 1, 2, 26, 27: Adapter registration and action support."""

    def test_adapter_registration_for_download_file(self):
        registry = get_integration_registry()
        adapter = registry.get_adapter("Gmail", "download_file")
        assert adapter is not None
        assert isinstance(adapter, GmailAdapter)
        assert adapter.application_name == "Gmail"

    def test_can_handle_download_file_case_insensitive(self):
        adapter = GmailAdapter()
        assert adapter.can_handle("download_file") is True
        assert adapter.can_handle("DOWNLOAD_FILE") is True
        assert adapter.can_handle("  download_file  ") is True

    def test_existing_read_email_remains_working(self):
        """Requirement 26."""
        adapter = GmailAdapter()
        assert adapter.can_handle("read_email") is True

    def test_existing_open_email_remains_working(self):
        """Requirement 27."""
        adapter = GmailAdapter()
        assert adapter.can_handle("open_email") is True

    def test_unsupported_actions_rejected(self):
        adapter = GmailAdapter()
        for forbidden in ("send_email", "delete_file", "trash_file", "execute_file"):
            assert adapter.can_handle(forbidden) is False


class TestGmailDownloadFileInputValidation:
    """Requirement 3, 4, 5, 6: Missing, empty, or whitespace inputs."""

    def test_missing_message_id_fails(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"attachmentId": "att1", "filename": "doc.pdf"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "missing required 'messageId' input" in res.error_summary

    def test_missing_attachment_id_fails(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "msg1", "filename": "doc.pdf"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "missing required 'attachmentId' input" in res.error_summary

    def test_missing_filename_fails(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "msg1", "attachmentId": "att1"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "missing required 'filename' input" in res.error_summary

    def test_empty_or_whitespace_inputs_fail(self):
        adapter = GmailAdapter()
        # Empty messageId
        res = adapter.execute(build_download_context(variables={"messageId": "   ", "attachmentId": "att1", "filename": "doc.pdf"}))
        assert res.success is False
        assert "missing required 'messageId' input" in res.error_summary

        # Empty attachmentId
        res = adapter.execute(build_download_context(variables={"messageId": "msg1", "attachmentId": "   ", "filename": "doc.pdf"}))
        assert res.success is False
        assert "missing required 'attachmentId' input" in res.error_summary

        # Empty filename
        res = adapter.execute(build_download_context(variables={"messageId": "msg1", "attachmentId": "att1", "filename": "   "}))
        assert res.success is False
        assert "missing required 'filename' input" in res.error_summary


class TestGmailDownloadFileSecurityAndPathTraversal:
    """Requirement 7, 8, 9, 10, 11: Security, path traversal, extension allowlist, and size limit."""

    def test_path_traversal_unix_relative(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "../../../etc/passwd.pdf"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "path traversal" in res.error_summary.lower()

    def test_path_traversal_windows_relative(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "..\\..\\windows\\system32\\config.pdf"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "path traversal" in res.error_summary.lower()

    def test_absolute_and_drive_letter_paths_rejected(self):
        adapter = GmailAdapter()
        for bad_path in ("/var/log/secret.pdf", "C:\\Users\\admin\\secret.pdf", "\\\\server\\share\\doc.pdf"):
            ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": bad_path})
            res = adapter.execute(ctx)
            assert res.success is False
            assert res.status == ExecutionStepStatus.FAILED
            assert "path traversal" in res.error_summary.lower()

    def test_null_bytes_in_filename_rejected(self):
        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "doc.pdf\0.exe"})
        res = adapter.execute(ctx)
        assert res.success is False
        assert "null bytes" in res.error_summary.lower()

    def test_unsupported_extensions_rejected(self):
        adapter = GmailAdapter()
        for bad_ext in ("payload.exe", "script.sh", "install.bat", "tool.py", "macro.vbs"):
            ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": bad_ext})
            res = adapter.execute(ctx)
            assert res.success is False
            assert res.status == ExecutionStepStatus.FAILED
            assert "not permitted" in res.error_summary.lower() or "prohibited" in res.error_summary.lower()

    def test_supported_document_extensions_accepted_by_validator(self):
        adapter = GmailAdapter()
        for valid_name in ("report.pdf", "data.xlsx", "notes.docx", "sheet.csv", "log.txt", "photo.png", "img.jpg", "img.webp"):
            m, a, f, err = adapter._resolve_download_file_inputs(
                build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": valid_name})
            )
            assert err is None
            assert f == valid_name

    def test_file_size_limit_rejection_before_write(self, monkeypatch, tmp_path):
        # Set a small limit: 100 bytes
        monkeypatch.setenv("GMAIL_MAX_ATTACHMENT_SIZE_BYTES", "100")
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        with patch("googleapiclient.discovery.build") as mock_build, \
             patch("google.oauth2.credentials.Credentials") as mock_creds_cls:
            mock_creds_inst = MagicMock()
            mock_creds_inst.token = "token"
            mock_creds_cls.return_value = mock_creds_inst

            mock_service = MagicMock()
            mock_att_req = MagicMock()
            # Reported size is 500 bytes (> 100 limit)
            mock_att_req.execute.return_value = {"size": 500, "data": "dGVzdA=="}
            mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value = mock_att_req
            mock_build.return_value = mock_service

            adapter = GmailAdapter()
            ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "large.pdf"})
            res = adapter.execute(ctx)

            assert res.success is False
            assert res.status == ExecutionStepStatus.FAILED
            assert "exceeds maximum permitted limit" in res.error_summary
            # Verify no file was written
            assert len(list(tmp_path.glob("*"))) == 0


class TestGmailDownloadFileDryRun:
    """Requirement 12 & 13: Dry-run zero API calls and zero files written."""

    def test_dry_run_makes_zero_api_calls_and_zero_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))
        adapter = GmailAdapter()
        ctx = build_download_context(
            variables={"messageId": "msg_001", "attachmentId": "att_001", "filename": "invoice.pdf"},
            dry_run=True,
        )

        with patch("googleapiclient.discovery.build") as mock_build:
            res = adapter.execute(ctx)
            assert mock_build.call_count == 0

        assert res.success is True
        assert res.status == ExecutionStepStatus.DRY_RUN
        assert res.outputs["dry_run"] is True
        assert res.outputs["network_call"] is False
        assert res.outputs["filesystem_write"] is False
        assert res.outputs["filename"] == "invoice.pdf"

        # Verify zero files written
        assert len(list(tmp_path.glob("*"))) == 0


class TestGmailDownloadFileMockedExecution:
    """Requirement 14, 15, 16, 22, 23: Mocked download, base64 decoding, collision safety, no mutation."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_successful_mocked_download_and_base64_decode(self, mock_creds_cls, mock_build, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        # Fake PDF content encoded as URL-safe base64
        fake_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        encoded_data = base64.urlsafe_b64encode(fake_content).decode("utf-8")

        mock_service = MagicMock()
        mock_messages = MagicMock()
        mock_attachments = MagicMock()
        mock_get_req = MagicMock()
        mock_get_req.execute.return_value = {"size": len(fake_content), "data": encoded_data}
        mock_attachments.get.return_value = mock_get_req
        mock_messages.attachments.return_value = mock_attachments
        mock_service.users.return_value.messages.return_value = mock_messages
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m123", "attachmentId": "a456", "filename": "sample.pdf"})

        res = adapter.execute(ctx)

        assert res.success is True
        assert res.status == ExecutionStepStatus.COMPLETED
        assert res.outputs["filename"] == "sample.pdf"
        assert res.outputs["size_bytes"] == len(fake_content)
        assert res.outputs["content_type"] == "application/pdf"
        assert res.outputs["message_id"] == "m123"
        assert res.outputs["attachment_id"] == "a456"

        # Verify file exists on disk with exact content
        saved_file = tmp_path / "sample.pdf"
        assert saved_file.is_file()
        assert saved_file.read_bytes() == fake_content

        # Requirement 22: Zero mutation methods called
        assert mock_messages.send.call_count == 0
        assert mock_messages.delete.call_count == 0
        assert mock_messages.trash.call_count == 0
        assert mock_messages.modify.call_count == 0

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_existing_file_collision_handling(self, mock_creds_cls, mock_build, tmp_path, monkeypatch):
        """Requirement 23: Non-destructive collision rename preserves existing file."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        # Pre-create sample.pdf with initial content
        existing_file = tmp_path / "sample.pdf"
        existing_file.write_bytes(b"INITIAL_USER_CONTENT")

        new_content = b"NEW_DOWNLOADED_CONTENT"
        encoded_data = base64.urlsafe_b64encode(new_content).decode("utf-8")

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
            "size": len(new_content),
            "data": encoded_data,
        }
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "sample.pdf"})

        res = adapter.execute(ctx)

        assert res.success is True
        # Output filename was renamed safely to sample_1.pdf
        assert res.outputs["filename"] == "sample_1.pdf"

        # Verify original file was preserved intact
        assert existing_file.read_bytes() == b"INITIAL_USER_CONTENT"
        # Verify collision file was created
        collision_file = tmp_path / "sample_1.pdf"
        assert collision_file.is_file()
        assert collision_file.read_bytes() == b"NEW_DOWNLOADED_CONTENT"

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_malformed_base64_data_fails_safely(self, mock_creds_cls, mock_build, tmp_path, monkeypatch):
        """Requirement 16: Malformed attachment data handled safely without crashing."""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
            "size": 50,
            "data": "!!!NOT_VALID_BASE64@@@",
        }
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "corrupt.pdf"})

        res = adapter.execute(ctx)
        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "malformed attachment data" in res.result_summary.lower()


class TestGmailDownloadFileErrorsAndSecurity:
    """Requirement 17, 18, 19, 20, 21: Error handling, status codes, and secret sanitization."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_gmail_404_attachment_not_found(self, mock_creds_cls, mock_build, monkeypatch):
        from googleapiclient.errors import HttpError
        import httplib2

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        resp = httplib2.Response({"status": "404"})
        resp.status = 404
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.side_effect = (
            HttpError(resp, b'{"error": {"code": 404, "message": "Attachment Not Found"}}')
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "missing.pdf"})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "not found" in res.result_summary.lower()

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_gmail_401_403_authorization_error(self, mock_creds_cls, mock_build, monkeypatch):
        from googleapiclient.errors import HttpError
        import httplib2

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        resp = httplib2.Response({"status": "403"})
        resp.status = 403
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.side_effect = (
            HttpError(resp, b'{"error": {"code": 403, "message": "Forbidden"}}')
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "doc.pdf"})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "authorization error" in res.result_summary.lower()

    @patch("google.oauth2.credentials.Credentials")
    def test_oauth_refresh_failure_and_token_redaction(self, mock_creds_cls, monkeypatch):
        dummy_secret = "SECRET_SUPER_SECRET_GOCSPX_999"
        dummy_refresh = "REFRESH_SUPER_SECRET_111"

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", dummy_secret)
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", dummy_refresh)

        mock_creds_inst = MagicMock()
        mock_creds_inst.refresh.side_effect = Exception(f"invalid_grant with secret {dummy_secret}")
        mock_creds_cls.return_value = mock_creds_inst

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "doc.pdf"})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert dummy_secret not in res.error_summary
        assert dummy_refresh not in res.error_summary
        assert "[REDACTED_GOOGLE_CLIENT_SECRET]" in res.error_summary

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_network_socket_timeout(self, mock_creds_cls, mock_build, monkeypatch):
        import socket

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.side_effect = (
            socket.timeout("Socket timed out")
        )
        mock_build.return_value = mock_service

        adapter = GmailAdapter()
        ctx = build_download_context(variables={"messageId": "m1", "attachmentId": "a1", "filename": "doc.pdf"})
        res = adapter.execute(ctx)

        assert res.success is False
        assert res.status == ExecutionStepStatus.FAILED
        assert "timed out" in res.result_summary.lower()


class TestExecutionServiceGmailDownloadFileIntegration:
    """Requirement 24 & 25: Execution service integration and approval guard."""

    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_execute_live_approved_workflow_with_download_step(self, mock_creds_cls, mock_build, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        fake_pdf = b"%PDF-1.4 TEST CONTENT"
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
            "size": len(fake_pdf),
            "data": base64.urlsafe_b64encode(fake_pdf).decode("utf-8"),
        }
        mock_build.return_value = mock_service

        wf = build_download_workflow(status="approved")
        upsert_workflow(wf)

        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"messageId": "msg_live_001", "attachmentId": "att_live_001", "filename": "live_invoice.pdf"},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_steps == 1
        assert len(execution.step_records) == 1

        step_rec = execution.step_records[0]
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.application == "Gmail"
        assert step_rec.action == "download_file"
        assert "Gmail download_file completed successfully" in step_rec.result_summary

    def test_execute_live_fails_if_workflow_not_approved(self):
        """Hard approval guard prevents execution of unapproved download_file workflows."""
        for status in ("generated", "rejected"):
            wf = build_download_workflow(status=status)
            wf.workflow_id = f"wf-dl-guard-{status}"
            upsert_workflow(wf)

            with pytest.raises(WorkflowNotApprovedError) as exc_info:
                execute_live(
                    wf.workflow_id,
                    variables={"messageId": "m1", "attachmentId": "a1", "filename": "doc.pdf"},
                )

            assert exc_info.value.status_code == 409
            assert f"current status is '{status}'" in exc_info.value.message

    def test_execution_step_record_has_no_outputs_attribute(self):
        """Regression test: ExecutionStepRecord model strictly does not expose .outputs."""
        from app.schemas.execution import ExecutionStepRecord, ExecutionStepStatus

        rec = ExecutionStepRecord(
            step_id="step-1",
            order=1,
            application="Gmail",
            action="download_file",
            status=ExecutionStepStatus.COMPLETED,
            result_summary="Gmail download_file completed successfully: downloaded 'doc.pdf' (1024 bytes).",
        )
        assert hasattr(rec, "status")
        assert hasattr(rec, "result_summary")
        assert hasattr(rec, "error_summary")
        assert not hasattr(rec, "outputs"), "ExecutionStepRecord must not have 'outputs' attribute"

    def test_step_execution_result_uses_error_summary_not_error_message(self):
        """
        Regression test: StepExecutionResult exposes 'error_summary', NOT 'error_message'.

        Root cause of Phase 8.7 verification script crash (line 224):
            res.error_message   # AttributeError — wrong field name
        Correct access:
            res.error_summary   # correct field on StepExecutionResult
        """
        from app.integrations.base import StepExecutionResult
        from app.schemas.execution import ExecutionStepStatus

        # A failure result (e.g. as returned by GmailAdapter when credentials are missing)
        res = StepExecutionResult(
            success=False,
            status=ExecutionStepStatus.FAILED,
            result_summary="Required Google dependencies missing.",
            error_summary="No module named 'googleapiclient'",
        )

        # The correct field is 'error_summary'
        assert hasattr(res, "error_summary"), "StepExecutionResult must have 'error_summary'"
        assert res.error_summary == "No module named 'googleapiclient'"

        # 'error_message' must NOT exist — accessing it would raise AttributeError
        assert not hasattr(res, "error_message"), (
            "StepExecutionResult must NOT have 'error_message'; "
            "use 'error_summary' instead"
        )
        with pytest.raises(AttributeError):
            _ = res.error_message  # noqa: B018 — intentional AttributeError probe


    @patch("googleapiclient.discovery.build")
    @patch("google.oauth2.credentials.Credentials")
    def test_verification_script_validation_pattern_regression(self, mock_creds_cls, mock_build, tmp_path, monkeypatch):
        """
        Regression test: Validates the post-execution pattern used by verify_phase8_7_gmail_download_file.py
        reads status, result_summary, locates the file on disk without attempting to read step_record.outputs.
        """
        import re

        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "test-refresh")
        monkeypatch.setenv("GMAIL_DOWNLOAD_DIR", str(tmp_path))

        mock_creds_inst = MagicMock()
        mock_creds_inst.token = "token"
        mock_creds_cls.return_value = mock_creds_inst

        fake_pdf = b"%PDF-1.4 TEST CONTENT"
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.attachments.return_value.get.return_value.execute.return_value = {
            "size": len(fake_pdf),
            "data": base64.urlsafe_b64encode(fake_pdf).decode("utf-8"),
        }
        mock_build.return_value = mock_service

        wf = build_download_workflow(status="approved")
        upsert_workflow(wf)

        filename = "verified_doc.pdf"
        execution = execute_live(
            workflow_id=wf.workflow_id,
            variables={"messageId": "msg_live_002", "attachmentId": "att_live_002", "filename": filename},
        )

        assert execution.status == ExecutionStatus.COMPLETED
        step_rec = execution.step_records[0]

        # Ensure reading step_rec.status and step_rec.result_summary works
        assert step_rec.status == ExecutionStepStatus.COMPLETED
        assert step_rec.result_summary is not None

        # Ensure attempting to access .outputs raises AttributeError
        with pytest.raises(AttributeError):
            _ = step_rec.outputs

        # Ensure script's regex extraction and file existence check works
        match = re.search(r"downloaded '([^']+)'", step_rec.result_summary)
        assert match is not None
        saved_filename = match.group(1)
        assert saved_filename == filename

        local_file = tmp_path / saved_filename
        assert local_file.exists()
        assert local_file.stat().st_size == len(fake_pdf)
        assert local_file.resolve().is_relative_to(tmp_path.resolve())


class TestOptInLiveGmailDownloadFileAPI:
    """
    Opt-in live integration test.
    Only runs when RUN_LIVE_GMAIL_TESTS=1 is set.
    """

    @pytest.mark.skipif(
        not os.getenv("RUN_LIVE_GMAIL_TESTS"),
        reason="Opt-in only. Set RUN_LIVE_GMAIL_TESTS=1 to run against live Gmail API.",
    )
    def test_live_gmail_download_file_call(self):
        adapter = GmailAdapter()
        # Search for an email with an attachment
        ctx = build_download_context(variables={"query": "has:attachment", "max_results": 1})
        read_res = adapter.execute(ctx)
        if not read_res.success or not read_res.outputs.get("message_ids"):
            pytest.skip("No emails with attachments found in mailbox.")
