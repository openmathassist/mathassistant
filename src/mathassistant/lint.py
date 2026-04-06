"""Project-level health checks (lint).

Detects: contradictions, orphan pages, missing concepts,
unextracted problems, and suggests next investigation directions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .llm.base import LLMBackend, get_llm_backend
from .storage.frontmatter import Document

LINT_SYSTEM_PROMPT = """\
You are a mathematical research project auditor. Analyze the provided project
content and identify issues. Be specific and actionable.

Respond as JSON with this structure:
{
  "issues": [
    {"type": "contradiction|orphan|missing_concept|unextracted_problem|stale|redundant",
     "severity": "high|medium|low",
     "description": "...",
     "files": ["file1.md", "file2.md"],
     "suggestion": "..."}
  ],
  "next_steps": [
    {"direction": "...", "reason": "..."}
  ]
}"""


def _collect_project_content(project_dir: Path) -> dict[str, list[dict]]:
    """Collect all project documents for analysis."""
    content = {}
    for subdir in ["conclusions", "problems", "discussions", "attempts"]:
        d = project_dir / subdir
        if not d.exists():
            content[subdir] = []
            continue
        items = []
        for f in sorted(d.glob("*.md")):
            try:
                doc = Document.from_file(f)
                items.append({
                    "file": f"{subdir}/{f.name}",
                    "meta": doc.meta,
                    "body": doc.body[:2000],  # Truncate for token budget
                })
            except Exception:
                pass
        content[subdir] = items
    return content


def _check_orphan_pages(content: dict[str, list[dict]]) -> list[dict]:
    """Find pages not referenced by any other page."""
    issues = []
    # Collect all file references across all documents
    all_refs = set()
    all_files = set()
    for subdir, items in content.items():
        for item in items:
            all_files.add(item["file"])
            # Find markdown links
            refs = re.findall(r"\[.*?\]\((.*?)\)", item["body"])
            for ref in refs:
                all_refs.add(ref.strip("./"))

    for f in all_files:
        basename = f.split("/")[-1]
        if not any(basename in ref or f in ref for ref in all_refs):
            # Not referenced anywhere — but skip discussions (they're raw sources)
            if not f.startswith("discussions/"):
                issues.append({
                    "type": "orphan",
                    "severity": "low",
                    "description": f"{f} is not referenced by any other page",
                    "files": [f],
                    "suggestion": f"Consider adding a reference to {f} in related discussions or conclusions, or archive it if no longer needed",
                })
    return issues


def _check_missing_cross_refs(content: dict[str, list[dict]]) -> list[dict]:
    """Find problems without related conclusions and vice versa."""
    issues = []
    problems = content.get("problems", [])
    conclusions = content.get("conclusions", [])

    for p in problems:
        # Check if any conclusion references this problem
        pid = p["meta"].get("id", "")
        referenced = False
        for c in conclusions:
            if pid in c["body"] or pid in json.dumps(c["meta"]):
                referenced = True
                break
        if not referenced and pid:
            issues.append({
                "type": "missing_concept",
                "severity": "medium",
                "description": f"Problem {pid} has no related conclusion page",
                "files": [p["file"]],
                "suggestion": "Are there partial conclusions in discussions that could be extracted for this problem?",
            })

    return issues


async def run_lint(
    project_dir: Path,
    llm: LLMBackend | None = None,
) -> dict:
    """Run all project-level health checks."""
    content = _collect_project_content(project_dir)

    # Rule-based checks (fast, no LLM needed)
    issues = []
    issues.extend(_check_orphan_pages(content))
    issues.extend(_check_missing_cross_refs(content))

    # LLM-based deep analysis (contradictions, unextracted problems, suggestions)
    llm = llm or get_llm_backend()

    # Build a compact project summary for the LLM
    summary_parts = []
    for subdir, items in content.items():
        if items:
            summary_parts.append(f"### {subdir} ({len(items)} files)")
            for item in items:
                summary_parts.append(f"**{item['file']}** (status: {item['meta'].get('status', 'n/a')})")
                summary_parts.append(item["body"][:500])
                summary_parts.append("")

    project_summary = "\n".join(summary_parts)

    if project_summary.strip():
        response = await llm.complete(
            LINT_SYSTEM_PROMPT,
            f"Please audit the following math research project:\n\n{project_summary}",
        )

        try:
            data = json.loads(response.strip().strip("`").strip())
            llm_issues = data.get("issues", [])
            next_steps = data.get("next_steps", [])
            issues.extend(llm_issues)
        except json.JSONDecodeError:
            next_steps = []
    else:
        next_steps = [{"direction": "Project is empty, start adding discussions or problems", "reason": "Project initialization"}]

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 2))

    return {
        "issues": issues,
        "issue_count": len(issues),
        "next_steps": next_steps,
    }
