"""Anthropic LLM provider implementation."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from src.llm.base import BaseLLMProvider

_DEFAULT_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0


def _retry_api_call(fn, *args, retries: int = _DEFAULT_RETRIES, **kwargs):
    """Retry fn on transient errors (connection, timeout, rate limit)."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            err_str = str(e).lower()
            is_retryable = (
                "timeout" in err_str
                or "connection" in err_str
                or "429" in err_str
                or "rate" in err_str
            )
            if not is_retryable or attempt == retries - 1:
                raise
            time.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
    raise last_exc


class AnthropicProvider(BaseLLMProvider):
    def __init__(
        self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None
    ):
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        self._model = model
        self._client = anthropic.Anthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        resp = _retry_api_call(self._client.messages.create, **kwargs)
        return resp.content[0].text if resp.content else ""

    def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        sys_msg = (system or "") + "\nRespond ONLY with valid JSON, no markdown."
        text = self.complete(
            prompt, system=sys_msg, temperature=temperature, max_tokens=max_tokens
        )
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM did not return valid JSON: {e}") from e

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        system_msg = None
        api_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                api_msgs.append(m)
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=api_msgs,
        )
        if system_msg:
            kwargs["system"] = system_msg
        resp = _retry_api_call(self._client.messages.create, **kwargs)
        return resp.content[0].text if resp.content else ""
