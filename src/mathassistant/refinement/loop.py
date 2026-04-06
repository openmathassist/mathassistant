"""Problem refinement loop state machine."""

from __future__ import annotations

import json
from pathlib import Path

from ..git_sync import auto_commit
from ..llm.base import LLMBackend, get_llm_backend
from ..quality.checker import run_quality_checks
from ..storage.frontmatter import Document

REFINE_SYSTEM_PROMPT = """\
You are a mathematical research assistant. The user has responded to a quality check
question about a problem draft. Update the problem draft to incorporate their response.

Output the COMPLETE updated problem body (all sections: Definitions, Assumptions, Goal, etc.).
Do NOT output JSON — output the full Markdown body directly."""


def _load_draft(project_dir: Path, draft_id: str) -> dict | None:
    draft_path = project_dir / ".mathassist" / "drafts" / f"{draft_id}.json"
    if not draft_path.exists():
        return None
    return json.loads(draft_path.read_text())


def _save_draft(project_dir: Path, draft_id: str, data: dict) -> None:
    draft_path = project_dir / ".mathassist" / "drafts" / f"{draft_id}.json"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


async def refine(
    project_dir: Path,
    draft_id: str,
    user_response: str,
    llm: LLMBackend | None = None,
) -> dict:
    """Incorporate user response, update draft, re-run quality checks."""
    llm = llm or get_llm_backend()

    draft_data = _load_draft(project_dir, draft_id)
    if draft_data is None:
        return {"error": f"Draft {draft_id} not found"}

    doc = Document(meta=draft_data["meta"], body=draft_data["body"])

    # Get the current top issue for context
    top_issue = draft_data["meta"].get("check_results", {}).get("top_issue", {})
    question_context = top_issue.get("question", "") if top_issue else ""

    # Ask LLM to update the draft
    updated_body = await llm.complete(
        REFINE_SYSTEM_PROMPT,
        f"Current problem draft:\n\n{doc.body}\n\n"
        f"Quality check question: {question_context}\n\n"
        f"User response: {user_response}\n\n"
        f"Please output the complete updated problem document (Markdown format).",
    )

    # Update draft
    doc.body = updated_body.strip() + "\n"
    doc.meta["refinement_status"] = "checking"

    # Record history
    history = draft_data["meta"].get("check_history", [])
    history.append({
        "round": len(history) + 1,
        "issue": question_context,
        "user_response": user_response,
    })
    doc.meta["check_history"] = history

    # Re-run quality checks
    report = await run_quality_checks(doc, llm)
    doc.meta["check_results"] = report.to_dict()

    ready = report.overall.value == "pass"
    if ready:
        doc.meta["refinement_status"] = "confirmed"
    else:
        doc.meta["refinement_status"] = "waiting_user"

    # Save updated draft
    draft_data["meta"] = doc.meta
    draft_data["body"] = doc.body
    _save_draft(project_dir, draft_id, draft_data)

    result = {
        "draft_id": draft_id,
        "body_preview": doc.body[:1000],
        "check_results": report.to_dict(),
        "ready_to_finalize": ready,
    }
    if not ready and report.top_issue:
        result["next_question"] = report.top_issue.question

    return result


async def finalize(
    project_dir: Path,
    draft_id: str,
) -> dict:
    """Write finalized problem to problems/*.md and commit."""
    draft_data = _load_draft(project_dir, draft_id)
    if draft_data is None:
        return {"error": f"Draft {draft_id} not found"}

    meta = draft_data["meta"]
    body = draft_data["body"]

    # Clean up meta for the final file
    final_meta = {
        "id": meta.get("id", draft_id),
        "type": meta.get("type", "conjecture"),
        "status": "open",
    }
    if meta.get("check_history"):
        final_meta["refinement_rounds"] = len(meta["check_history"])

    doc = Document(meta=final_meta, body=body)

    # Generate filename from first heading or id
    import re
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if title_match:
        slug = re.sub(r"[^\w\s-]", "", title_match.group(1).lower())
        slug = re.sub(r"[\s]+", "-", slug.strip())[:50]
    else:
        slug = draft_id

    file_path = project_dir / "problems" / f"{slug}.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    doc.write(file_path)

    # Commit
    commit_result = auto_commit(project_dir, f"[problems] Add: {slug}")

    # Clean up draft
    draft_path = project_dir / ".mathassist" / "drafts" / f"{draft_id}.json"
    if draft_path.exists():
        draft_path.unlink()

    return {
        "file_path": str(file_path),
        "commit_hash": commit_result.get("commit_hash", ""),
        "committed": commit_result.get("committed", False),
    }
