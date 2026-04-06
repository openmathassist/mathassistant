"""FastMCP server entry point - registers all tools."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mathassistant")


def _run_async(coro):
    """Run coroutine safely from sync or async context (Python 3.10+)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — create one
        return asyncio.run(coro)
    else:
        # Running loop exists — nest gracefully
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(loop.run_until_complete, coro)
            return future.result()


def _cascade_update(project_dir: Path, operation: str, description: str) -> None:
    """Log the operation and refresh index."""
    from .storage.log import append_log
    from .storage.index import update_index

    append_log(Path(project_dir), operation, description)
    update_index(Path(project_dir))


# ---------------------------------------------------------------------------
# Discussion tools
# ---------------------------------------------------------------------------


@mcp.tool()
def record_message(
    project_dir: str,
    author: str,
    content: str,
    timestamp: str | None = None,
) -> dict:
    """Record a message to the daily discussion log (discussions/YYYY-MM-DD.md).

    Returns the file path and message count for today.
    """
    from .storage.discussion import append_message

    ts = datetime.fromisoformat(timestamp) if timestamp else None
    path, count = append_message(Path(project_dir), author, content, ts)
    _cascade_update(project_dir, "message", f"{author}: {content[:60]}")
    return {
        "file_path": str(path),
        "message_count_today": count,
    }


@mcp.tool()
def get_discussion_history(
    project_dir: str,
    date_str: str | None = None,
    limit: int = 50,
) -> dict:
    """Read discussion history for a given date (defaults to today)."""
    from .storage.discussion import read_discussion

    d = date.fromisoformat(date_str) if date_str else None
    doc = read_discussion(Path(project_dir), d)
    if doc is None:
        return {"found": False, "date": (d or date.today()).isoformat()}
    return {
        "found": True,
        "date": doc.meta.get("date", ""),
        "participants": doc.meta.get("participants", []),
        "topics": doc.meta.get("topics", []),
        "body": doc.body[:5000] if len(doc.body) > 5000 else doc.body,
    }


# ---------------------------------------------------------------------------
# Git tools
# ---------------------------------------------------------------------------


@mcp.tool()
def git_sync(project_dir: str, message: str | None = None) -> dict:
    """Stage all changes and commit to Git. Auto-generates commit message if omitted."""
    from .git_sync import auto_commit

    result = auto_commit(Path(project_dir), message)
    if result.get("committed"):
        _cascade_update(project_dir, "git-sync", result.get("message", "commit"))
    return result


# ---------------------------------------------------------------------------
# Project management tools
# ---------------------------------------------------------------------------


@mcp.tool()
def init_project(project_dir: str, project_name: str) -> dict:
    """Initialize a new math research project with directory structure and git init."""
    from .project import initialize_project

    result = initialize_project(Path(project_dir), project_name)
    _cascade_update(project_dir, "init", f"Project initialized: {project_name}")
    return result


@mcp.tool()
def get_project_state(project_dir: str) -> dict:
    """Get an overview of the project: discussions, conclusions, problems, attempts."""
    from .project import project_state

    return project_state(Path(project_dir))


@mcp.tool()
def get_project_log(project_dir: str, last_n: int = 20) -> dict:
    """Read the project activity log. Returns the last N entries."""
    from .storage.log import read_log

    entries = read_log(Path(project_dir), last_n)
    return {"entries": entries, "count": len(entries)}


@mcp.tool()
def get_project_index(project_dir: str) -> dict:
    """Read the project index (content catalog with summaries). LLM should read this first."""
    index_path = Path(project_dir) / "index.md"
    if not index_path.exists():
        from .storage.index import update_index
        update_index(Path(project_dir))
    return {"index": index_path.read_text(encoding="utf-8") if index_path.exists() else ""}


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------


@mcp.tool()
def generate_summary(
    project_dir: str,
    date_str: str | None = None,
    scope: str = "day",
) -> dict:
    """Generate an LLM summary of recent discussions."""
    from .summarizer import summarize

    d = date.fromisoformat(date_str) if date_str else None
    result = _run_async(summarize(Path(project_dir), d, scope))
    _cascade_update(project_dir, "summary", f"Generated {scope} summary")
    return result


# ---------------------------------------------------------------------------
# Problem refinement tools
# ---------------------------------------------------------------------------


@mcp.tool()
def detect_problems(
    project_dir: str,
    content: str,
    context_messages: list[str] | None = None,
) -> dict:
    """Analyze text for signals of provable mathematical problems."""
    from .refinement.detector import detect

    result = _run_async(detect(Path(project_dir), content, context_messages))
    if result.get("detected"):
        n = len(result.get("candidates", []))
        _cascade_update(project_dir, "detect", f"Detected {n} problem signal(s)")
    return result


@mcp.tool()
def draft_problem(
    project_dir: str,
    source_text: str,
    context_messages: list[str] | None = None,
    problem_type: str = "conjecture",
) -> dict:
    """Generate a draft problem file from discussion context. Does not write to disk."""
    from .refinement.drafter import create_draft

    result = _run_async(
        create_draft(Path(project_dir), source_text, context_messages, problem_type)
    )
    _cascade_update(
        project_dir, "draft", f"Created problem draft {result.get('draft_id', '')}: {result.get('title', '')[:40]}"
    )
    return result


@mcp.tool()
def check_problem_quality(
    project_dir: str,
    draft_id: str | None = None,
    problem_path: str | None = None,
) -> dict:
    """Run the 7-point quality checker on a problem draft or existing problem file."""
    from .quality.checker import run_checks

    return _run_async(run_checks(Path(project_dir), draft_id, problem_path))


@mcp.tool()
def refine_problem(
    project_dir: str,
    draft_id: str,
    user_response: str,
) -> dict:
    """Incorporate user response into problem draft. Re-runs quality checker."""
    from .refinement.loop import refine

    result = _run_async(refine(Path(project_dir), draft_id, user_response))
    status = "passed" if result.get("ready_to_finalize") else "refining"
    _cascade_update(project_dir, "refine", f"{draft_id} {status}")
    return result


@mcp.tool()
def finalize_problem(project_dir: str, draft_id: str) -> dict:
    """Write finalized problem to problems/*.md and commit to Git."""
    from .refinement.loop import finalize

    result = _run_async(finalize(Path(project_dir), draft_id))
    if not result.get("error"):
        _cascade_update(project_dir, "finalize", f"Problem written to {result.get('file_path', '')}")
    return result


# ---------------------------------------------------------------------------
# Lint tool
# ---------------------------------------------------------------------------


@mcp.tool()
def lint_project(project_dir: str) -> dict:
    """Run project-level health checks: contradictions, orphans, missing concepts, suggestions."""
    from .lint import run_lint

    result = _run_async(run_lint(Path(project_dir)))
    n_issues = len(result.get("issues", []))
    _cascade_update(project_dir, "lint", f"Found {n_issues} issue(s)")
    return result


# ---------------------------------------------------------------------------
# Batch ingest tool
# ---------------------------------------------------------------------------


@mcp.tool()
def batch_ingest(
    project_dir: str,
    sources: list[dict],
) -> dict:
    """Batch ingest multiple sources (papers, historical discussions).

    Each source: {"type": "paper"|"discussion", "content": "...", "title": "...", "author": "..."}
    """
    from .ingest import batch_ingest_sources

    result = _run_async(batch_ingest_sources(Path(project_dir), sources))
    _cascade_update(project_dir, "batch-ingest", f"Batch ingested {len(sources)} source(s)")
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
