"""Detect provable-problem signals in discussion text."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm.base import LLMBackend, get_llm_backend

DETECT_SYSTEM_PROMPT = """\
You are a mathematical research assistant. Analyze the given text for signals
that a provable mathematical problem is being discussed. Look for:
- Conjectures ("we conjecture that...", "猜想...")
- Lemma/theorem proposals ("we need to prove...", "需要证明...")
- Questions about truth value ("is it true that...", "是否成立...")
- Proof requests ("can we show...", "能否证明...")

Respond with JSON only."""


async def detect(
    project_dir: Path,
    content: str,
    context_messages: list[str] | None = None,
    llm: LLMBackend | None = None,
) -> dict:
    """Detect problem signals in text."""
    llm = llm or get_llm_backend()

    context_str = ""
    if context_messages:
        context_str = "\n\nRecent context:\n" + "\n".join(context_messages[-5:])

    response = await llm.complete(
        DETECT_SYSTEM_PROMPT,
        f"Analyze this text for mathematical problem signals:\n\n{content}{context_str}\n\n"
        f'Respond as JSON: {{"detected": true/false, "candidates": [{{"signal_text": "...", "problem_type": "conjecture|lemma|proposition", "confidence": 0.0-1.0}}]}}'
    )

    try:
        data = json.loads(response.strip().strip("`").strip())
        return {
            "detected": data.get("detected", False),
            "candidates": data.get("candidates", []),
        }
    except json.JSONDecodeError:
        return {"detected": False, "candidates": []}
