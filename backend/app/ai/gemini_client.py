"""
Gemini Client
=============
Thin abstraction over the google-genai SDK.

Responsibilities:
- Load GEMINI_API_KEY from environment (never hardcoded).
- Send a text prompt.
- Return the raw text response.
- Handle and log API errors without exposing credentials.

All other modules interact with Gemini through this module only.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env so that env vars are available when this module is imported
load_dotenv()

# Model to use — prefer flash for low latency; override via GEMINI_MODEL env var if needed
_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


class GeminiClientError(Exception):
    """Raised when the Gemini API call fails or the response is unusable."""


class GeminiClient:
    """
    Wrapper around the google-genai SDK for WorkFlowOS.

    Usage:
        client = GeminiClient()
        text = client.generate(prompt)
    """

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise GeminiClientError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file and restart the server."
            )
        # Keep api_key only inside the SDK client — do NOT store as self.api_key
        try:
            from google import genai  # type: ignore[import]
            self._client = genai.Client(api_key=api_key)
        except ImportError as exc:
            raise GeminiClientError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            ) from exc

        self._model = model
        logger.info("GeminiClient initialised (model=%s).", model)

    def generate(self, prompt: str, *, timeout: int = 30) -> str:
        """
        Send a text prompt and return the model's text response.

        Args:
            prompt:  The full prompt string to send.
            timeout: Request timeout in seconds (not natively enforced by SDK;
                     kept for future retry logic).

        Returns:
            The model's text reply.

        Raises:
            GeminiClientError: on API failure, empty response, or SDK error.
        """
        if not prompt or not prompt.strip():
            raise GeminiClientError("Prompt must not be empty.")

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
        except Exception as exc:  # noqa: BLE001
            # Log message only — never log the prompt (it may contain user data)
            logger.error("Gemini API call failed: %s", type(exc).__name__)
            raise GeminiClientError(f"Gemini API error: {type(exc).__name__}") from exc

        # Extract text from response
        text = _extract_text(response)
        if not text:
            raise GeminiClientError("Gemini returned an empty response.")

        return text

    @property
    def model(self) -> str:
        """The Gemini model being used."""
        return self._model


def _extract_text(response: object) -> str:
    """
    Pull the first text candidate from a Gemini GenerateContentResponse.

    The google-genai SDK exposes response.text as a convenience property.
    """
    try:
        text: str = response.text  # type: ignore[attr-defined]
        return (text or "").strip()
    except Exception:  # noqa: BLE001
        return ""
