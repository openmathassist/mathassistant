"""Configuration loading from environment variables and config files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    llm_backend: str = "claude"
    llm_api_key: str | None = None
    llm_endpoint: str | None = None
    llm_model: str | None = None
    default_project_dir: str | None = None

    @classmethod
    def from_env(cls) -> Config:
        backend = os.environ.get("MATHASSIST_LLM_BACKEND", "claude")

        # Pick API key matching the backend, with MATHASSIST_LLM_API_KEY as override
        explicit_key = os.environ.get("MATHASSIST_LLM_API_KEY")
        if explicit_key:
            api_key = explicit_key
        elif backend == "gemini":
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        elif backend == "claude":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        elif backend == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
        else:
            # Fallback: try all
            api_key = (
                os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
            )

        return cls(
            llm_backend=backend,
            llm_api_key=api_key,
            llm_endpoint=os.environ.get("MATHASSIST_LLM_ENDPOINT"),
            llm_model=os.environ.get("MATHASSIST_LLM_MODEL"),
            default_project_dir=os.environ.get("MATHASSIST_PROJECT_DIR"),
        )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
