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
# Verification tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_knowledge(project_dir: str, query: str, max_results: int = 5) -> dict:
    """Search project knowledge base for relevant theorems, definitions, and results.
    
    This is a lightweight theorem search - searches through project markdown files
    for content matching the query. For deep theorem search, consider integrating
    with external tools like Semantic Scholar API.
    
    Args:
        project_dir: Project directory to search in
        query: Search query (can be mathematical concept, theorem name, etc.)
        max_results: Maximum number of results to return (default 5)
    
    Returns:
        dict with list of relevant results (file paths, snippets, relevance scores)
    """
    import json
    from pathlib import Path
    from ..llm.base import get_llm_backend, _extract_json

    project = Path(project_dir)
    if not project.exists():
        return {"error": f"Project not found: {project_dir}", "results": []}

    # Search through markdown files
    md_files = list(project.rglob("*.md"))
    results = []
    
    query_lower = query.lower()
    
    for md_file in md_files:
        # Skip hidden and draft files for search
        if "/." in str(md_file) or "draft" in str(md_file):
            continue
            
        try:
            content = md_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            
            # Find matching lines
            matches = []
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Get context (surrounding lines)
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = "\n".join(lines[start:end])
                    matches.append({
                        "line": i + 1,
                        "text": line.strip()[:200],
                        "context": context[:500]
                    })
            
            if matches:
                results.append({
                    "file": str(md_file.relative_to(project)),
                    "matches": matches[:3],  # Top 3 matches per file
                    "score": len(matches)
                })
                
        except Exception:
            continue
    
    # Sort by score and limit
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:max_results]
    
    # Clean up for return
    for r in results:
        del r["score"]
        for m in r["matches"]:
            del m["score"] if "score" in m else None
    
    return {
        "query": query,
        "results": results,
        "total_files_searched": len(md_files)
    }


@mcp.tool()
def detect_gaps(content: str, proof_type: str = "standard") -> dict:
    """Detect potential gaps in a proof using LLM analysis.
    
    This tool analyzes proof content to identify:
    - Missing steps
    - Implicit assumptions
    - Logical gaps
    - Unjustified claims
    
    Args:
        content: The proof content to analyze
        proof_type: Type of proof ("standard", "induction", "constructive", "existence")
    
    Returns:
        dict with identified gaps and suggestions
    """
    from ..llm.base import get_llm_backend, _extract_json
    import json
    import asyncio

    llm = get_llm_backend()
    
    prompt = f"""Analyze this proof and identify any gaps, missing steps, or logical issues.

Proof type hint: {proof_type}

Proof content:
{content}

Identify:
1. Missing steps (steps that are assumed without justification)
2. Implicit assumptions (things used but not stated)
3. Logical gaps (jumps in reasoning)
4. Unjustified claims (assertions without proof)
5. Circular reasoning (if any)

Respond ONLY with JSON:
{{
  "has_gaps": true/false,
  "gap_count": number,
  "gaps": [
    {{
      "type": "missing_step|implicit_assumption|logical_gap|unjustified_claim",
      "location": "brief description of where in proof",
      "description": "what's missing or wrong",
      "severity": "high|medium|low",
      "suggestion": "how to fix"
    }}
  ],
  "overall_assessment": "brief summary"
}}"""

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(loop.run_until_complete, llm.complete(
                "You are a mathematical proof reviewer.", prompt
            ))
            response = future.result()
    except RuntimeError:
        response = asyncio.run(llm.complete(
            "You are a mathematical proof reviewer.", prompt
        ))

    data = _extract_json(response)
    if data is None:
        return {
            "has_gaps": False,
            "gap_count": 0,
            "gaps": [],
            "error": "Could not parse LLM response"
        }
    
    return {
        "has_gaps": data.get("has_gaps", False),
        "gap_count": data.get("gap_count", 0),
        "gaps": data.get("gaps", []),
        "overall_assessment": data.get("overall_assessment", "")
    }


