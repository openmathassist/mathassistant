"""Generate problem draft from discussion context."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..llm.base import LLMBackend, get_llm_backend
from ..storage.frontmatter import Document

DRAFT_SYSTEM_PROMPT = """\
You are a mathematical research assistant. Generate a self-contained problem document
from the given discussion text. The document must:

1. Define ALL mathematical objects and symbols used
2. State ALL assumptions explicitly (no implicit "everyone knows")
3. Have a clear, precise goal (a concrete mathematical proposition)
4. Be readable WITHOUT the original discussion context

Use LaTeX notation for math ($...$).

Structure your response as JSON with these fields:
- title: problem title
- definitions: section text defining all objects
- assumptions: numbered list of assumptions
- goal: the precise statement to prove
- known_results: any relevant known results (optional)
- notes: proof intuitions from the discussion (optional)"""


async def create_draft(
    project_dir: Path,
    source_text: str,
    context_messages: list[str] | None = None,
    problem_type: str = "conjecture",
    llm: LLMBackend | None = None,
) -> dict:
    """Generate a problem draft. Does not write to disk yet."""
    llm = llm or get_llm_backend()

    context_str = ""
    if context_messages:
        context_str = "\n\nDiscussion context:\n" + "\n".join(context_messages[-10:])

    response = await llm.complete(
        DRAFT_SYSTEM_PROMPT,
        f"Extract a problem from the following discussion:\n\n{source_text}{context_str}\n\n"
        f"Problem type: {problem_type}\n"
        f"Respond as JSON with fields: title, definitions, assumptions, goal, known_results, notes"
    )

    from ..quality.checks import _extract_json
    data = _extract_json(response)
    if data is None:
        data = {
            "title": "Undefined problem",
            "definitions": source_text,
            "assumptions": "",
            "goal": "",
            "known_results": "",
            "notes": "",
        }

    draft_id = f"draft-{uuid.uuid4().hex[:6]}"

    # Build markdown body
    body_parts = [f"# {data.get('title', 'Problem')}"]
    if data.get("definitions"):
        body_parts.append(f"\n## Definitions\n\n{data['definitions']}")
    if data.get("assumptions"):
        body_parts.append(f"\n## Assumptions\n\n{data['assumptions']}")
    if data.get("goal"):
        body_parts.append(f"\n## Goal\n\n{data['goal']}")
    if data.get("known_results"):
        body_parts.append(f"\n## Known Results\n\n{data['known_results']}")
    if data.get("notes"):
        body_parts.append(f"\n## Notes\n\n{data['notes']}")

    body = "\n".join(body_parts) + "\n"

    meta = {
        "id": draft_id,
        "type": problem_type,
        "status": "draft",
        "refinement_status": "drafting",
        "check_results": {},
        "check_history": [],
    }

    # Persist draft to .mathassist/drafts/
    draft_data = {"meta": meta, "body": body, "source_text": source_text}
    drafts_dir = project_dir / ".mathassist" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_path = drafts_dir / f"{draft_id}.json"
    draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2))

    slug = data.get("title", "problem").lower().replace(" ", "-")[:40]
    proposed_path = f"problems/{slug}.md"

    return {
        "draft_id": draft_id,
        "title": data.get("title", ""),
        "body_preview": body[:1000],
        "file_path_proposed": proposed_path,
    }
