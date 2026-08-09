"""Pluggable LLM client.

Provider is selected entirely via environment variables so the same code can
target DeepSeek (default), OpenAI, Azure, or any OpenAI-compatible endpoint.

Env vars:
    LLM_PROVIDER   - "deepseek" (default) | "openai" | "azure" | "custom"
    LLM_API_BASE   - base URL, e.g. https://api.deepseek.com/v1
    LLM_API_KEY    - your API key (keep in .env, git-ignored)
    LLM_MODEL      - e.g. deepseek-chat
"""

import os

from django.conf import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


class LLMClientError(RuntimeError):
    pass


class LLMClient:
    """Thin OpenAI-compatible wrapper used by all agents."""

    def __init__(self, api_key=None, base_url=None, model=None, timeout=None):
        self.api_key = api_key or getattr(settings, "LLM_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or getattr(settings, "LLM_API_BASE", "https://api.deepseek.com/v1")
        self.model = model or getattr(settings, "LLM_MODEL", "deepseek-chat")
        self.timeout = timeout or getattr(settings, "LLM_TIMEOUT", 60)

        if OpenAI is None:
            raise LLMClientError("openai package not installed.")

        # (connect, read) timeout tuple: unreachable endpoints (bad base URL,
        # dead provider) fail fast at connect so agents fall back to the
        # deterministic path quickly instead of hanging the full read budget.
        connect_timeout = min(10, self.timeout)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=(connect_timeout, self.timeout),
        )

    def _check_ready(self):
        if not self.api_key:
            raise LLMClientError(
                "LLM_API_KEY not configured. Set it in your .env file. "
                "No API key is stored in code."
            )

    def complete(self, system_prompt, user_prompt, max_tokens=1200, temperature=0.2):
        """Return model text response for a two-part prompt."""
        self._check_ready()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as exc:
            # Treat any upstream failure (auth, network, bad base URL) as an
            # LLM unavailability so agents fall back to deterministic mode.
            raise LLMClientError(f"LLM call failed: {exc}") from exc


def get_llm_client():
    """Return a configured LLMClient based on current settings."""
    return LLMClient()


def is_configured():
    """True when an API key is available in settings/env."""
    return bool(getattr(settings, "LLM_API_KEY", "") or os.getenv("LLM_API_KEY", ""))
