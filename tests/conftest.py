"""Shared test fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with git init and basic structure."""
    dirs = ["discussions", "conclusions", "problems", "attempts", "references", ".mathassist"]
    for d in dirs:
        (tmp_path / d).mkdir()
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


class MockLLMBackend:
    """Mock LLM backend for deterministic testing."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        self.calls.append((system_prompt, user_message))
        for pattern, response in self.responses.items():
            if pattern in user_message:
                return response
        return "Mock LLM response"

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        self.calls.append((system_prompt, user_message))
        for pattern, response in self.responses.items():
            if pattern in user_message:
                if isinstance(response, dict):
                    return response
                return {"text": response}
        return {"text": "Mock structured response"}


@pytest.fixture
def mock_llm() -> MockLLMBackend:
    return MockLLMBackend()
