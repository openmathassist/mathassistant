"""Discussion summary generation via LLM."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .llm.base import LLMBackend, get_llm_backend
from .storage.discussion import list_discussions, read_discussion

SUMMARY_SYSTEM_PROMPT = """\
You are a mathematical research assistant. Summarize the given discussion concisely.
Focus on:
1. Key mathematical ideas and claims discussed
2. Conjectures or problems raised
3. Conclusions reached or open questions remaining
4. Action items or next steps mentioned

Output in the same language as the discussion (Chinese if the discussion is in Chinese).
Keep the summary under 500 words."""


async def summarize(
    project_dir: Path,
    target_date: date | None = None,
    scope: str = "day",
    llm: LLMBackend | None = None,
) -> dict:
    """Generate a summary of discussions."""
    llm = llm or get_llm_backend()

    if scope == "day":
        d = target_date or date.today()
        doc = read_discussion(project_dir, d)
        if doc is None:
            return {"summary": "", "date_range": d.isoformat(), "error": "No discussion found"}
        content = doc.body
        date_range = d.isoformat()
    else:  # week
        end = target_date or date.today()
        start = end - timedelta(days=7)
        docs = list_discussions(project_dir)
        relevant = [
            doc for doc in docs
            if doc.meta.get("date") and start.isoformat() <= doc.meta["date"] <= end.isoformat()
        ]
        if not relevant:
            return {"summary": "", "date_range": f"{start} to {end}", "error": "No discussions found"}
        content = "\n\n---\n\n".join(
            f"## {doc.meta.get('date', 'unknown')}\n\n{doc.body}" for doc in relevant
        )
        date_range = f"{start.isoformat()} to {end.isoformat()}"

    summary_text = await llm.complete(
        SUMMARY_SYSTEM_PROMPT,
        f"请总结以下讨论内容:\n\n{content}",
    )

    return {
        "summary": summary_text,
        "date_range": date_range,
        "scope": scope,
    }
