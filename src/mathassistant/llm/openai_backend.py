"""OpenAI backend."""

from __future__ import annotations

import json


class OpenAIBackend:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        try:
            import openai
        except ImportError:
            raise ImportError("Install openai: pip install mathassistant[openai]")
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

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
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