@mcp.tool()
def classify_conjecture(project_dir: str, file_path: str) -> dict:
    """Classify a conjecture/problem and map its relationships.
    
    Analyzes a problem file to determine:
    - Conjecture type (existence, uniqueness, classification, bound, equivalence)
    - Difficulty level
    - Relationships to other problems
    
    Args:
        project_dir: Project directory
        file_path: Path to problem/conjecture file
    
    Returns:
        dict with classification and relationships
    """
    from ..llm.base import get_llm_backend, _extract_json
    import json
    import asyncio
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text()
    llm = get_llm_backend()
    
    prompt = f"""Classify this mathematical problem/conjecture.

Content:
{content[:3000]}

Determine:
1. Type: existence|uniqueness|classification|bound|equivalence|other
2. Difficulty: easy|medium|hard|open|unknown
3. Key mathematical structures involved
4. Potential generalizations
5. Related problem types

Respond ONLY with JSON:
{{
  "type": "existence|uniqueness|classification|bound|equivalence|other",
  "difficulty": "easy|medium|hard|open|unknown",
  "structures": ["list of mathematical structures"],
  "generalizations": ["possible generalizations"],
  "related_types": ["related problem types"],
  "keywords": ["relevant keywords for search"]
}}"""

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(loop.run_until_complete, llm.complete(
                "You are a mathematical classifier.", prompt
            ))
            response = future.result()
    except RuntimeError:
        response = asyncio.run(llm.complete(
            "You are a mathematical classifier.", prompt
        ))

    data = _extract_json(response)
    if data is None:
        return {
            "type": "unknown",
            "difficulty": "unknown",
            "error": "Could not parse LLM response"
        }
    
    # Update frontmatter if it exists
    # (This is a basic implementation - could be extended)
    
    return {
        "file": str(path.relative_to(Path(project_dir))),
        "type": data.get("type", "unknown"),
        "difficulty": data.get("difficulty", "unknown"),
        "structures": data.get("structures", []),
        "generalizations": data.get("generalizations", []),
        "related_types": data.get("related_types", []),
        "keywords": data.get("keywords", [])
    }


@mcp.tool()
def verify_markdown(file_path: str, verification_type: str = "problem") -> dict:
    """Verify a markdown file using LLM (via MCP server for clean context isolation).
    
    Args:
        file_path: Path to the md file to verify
        verification_type: "problem" or "proof"
            - "problem": Verify statement is complete, correct, non-trivial, well-posed
            - "proof": Verify proof is complete, correct, no gaps, no errors
    
    Returns:
        dict with keys: valid (bool), issues (list), message (str)
    """
    from .llm.base import get_llm_backend
    from .quality.checks import _extract_json
    import json
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        return {"valid": False, "issues": [], "message": f"File not found: {file_path}"}

    content = path.read_text()
    llm = get_llm_backend()

    if verification_type == "problem":
        prompt = f"""You are a mathematical quality checker. Analyze this problem statement and determine if it is:
- Complete: all assumptions stated
- Correct: mathematically sound  
- Non-trivial: has substance, not obvious
- Well-posed: no ambiguity

Problem statement:
{content}

Respond ONLY with JSON:
{{"valid": true/false, "issues": ["issue1", "issue2", ...], "message": "brief explanation"}}"""
    else:  # proof
        prompt = f"""You are a mathematical proof verifier. Analyze this proof and determine if it is:
- Complete: all steps present
- Correct: logic valid
- No gaps: no missing reasoning steps
- No errors: no mathematical mistakes

Proof content:
{content}

Respond ONLY with JSON:
{{"valid": true/false, "gaps": ["gap1", ...], "errors": ["error1", ...], "message": "brief explanation"}}"""

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(loop.run_until_complete, llm.complete("You are a helpful assistant.", prompt))
            response = future.result()
    except RuntimeError:
        response = asyncio.run(llm.complete("You are a helpful assistant.", prompt))

    data = _extract_json(response)
    if data is None:
        return {"valid": False, "issues": ["Could not parse LLM response"], "message": response[:200] if response else "No response"}

    if verification_type == "problem":
        return {
            "valid": data.get("valid", False),
            "issues": data.get("issues", []),
            "message": data.get("message", "")
        }
    else:  # proof
        return {
            "valid": data.get("valid", False),
            "issues": data.get("gaps", []) + data.get("errors", []),
            "message": data.get("message", "")
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
