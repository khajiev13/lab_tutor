"""OpenAI LLM provider implementation."""

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


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._model = model
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format

        def _create():
            return self._client.chat.completions.create(**kwargs)

        resp = _retry_api_call(_create)
        return (resp.choices[0].message.content or "") if resp.choices else ""

    def complete_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        text = self.complete(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
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
        def _create():
            return self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        resp = _retry_api_call(_create)
        return (resp.choices[0].message.content or "") if resp.choices else ""
