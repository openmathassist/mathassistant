"""
LLM Backend for Google Gemini models.
"""
from google.genai import Client, types


class GeminiBackend:
    """Google Gemini LLM backend using google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        thinking_budget: int = -1,  # -1 means disabled
    ):
        """
        Initialize Gemini backend.

        Args:
            api_key: Google AI API key
            model: Model name (default: gemini-2.5-flash)
            thinking_budget: Thinking budget for extended thinking (0 = disabled)
        """
        self._client = Client(api_key=api_key)
        self._model = model
        self.thinking_budget = thinking_budget

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Send a prompt and return the completion text."""
        from google.genai import types

        # Build contents - prepend system prompt as first message if provided
        if system_prompt and system_prompt.strip():
            contents = [
                types.Content(role="user", parts=[types.Part(text=system_prompt + "\n\n" + user_message)])
            ]
        else:
            contents = [
                types.Content(role="user", parts=[types.Part(text=user_message)])
            ]

        try:
            # google-genai 0.8.x API
            # Note: Not using config parameter to avoid region restriction issues
            response = await self._client.models.generate_content(
                model=self._model,
                contents=contents,
            )
        except Exception as e:
            return f"Error: {e}"

        # Extract text from response - new API uses response.text
        if hasattr(response, 'text') and response.text:
            return response.text

        # Fallback: try to extract from candidates
        if response.candidates:
            response_text = ""
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            response_text += part.text
            return response_text if response_text else "No text in response"

        return "No response generated"
