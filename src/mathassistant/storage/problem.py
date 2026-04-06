"""Problem file operations - problems/*.md."""

from __future__ import annotations

from pathlib import Path

from .frontmatter import Document


def list_problems(project_dir: Path) -> list[Document]:
    """List all problem files."""
    prob_dir = project_dir / "problems"
    if not prob_dir.exists():
        return []
    return [Document.from_file(f) for f in sorted(prob_dir.glob("*.md"))]


def read_problem(path: Path) -> Document:
    """Read a problem file."""
    return Document.from_file(path)
