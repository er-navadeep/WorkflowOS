"""
Gmail Adapter — Phase 8 Step 8.5, 8.6 & 8.7
===========================================
Executes Gmail actions for WorkFlowOS workflows.
Supported actions:
    - 'read_email': Query/search emails in user mailbox (read-only).
    - 'open_email': Retrieve single email details by messageId (read-only).
    - 'download_file': Download specific email attachment by messageId & attachmentId (read-only).

Security & Guardrails:
    - Scope: strictly 'https://www.googleapis.com/auth/gmail.readonly'.
    - Never mutates, sends, deletes, archives, or labels emails.
    - Zero external network requests during dry-run simulation.
    - Zero filesystem writes during dry-run simulation.
    - Strict path traversal prevention: rejects '../', '..\\', absolute, drive-letter, UNC paths, and null bytes.
    - Enforces configurable allowlist for file extensions (.pdf, .docx, .xlsx, .csv, .txt, .jpg, .jpeg, .png, .webp).
    - Enforces configurable maximum attachment size limit (GMAIL_MAX_ATTACHMENT_SIZE_BYTES, default 10MB).
    - Fails safely on missing credentials, unsupported actions, or missing inputs.
    - Never prints, logs, or returns OAuth credentials, refresh tokens, access tokens, or Authorization headers.
    - Never logs raw attachment bytes or full email body content.
    - Non-destructive collision-safe file naming preserves existing user files.
    - Strict timeout enforced on all API operations.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.integrations.base import (
    BaseIntegrationAdapter,
    StepExecutionContext,
    StepExecutionResult,
    sanitize_text,
)
from app.schemas.execution import ExecutionStepStatus

logger = logging.getLogger(__name__)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESULTS = 5
MAX_ALLOWED_RESULTS = 25
DEFAULT_MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB default limit (10,485,760 bytes)
MAX_ATTACHMENT_SIZE_ENV_KEY = "GMAIL_MAX_ATTACHMENT_SIZE_BYTES"

DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
SUPPORTED_ATTACHMENT_EXTENSIONS = DEFAULT_ALLOWED_EXTENSIONS

DISALLOWED_SCRIPT_EXTENSIONS: Set[str] = {
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".py",
    ".js",
    ".vbs",
    ".dll",
    ".bin",
    ".com",
    ".scr",
    ".msi",
}

SUPPORTED_ACTIONS = ("read_email", "open_email", "download_file")


class GmailAdapter(BaseIntegrationAdapter):
    """
    Adapter for integrating WorkFlowOS with Gmail in read-only mode.
    """

    @property
    def application_name(self) -> str:
        return "Gmail"

    def can_handle(self, action: str) -> bool:
        """
        GmailAdapter supports 'read_email', 'open_email', and 'download_file'.
        """
        if not action or not isinstance(action, str):
            return False
        return action.strip().lower() in SUPPORTED_ACTIONS

    def execute(self, context: StepExecutionContext) -> StepExecutionResult:
        """
        Execute Gmail action for the given workflow step context.
        """
        action = context.step.action.strip().lower() if context.step.action else ""
        if not self.can_handle(action):
            error_msg = f"Unsupported action '{context.step.action}' for Gmail adapter."
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=f"Gmail adapter does not support action '{context.step.action}'.",
                error_summary=sanitize_text(error_msg),
            )

        # -------------------------------------------------------------------
        # Dry-run handling: MUST NOT make any external network call
        # -------------------------------------------------------------------
        if context.dry_run:
            if action == "open_email":
                return self._dry_run_open_email(context)
            elif action == "download_file":
                return self._dry_run_download_file(context)
            return self._dry_run_read_email(context)

        # -------------------------------------------------------------------
        # Configuration check: GOOGLE_CLIENT_ID, SECRET, REFRESH_TOKEN
        # -------------------------------------------------------------------
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
        user_id = os.getenv("GMAIL_USER_ID", "me").strip() or "me"

        missing_configs = []
        if not client_id:
            missing_configs.append("GOOGLE_CLIENT_ID")
        if not client_secret:
            missing_configs.append("GOOGLE_CLIENT_SECRET")
        if not refresh_token:
            missing_configs.append("GOOGLE_REFRESH_TOKEN")

        if missing_configs:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail execution failed: missing required OAuth configuration.",
                error_summary=f"Missing configuration variable(s): {', '.join(missing_configs)}.",
            )

        # -------------------------------------------------------------------
        # Action Dispatch
        # -------------------------------------------------------------------
        if action == "download_file":
            message_id, attachment_id, filename, input_err = self._resolve_download_file_inputs(context)
            if input_err:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file failed: input validation error.",
                    error_summary=sanitize_text(input_err),
                )
            return self._execute_download_file(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                user_id=user_id,
                message_id=message_id,  # type: ignore[arg-type]
                attachment_id=attachment_id,  # type: ignore[arg-type]
                filename=filename,  # type: ignore[arg-type]
                context=context,
            )

        if action == "open_email":
            message_id, input_err = self._resolve_open_email_inputs(context)
            if input_err:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail open_email failed: input validation error.",
                    error_summary=sanitize_text(input_err),
                )
            return self._execute_open_email(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                user_id=user_id,
                message_id=message_id,  # type: ignore[arg-type]
                context=context,
            )

        # action == "read_email"
        query, max_results, input_err = self._resolve_read_email_inputs(context)
        if input_err:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail read_email failed: input validation error.",
                error_summary=sanitize_text(input_err),
            )

        return self._execute_read_email(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            user_id=user_id,
            query=query,  # type: ignore[arg-type]
            max_results=max_results,
            context=context,
        )

    # -----------------------------------------------------------------------
    # Dry Run Helpers
    # -----------------------------------------------------------------------

    def _dry_run_read_email(self, context: StepExecutionContext) -> StepExecutionResult:
        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.DRY_RUN,
            outputs={
                "message_ids": ["simulated-msg-001"],
                "message_count": 1,
                "messages": [
                    {
                        "id": "simulated-msg-001",
                        "thread_id": "simulated-thread-001",
                        "subject": "DRY RUN Simulation — Read Email",
                        "sender": "simulated-sender@example.com",
                        "received_at": "2026-01-01T00:00:00Z",
                        "snippet": "DRY RUN — Simulated email body snippet.",
                    }
                ],
                "messageId": "simulated-msg-001",
                "message_id": "simulated-msg-001",
                "subject": "DRY RUN Simulation — Read Email",
                "sender": "simulated-sender@example.com",
                "received_at": "2026-01-01T00:00:00Z",
                "snippet": "DRY RUN — Simulated email body snippet.",
                "dry_run": True,
            },
            result_summary="Gmail read_email simulated; zero external API requests made.",
            error_summary=None,
        )

    def _dry_run_open_email(self, context: StepExecutionContext) -> StepExecutionResult:
        raw_id = (
            context.variables.get("messageId")
            or context.variables.get("message_id")
            or context.variables.get("id")
            or context.variables.get("msg_id")
            or context.variables.get("email_id")
            or "simulated-msg-001"
        )
        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.DRY_RUN,
            outputs={
                "messageId": str(raw_id),
                "message_id": str(raw_id),
                "threadId": "simulated-thread-001",
                "thread_id": "simulated-thread-001",
                "subject": "DRY RUN Simulation — Open Email",
                "sender": "simulated-sender@example.com",
                "recipient": "simulated-recipient@example.com",
                "received_at": "2026-01-01T00:00:00Z",
                "snippet": "DRY RUN — Simulated email body snippet.",
                "dry_run": True,
            },
            result_summary="Gmail open_email simulated; zero external API requests made.",
            error_summary=None,
        )

    def _dry_run_download_file(self, context: StepExecutionContext) -> StepExecutionResult:
        filename = (
            context.variables.get("filename")
            or context.variables.get("file_name")
            or context.variables.get("fileName")
            or "simulated_attachment.pdf"
        )
        message_id = (
            context.variables.get("messageId")
            or context.variables.get("message_id")
            or "simulated-msg-001"
        )
        attachment_id = (
            context.variables.get("attachmentId")
            or context.variables.get("attachment_id")
            or "simulated-att-001"
        )
        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.DRY_RUN,
            outputs={
                "filename": str(filename),
                "path": f"backend/runtime/downloads/{filename}",
                "size_bytes": 1024,
                "content_type": mimetypes.guess_type(str(filename))[0] or "application/pdf",
                "message_id": str(message_id),
                "attachment_id": str(attachment_id),
                "dry_run": True,
                "network_call": False,
                "filesystem_write": False,
            },
            result_summary="Gmail download_file simulated; zero network calls made and zero files written to disk.",
            error_summary=None,
        )

    # -----------------------------------------------------------------------
    # Policy & Configuration Helpers
    # -----------------------------------------------------------------------

    def _get_max_attachment_size_bytes(self) -> int:
        """
        Return the configured maximum attachment size in bytes.
        Defaults to 10 MB (10,485,760 bytes).
        """
        raw = os.getenv("GMAIL_MAX_ATTACHMENT_SIZE_BYTES", "").strip()
        if raw:
            try:
                val = int(raw)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        return DEFAULT_MAX_ATTACHMENT_SIZE_BYTES

    def _get_allowed_extensions(self) -> Set[str]:
        """
        Return the allowlist of supported file extensions.
        """
        custom = os.getenv("GMAIL_ALLOWED_EXTENSIONS", "").strip()
        if custom:
            parts = {ext.strip().lower() for ext in custom.split(",") if ext.strip()}
            return {ext if ext.startswith(".") else f".{ext}" for ext in parts}
        return set(DEFAULT_ALLOWED_EXTENSIONS)

    def _get_download_dir(self) -> Path:
        """
        Return the controlled application-managed download directory.
        Defaults to backend/runtime/downloads/ within the project.
        """
        custom = os.getenv("GMAIL_DOWNLOAD_DIR", "").strip()
        if custom:
            p = Path(custom).resolve()
        else:
            p = Path(__file__).resolve().parent.parent.parent / "runtime" / "downloads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _get_collision_safe_path(self, download_dir: Path, filename: str) -> Path:
        """
        Return a collision-safe path within download_dir to prevent accidental destructive overwrite.
        """
        base_path = download_dir / filename
        if not base_path.exists():
            return base_path

        p = Path(filename)
        stem = p.stem
        ext = p.suffix
        counter = 1
        while True:
            candidate = download_dir / f"{stem}_{counter}{ext}"
            if not candidate.exists():
                return candidate
            counter += 1

    # -----------------------------------------------------------------------
    # Input Resolvers
    # -----------------------------------------------------------------------

    def _resolve_read_email_inputs(
        self, context: StepExecutionContext
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """
        Safely resolve 'query' and 'max_results' for read_email.
        Never invents query values.
        """
        query_val = None
        for key in ("query", "gmail_query", "search_query", "q"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    query_val = val
                    break

        if not query_val:
            for inp in context.step.inputs:
                if inp in context.variables and context.variables[inp] is not None:
                    val = str(context.variables[inp]).strip()
                    if val:
                        query_val = val
                        break

        if not query_val:
            return (
                None,
                DEFAULT_MAX_RESULTS,
                "Cannot execute read_email: missing required 'query' input. No query was specified in execution context.",
            )

        max_results = DEFAULT_MAX_RESULTS
        raw_max = context.variables.get("max_results")
        if raw_max is None:
            raw_max = context.variables.get("limit")

        if raw_max is not None:
            try:
                parsed_max = int(raw_max)
                if parsed_max < 1 or parsed_max > MAX_ALLOWED_RESULTS:
                    return (
                        None,
                        DEFAULT_MAX_RESULTS,
                        f"Invalid 'max_results': value '{raw_max}' must be an integer between 1 and {MAX_ALLOWED_RESULTS}.",
                    )
                max_results = parsed_max
            except (ValueError, TypeError):
                return (
                    None,
                    DEFAULT_MAX_RESULTS,
                    f"Invalid 'max_results': '{raw_max}' is not a valid integer.",
                )

        return (query_val, max_results, None)

    def _resolve_open_email_inputs(
        self, context: StepExecutionContext
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Safely resolve 'messageId' for open_email.
        Never invents message IDs.
        """
        raw_id = None
        for key in ("messageId", "message_id", "id", "email_id", "msg_id"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    raw_id = val
                    break

        if not raw_id:
            for inp in context.step.inputs:
                if inp in context.variables and context.variables[inp] is not None:
                    val = str(context.variables[inp]).strip()
                    if val:
                        raw_id = val
                        break

        if not raw_id:
            return (
                None,
                "Cannot execute open_email: missing required 'messageId' input. No message ID was specified in execution context.",
            )

        # Validate messageId: must not contain whitespace or invalid characters
        if any(c in raw_id for c in (" ", "\n", "\r", "\t", "<", ">", '"', "'", "/")):
            return (
                None,
                "Invalid 'messageId': value contains whitespace or invalid characters.",
            )

        return (raw_id, None)

    def _resolve_download_file_inputs(
        self, context: StepExecutionContext
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Safely resolve messageId, attachmentId, and filename for download_file.

        Security & Validation:
        - Rejects missing or empty inputs.
        - Never invents message IDs, attachment IDs, filenames, or locations.
        - Strict path traversal prevention: rejects null bytes, '../', '..\\',
          absolute paths, drive-letter paths, and UNC paths.
        - Validates file extension against document allowlist.
        """
        # 1. messageId
        message_id = None
        for key in ("messageId", "message_id", "id", "email_id", "msg_id"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    message_id = val
                    break

        if not message_id:
            for inp in context.step.inputs:
                if inp in ("messageId", "message_id", "id") and inp in context.variables:
                    val = str(context.variables[inp]).strip()
                    if val:
                        message_id = val
                        break

        if not message_id:
            return (
                None,
                None,
                None,
                "Cannot execute download_file: missing required 'messageId' input. No message ID was specified in execution context.",
            )

        if any(c in message_id for c in (" ", "\n", "\r", "\t", "<", ">", '"', "'", "/")):
            return (
                None,
                None,
                None,
                "Invalid 'messageId': value contains whitespace or invalid characters.",
            )

        # 2. attachmentId
        attachment_id = None
        for key in ("attachmentId", "attachment_id", "att_id"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    attachment_id = val
                    break

        if not attachment_id:
            for inp in context.step.inputs:
                if inp in ("attachmentId", "attachment_id") and inp in context.variables:
                    val = str(context.variables[inp]).strip()
                    if val:
                        attachment_id = val
                        break

        if not attachment_id:
            return (
                None,
                None,
                None,
                "Cannot execute download_file: missing required 'attachmentId' input. No attachment ID was specified in execution context.",
            )

        if any(c in attachment_id for c in (" ", "\n", "\r", "\t", "<", ">", '"', "'")):
            return (
                None,
                None,
                None,
                "Invalid 'attachmentId': value contains whitespace or invalid characters.",
            )

        # 3. filename
        filename = None
        for key in ("filename", "file_name", "fileName", "name"):
            if key in context.variables and context.variables[key] is not None:
                val = str(context.variables[key]).strip()
                if val:
                    filename = val
                    break

        if not filename:
            for inp in context.step.inputs:
                if inp in ("filename", "file_name", "fileName", "name") and inp in context.variables:
                    val = str(context.variables[inp]).strip()
                    if val:
                        filename = val
                        break

        if not filename:
            return (
                None,
                None,
                None,
                "Cannot execute download_file: missing required 'filename' input. No filename was specified in execution context.",
            )

        # Path Traversal Guard: null bytes, directory separators, drive letters
        if "\0" in filename:
            return (
                None,
                None,
                None,
                "Invalid 'filename': null bytes are not permitted.",
            )

        if (
            ".." in filename
            or "/" in filename
            or "\\" in filename
            or ":" in filename
            or filename.startswith("~")
        ):
            return (
                None,
                None,
                None,
                "Invalid 'filename': path traversal sequences ('../', '..\\'), directory separators, drive letters, and absolute paths are not permitted.",
            )

        p = Path(filename)
        ext = p.suffix.lower()
        if not ext:
            return (
                None,
                None,
                None,
                "Invalid 'filename': file must include a valid extension.",
            )

        # Check against dangerous script/executable extensions
        if ext in DISALLOWED_SCRIPT_EXTENSIONS:
            return (
                None,
                None,
                None,
                f"Security violation: executable file extension '{ext}' is strictly prohibited.",
            )

        # Check against allowed document extensions
        allowed = self._get_allowed_extensions()
        if ext not in allowed:
            return (
                None,
                None,
                None,
                f"Unsupported file type: extension '{ext}' is not permitted. Allowed extensions: {', '.join(sorted(allowed))}.",
            )

        return (message_id, attachment_id, filename, None)

    # -----------------------------------------------------------------------
    # Live Execution Helpers
    # -----------------------------------------------------------------------

    def _execute_read_email(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        user_id: str,
        query: str,
        max_results: int,
        context: StepExecutionContext,
    ) -> StepExecutionResult:
        """
        Perform authenticated Gmail API list and get calls with strict timeout
        and zero secret exposure.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError as exc:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail execution failed: missing Google client libraries.",
                error_summary=f"Required Google dependencies missing: {exc}",
            )

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[GMAIL_READONLY_SCOPE],
        )

        try:
            request = Request()
            creds.refresh(request)
        except Exception as exc:
            sanitized_err = sanitize_text(f"OAuth refresh failed: {type(exc).__name__}: {exc}")
            logger.error("Gmail OAuth refresh failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed during OAuth token refresh.",
                error_summary=sanitized_err,
            )

        if not creds.token:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed: no access token returned.",
                error_summary="OAuth refresh did not produce an active access token.",
            )

        orig_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(DEFAULT_TIMEOUT_SECONDS)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            list_resp = (
                service.users()
                .messages()
                .list(userId=user_id, q=query, maxResults=max_results)
                .execute()
            )
            raw_messages = list_resp.get("messages", [])

            extracted_messages: List[Dict[str, Any]] = []
            message_ids: List[str] = []

            for msg_item in raw_messages:
                msg_id = msg_item.get("id")
                if not msg_id:
                    continue
                message_ids.append(msg_id)

                try:
                    msg_detail = (
                        service.users()
                        .messages()
                        .get(
                            userId=user_id,
                            id=msg_id,
                            format="metadata",
                            metadataHeaders=["Subject", "From", "Date"],
                        )
                        .execute()
                    )

                    headers = {
                        h.get("name", "").lower(): h.get("value", "")
                        for h in msg_detail.get("payload", {}).get("headers", [])
                    }

                    received_at = headers.get("date", "")
                    internal_ms = msg_detail.get("internalDate")
                    if internal_ms:
                        try:
                            received_at = datetime.fromtimestamp(
                                int(internal_ms) / 1000, tz=timezone.utc
                            ).isoformat()
                        except Exception:
                            pass

                    extracted_messages.append(
                        {
                            "id": msg_id,
                            "thread_id": msg_detail.get("threadId", ""),
                            "subject": headers.get("subject", ""),
                            "sender": headers.get("from", ""),
                            "received_at": received_at,
                            "snippet": msg_detail.get("snippet", ""),
                        }
                    )
                except Exception as get_exc:
                    logger.warning("Could not fetch detail for Gmail message %s: %s", msg_id, get_exc)
                    extracted_messages.append(
                        {
                            "id": msg_id,
                            "thread_id": msg_item.get("threadId", ""),
                            "subject": "",
                            "sender": "",
                            "received_at": "",
                            "snippet": "",
                        }
                    )

        except Exception as api_exc:
            sanitized_err = sanitize_text(f"Gmail API error: {type(api_exc).__name__}: {api_exc}")
            logger.error("Gmail API call failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail API request failed.",
                error_summary=sanitized_err,
            )
        finally:
            socket.setdefaulttimeout(orig_timeout)

        first_msg = extracted_messages[0] if extracted_messages else {}
        outputs: Dict[str, Any] = {
            "message_ids": message_ids,
            "message_count": len(extracted_messages),
            "messages": extracted_messages,
            "messageId": first_msg.get("id", ""),
            "message_id": first_msg.get("id", ""),
            "subject": first_msg.get("subject", ""),
            "sender": first_msg.get("sender", ""),
            "received_at": first_msg.get("received_at", ""),
            "snippet": first_msg.get("snippet", ""),
        }

        logger.info(
            "Successfully executed Gmail read_email for execution %s (step %d): found %d message(s).",
            context.execution_id,
            context.step.order,
            len(extracted_messages),
        )

        return StepExecutionResult(
            success=True,
            status=ExecutionStepStatus.COMPLETED,
            outputs=outputs,
            result_summary=f"Gmail read_email completed successfully: found {len(extracted_messages)} message(s) matching query.",
            error_summary=None,
        )

    def _execute_open_email(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        user_id: str,
        message_id: str,
        context: StepExecutionContext,
    ) -> StepExecutionResult:
        """
        Perform authenticated Gmail API messages.get for one specific messageId.
        Strictly read-only, controlled metadata format, strict timeout, zero secret exposure.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
        except ImportError as exc:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail execution failed: missing Google client libraries.",
                error_summary=f"Required Google dependencies missing: {exc}",
            )

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[GMAIL_READONLY_SCOPE],
        )

        try:
            request = Request()
            creds.refresh(request)
        except Exception as exc:
            sanitized_err = sanitize_text(f"OAuth refresh failed: {type(exc).__name__}: {exc}")
            logger.error("Gmail OAuth refresh failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed during OAuth token refresh.",
                error_summary=sanitized_err,
            )

        if not creds.token:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed: no access token returned.",
                error_summary="OAuth refresh did not produce an active access token.",
            )

        orig_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(DEFAULT_TIMEOUT_SECONDS)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            msg_detail = (
                service.users()
                .messages()
                .get(
                    userId=user_id,
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Date"],
                )
                .execute()
            )

            headers = {
                h.get("name", "").lower(): h.get("value", "")
                for h in msg_detail.get("payload", {}).get("headers", [])
            }

            received_at = headers.get("date", "")
            internal_ms = msg_detail.get("internalDate")
            if internal_ms:
                try:
                    received_at = datetime.fromtimestamp(
                        int(internal_ms) / 1000, tz=timezone.utc
                    ).isoformat()
                except Exception:
                    pass

            thread_id = msg_detail.get("threadId", "")
            snippet = msg_detail.get("snippet", "")
            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            recipient = headers.get("to", "")

            outputs: Dict[str, Any] = {
                "messageId": message_id,
                "message_id": message_id,
                "threadId": thread_id,
                "thread_id": thread_id,
                "subject": subject,
                "sender": sender,
                "recipient": recipient,
                "received_at": received_at,
                "snippet": snippet,
            }

            logger.info(
                "Successfully executed Gmail open_email for execution %s (step %d, message %s).",
                context.execution_id,
                context.step.order,
                message_id,
            )

            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs=outputs,
                result_summary=f"Gmail open_email completed successfully: retrieved message '{message_id}'.",
                error_summary=None,
            )

        except HttpError as http_exc:
            status_code = getattr(http_exc.resp, "status", None) if hasattr(http_exc, "resp") else getattr(http_exc, "status_code", None)
            if status_code == 404:
                error_msg = f"Gmail message '{message_id}' not found (404 Not Found)."
                result_sum = f"Gmail open_email failed: message '{message_id}' not found."
            elif status_code in (401, 403):
                error_msg = f"Gmail API authorization error ({status_code} Forbidden/Unauthorized)."
                result_sum = "Gmail open_email failed: authorization error."
            else:
                error_msg = f"Gmail API HTTP error {status_code}."
                result_sum = "Gmail API request failed."
            sanitized_err = sanitize_text(error_msg)
            logger.error("Gmail open_email HTTP error for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=result_sum,
                error_summary=sanitized_err,
            )
        except (socket.timeout, TimeoutError) as timeout_exc:
            sanitized_err = sanitize_text(f"Timeout: {timeout_exc}")
            logger.error("Gmail open_email timed out for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail API request timed out.",
                error_summary="Gmail open_email timed out waiting for API response.",
            )
        except Exception as api_exc:
            err_str = str(api_exc)
            if "404" in err_str:
                error_msg = f"Gmail message '{message_id}' not found (404 Not Found)."
                result_sum = f"Gmail open_email failed: message '{message_id}' not found."
            elif any(c in err_str for c in ("401", "403", "invalid_grant", "unauthorized")):
                error_msg = "Gmail API authorization error (401/403)."
                result_sum = "Gmail open_email failed: authorization error."
            else:
                error_msg = f"Gmail API error: {type(api_exc).__name__}: {api_exc}"
                result_sum = "Gmail open_email failed with API error."
            sanitized_err = sanitize_text(error_msg)
            logger.error("Gmail open_email failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=result_sum,
                error_summary=sanitized_err,
            )
        finally:
            socket.setdefaulttimeout(orig_timeout)

    def _execute_download_file(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        user_id: str,
        message_id: str,
        attachment_id: str,
        filename: str,
        context: StepExecutionContext,
    ) -> StepExecutionResult:
        """
        Perform authenticated Gmail API messages.attachments.get for the specific attachmentId.
        Decodes base64 data, validates size against limit, and writes safely to controlled directory.
        Zero secret exposure, strict timeout, zero mutation.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.errors import HttpError
        except ImportError as exc:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail execution failed: missing Google client libraries.",
                error_summary=f"Required Google dependencies missing: {exc}",
            )

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[GMAIL_READONLY_SCOPE],
        )

        try:
            request = Request()
            creds.refresh(request)
        except Exception as exc:
            sanitized_err = sanitize_text(f"OAuth refresh failed: {type(exc).__name__}: {exc}")
            logger.error("Gmail OAuth refresh failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed during OAuth token refresh.",
                error_summary=sanitized_err,
            )

        if not creds.token:
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail authentication failed: no access token returned.",
                error_summary="OAuth refresh did not produce an active access token.",
            )

        max_size_bytes = self._get_max_attachment_size_bytes()
        orig_timeout = socket.getdefaulttimeout()

        try:
            socket.setdefaulttimeout(DEFAULT_TIMEOUT_SECONDS)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)

            att_resp = (
                service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=message_id, id=attachment_id)
                .execute()
            )

            # Early size check if reported by Gmail API
            reported_size = att_resp.get("size")
            if isinstance(reported_size, int) and reported_size > max_size_bytes:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file failed: attachment exceeds size limit.",
                    error_summary=f"Attachment size ({reported_size} bytes) exceeds maximum permitted limit ({max_size_bytes} bytes).",
                )

            # Base64 URL-safe decoding
            raw_data = att_resp.get("data", "")
            if not raw_data:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file failed: empty attachment payload.",
                    error_summary="Gmail API returned empty attachment data.",
                )

            try:
                # Convert URL-safe base64 to standard base64 and add padding
                standard_b64 = raw_data.replace("-", "+").replace("_", "/")
                padded_data = standard_b64 + "=" * (-len(standard_b64) % 4)
                decoded_bytes = base64.b64decode(padded_data, validate=True)
            except Exception as b64_err:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file failed: malformed attachment data.",
                    error_summary=f"Failed to decode base64 attachment data: {b64_err}",
                )

            actual_size = len(decoded_bytes)
            if actual_size > max_size_bytes:
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file failed: attachment exceeds size limit.",
                    error_summary=f"Attachment decoded size ({actual_size} bytes) exceeds maximum permitted limit ({max_size_bytes} bytes).",
                )

            # Resolve controlled download directory and collision-safe path
            download_dir = self._get_download_dir()
            target_path = self._get_collision_safe_path(download_dir, filename)

            # Extra security assertion: target path must be strictly inside download_dir
            if not str(target_path.resolve()).startswith(str(download_dir.resolve())):
                return StepExecutionResult(
                    success=False,
                    status=ExecutionStepStatus.FAILED,
                    result_summary="Gmail download_file blocked by path traversal security guard.",
                    error_summary="Resolved path escaped application download directory.",
                )

            # Write file safely
            with open(target_path, "wb") as f:
                f.write(decoded_bytes)

            # Format project-relative path
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            try:
                rel_path = target_path.relative_to(project_root).as_posix()
            except ValueError:
                rel_path = target_path.name

            content_type = mimetypes.guess_type(target_path.name)[0] or "application/octet-stream"

            outputs: Dict[str, Any] = {
                "filename": target_path.name,
                "path": rel_path,
                "size_bytes": actual_size,
                "content_type": content_type,
                "message_id": message_id,
                "attachment_id": attachment_id,
            }

            logger.info(
                "Successfully executed Gmail download_file for execution %s (step %d, file %s, %d bytes).",
                context.execution_id,
                context.step.order,
                target_path.name,
                actual_size,
            )

            return StepExecutionResult(
                success=True,
                status=ExecutionStepStatus.COMPLETED,
                outputs=outputs,
                result_summary=f"Gmail download_file completed successfully: downloaded '{target_path.name}' ({actual_size} bytes).",
                error_summary=None,
            )

        except HttpError as http_exc:
            status_code = getattr(http_exc.resp, "status", None) if hasattr(http_exc, "resp") else getattr(http_exc, "status_code", None)
            if status_code == 404:
                error_msg = f"Gmail attachment or message not found (404 Not Found)."
                result_sum = "Gmail download_file failed: attachment not found."
            elif status_code in (401, 403):
                error_msg = f"Gmail API authorization error ({status_code} Forbidden/Unauthorized)."
                result_sum = "Gmail download_file failed: authorization error."
            elif status_code == 429:
                error_msg = "Gmail API rate limit exceeded (429 Too Many Requests)."
                result_sum = "Gmail download_file failed: rate limit exceeded."
            else:
                error_msg = f"Gmail API HTTP error {status_code}."
                result_sum = "Gmail API request failed."
            sanitized_err = sanitize_text(error_msg)
            logger.error("Gmail download_file HTTP error for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=result_sum,
                error_summary=sanitized_err,
            )
        except (socket.timeout, TimeoutError) as timeout_exc:
            sanitized_err = sanitize_text(f"Timeout: {timeout_exc}")
            logger.error("Gmail download_file timed out for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary="Gmail API request timed out.",
                error_summary="Gmail download_file timed out waiting for API response.",
            )
        except Exception as api_exc:
            err_str = str(api_exc)
            if "404" in err_str:
                error_msg = "Gmail attachment or message not found (404 Not Found)."
                result_sum = "Gmail download_file failed: attachment not found."
            elif any(c in err_str for c in ("401", "403", "invalid_grant", "unauthorized")):
                error_msg = "Gmail API authorization error (401/403)."
                result_sum = "Gmail download_file failed: authorization error."
            else:
                error_msg = f"Gmail API error: {type(api_exc).__name__}: {api_exc}"
                result_sum = "Gmail download_file failed with API error."
            sanitized_err = sanitize_text(error_msg)
            logger.error("Gmail download_file failed for execution %s: %s", context.execution_id, sanitized_err)
            return StepExecutionResult(
                success=False,
                status=ExecutionStepStatus.FAILED,
                result_summary=result_sum,
                error_summary=sanitized_err,
            )
        finally:
            socket.setdefaulttimeout(orig_timeout)
