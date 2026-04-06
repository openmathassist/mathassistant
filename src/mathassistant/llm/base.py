"""LLM backend abstraction."""

from __future__ import annotations

import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Send a prompt and return the completion text."""
        ...

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        """Send a prompt and return structured JSON matching the schema."""
        ...


def get_llm_backend() -> LLMBackend:
    """Factory: return the configured LLM backend."""
    from ..config import get_config

    config = get_config()
    backend = config.llm_backend.lower()

    if backend == "claude":
        from .claude import ClaudeBackend

        return ClaudeBackend(
            api_key=config.llm_api_key,
            model=config.llm_model or "claude-sonnet-4-20250514",
        )
    elif backend == "openai":
        from .openai_backend import OpenAIBackend

        return OpenAIBackend(
            api_key=config.llm_api_key,
            model=config.llm_model or "gpt-4o",
            base_url=config.llm_endpoint,
        )
    elif backend == "gemini":
        from .gemini import GeminiBackend

        return GeminiBackend(
            api_key=config.llm_api_key,
            model=config.llm_model or "gemini-2.5-flash",
            thinking_budget=8192,
        )
    elif backend == "http":
        from .http_generic import HTTPBackend

        return HTTPBackend(
            endpoint=config.llm_endpoint or "http://localhost:8080/v1/chat/completions",
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")
