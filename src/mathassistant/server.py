"""FastMCP server entry point - registers all tools."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mathassistant")


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
# Git tools (Phase 2)
# ---------------------------------------------------------------------------


@mcp.tool()
def git_sync(project_dir: str, message: str | None = None) -> dict:
    """Stage all changes and commit to Git. Auto-generates commit message if omitted."""
    from .git_sync import auto_commit

    return auto_commit(Path(project_dir), message)


# ---------------------------------------------------------------------------
# Project management tools (Phase 2)
# ---------------------------------------------------------------------------


@mcp.tool()
def init_project(project_dir: str, project_name: str) -> dict:
    """Initialize a new math research project with directory structure and git init."""
    from .project import initialize_project

    return initialize_project(Path(project_dir), project_name)


@mcp.tool()
def get_project_state(project_dir: str) -> dict:
    """Get an overview of the project: discussions, conclusions, problems, attempts."""
    from .project import project_state

    return project_state(Path(project_dir))


# ---------------------------------------------------------------------------
# Summary tools (Phase 4)
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
    import asyncio

    return asyncio.run(summarize(Path(project_dir), d, scope))


# ---------------------------------------------------------------------------
# Problem refinement tools (Phase 6)
# ---------------------------------------------------------------------------


@mcp.tool()
def detect_problems(
    project_dir: str,
    content: str,
    context_messages: list[str] | None = None,
) -> dict:
    """Analyze text for signals of provable mathematical problems."""
    from .refinement.detector import detect

    import asyncio

    return asyncio.run(detect(Path(project_dir), content, context_messages))


@mcp.tool()
def draft_problem(
    project_dir: str,
    source_text: str,
    context_messages: list[str] | None = None,
    problem_type: str = "conjecture",
) -> dict:
    """Generate a draft problem file from discussion context. Does not write to disk."""
    from .refinement.drafter import create_draft

    import asyncio

    return asyncio.run(
        create_draft(Path(project_dir), source_text, context_messages, problem_type)
    )


@mcp.tool()
def check_problem_quality(
    project_dir: str,
    draft_id: str | None = None,
    problem_path: str | None = None,
) -> dict:
    """Run the 7-point quality checker on a problem draft or existing problem file."""
    from .quality.checker import run_checks

    import asyncio

    return asyncio.run(run_checks(Path(project_dir), draft_id, problem_path))


@mcp.tool()
def refine_problem(
    project_dir: str,
    draft_id: str,
    user_response: str,
) -> dict:
    """Incorporate user response into problem draft. Re-runs quality checker."""
    from .refinement.loop import refine

    import asyncio

    return asyncio.run(refine(Path(project_dir), draft_id, user_response))


@mcp.tool()
def finalize_problem(project_dir: str, draft_id: str) -> dict:
    """Write finalized problem to problems/*.md and commit to Git."""
    from .refinement.loop import finalize

    import asyncio

    return asyncio.run(finalize(Path(project_dir), draft_id))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
