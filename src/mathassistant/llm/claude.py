"""Anthropic Claude backend."""

from __future__ import annotations

import json


class ClaudeBackend:
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        try:
            import anthropic
        except ImportError:
            raise ImportError("Install anthropic: pip install mathassistant[claude]")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: dict,
        temperature: float = 0.1,
    ) -> dict:
        prompt = (
            f"{user_message}\n\n"
            f"Respond with a JSON object matching this schema:\n"
            f"```json\n{json.dumps(response_schema, indent=2)}\n```\n"
            f"Output ONLY valid JSON, no other text."
        )
        text = await self.complete(system_prompt, prompt, temperature=temperature)
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
