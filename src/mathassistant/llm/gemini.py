"""Google Gemini backend using the google-genai SDK.

Supports thinking budget for deeper reasoning on math problems.
"""

from __future__ import annotations

import json


class GeminiBackend:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        thinking_budget: int = 8192,
    ):
        try:
            from google import genai
        except ImportError:
            raise ImportError("Install google-genai: pip install google-genai")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._thinking_budget = thinking_budget

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_budget=self._thinking_budget,
            ),
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_message,
            config=config,
        )
        # Extract text parts (skip thinking parts)
        parts = response.candidates[0].content.parts
        text_parts = [p.text for p in parts if p.text and not p.thought]
        return "\n".join(text_parts)

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
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
