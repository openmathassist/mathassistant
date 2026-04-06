"""Generic HTTP endpoint backend (OpenAI-compatible API)."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen


class HTTPBackend:
    def __init__(
        self,
        endpoint: str = "http://localhost:8080/v1/chat/completions",
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model or "default"

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = Request(
            self._endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(req) as resp:
            data = json.loads(resp.read())

        # OpenAI-compatible response format
        return data["choices"][0]["message"]["content"]

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
