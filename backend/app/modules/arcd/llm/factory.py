"""Factory function for LLM provider instantiation."""

from __future__ import annotations

from app.modules.arcd.llm.base import BaseLLMProvider


def get_llm_provider(
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> BaseLLMProvider:
    """Instantiate an LLM provider by name.

    Args:
        provider: ``"openai"`` or ``"anthropic"``.
        model: Model identifier (provider-specific default if *None*).
        api_key: API key override; falls back to environment variable.
    """
    provider = provider.lower().strip()
    if provider == "openai":
        from app.modules.arcd.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(model=model or "gpt-4o", api_key=api_key)
    elif provider == "anthropic":
        from app.modules.arcd.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=model or "claude-sonnet-4-20250514", api_key=api_key
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider!r}. Use 'openai' or 'anthropic'."
        )
