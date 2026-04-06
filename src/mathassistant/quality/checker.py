"""Quality checker orchestrator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..llm.base import LLMBackend, get_llm_backend
from ..storage.frontmatter import Document
from .checks import ALL_CHECKS
from .models import QualityReport


async def run_quality_checks(
    doc: Document,
    llm: LLMBackend | None = None,
) -> QualityReport:
    """Run all 7 quality checks in parallel on a problem document."""
    llm = llm or get_llm_backend()
    results = await asyncio.gather(*[check(doc, llm) for check in ALL_CHECKS])
    return QualityReport(results=list(results))


async def run_checks(
    project_dir: Path,
    draft_id: str | None = None,
    problem_path: str | None = None,
) -> dict:
    """MCP tool entry point: run quality checks on a draft or problem file."""
    if problem_path:
        doc = Document.from_file(Path(problem_path))
    elif draft_id:
        draft_path = project_dir / ".mathassist" / "drafts" / f"{draft_id}.json"
        if not draft_path.exists():
            return {"error": f"Draft {draft_id} not found"}
        data = json.loads(draft_path.read_text())
        doc = Document(meta=data["meta"], body=data["body"])
    else:
        return {"error": "Must provide draft_id or problem_path"}

    report = await run_quality_checks(doc)
    return report.to_dict()
