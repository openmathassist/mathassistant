"""Git add/commit operations via subprocess."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )


def _generate_commit_message(project_dir: Path) -> str:
    """Generate a structured commit message from staged changes."""
    result = _run_git(project_dir, "diff", "--cached", "--name-only")
    if result.returncode != 0:
        return "Update project files"

    files = [f for f in result.stdout.strip().split("\n") if f]
    if not files:
        return "Update project files"

    # Group by directory
    groups: dict[str, list[str]] = {}
    for f in files:
        parts = f.split("/", 1)
        category = parts[0] if len(parts) > 1 else "root"
        groups.setdefault(category, []).append(f)

    parts = []
    for category, category_files in sorted(groups.items()):
        parts.append(f"[{category}] {len(category_files)} file(s)")

    return "; ".join(parts)


def auto_commit(project_dir: Path, message: str | None = None) -> dict:
    """Stage all changes and commit."""
    # Stage all
    add_result = _run_git(project_dir, "add", "-A")
    if add_result.returncode != 0:
        return {"committed": False, "error": add_result.stderr}

    # Check if there's anything to commit
    status = _run_git(project_dir, "diff", "--cached", "--quiet")
    if status.returncode == 0:
        return {"committed": False, "message": "Nothing to commit"}

    commit_msg = message or _generate_commit_message(project_dir)
    commit_result = _run_git(project_dir, "commit", "-m", commit_msg)
    if commit_result.returncode != 0:
        return {"committed": False, "error": commit_result.stderr}

    # Get commit hash
    hash_result = _run_git(project_dir, "rev-parse", "--short", "HEAD")
    commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else ""

    # Get changed files
    diff_result = _run_git(project_dir, "diff", "--name-only", "HEAD~1", "HEAD")
    changed = [f for f in diff_result.stdout.strip().split("\n") if f] if diff_result.returncode == 0 else []

    return {
        "committed": True,
        "commit_hash": commit_hash,
        "message": commit_msg,
        "files_changed": changed,
    }
