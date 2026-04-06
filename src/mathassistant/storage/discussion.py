"""Discussion file operations - discussions/YYYY-MM-DD.md."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .frontmatter import Document


def _discussion_path(project_dir: Path, d: date) -> Path:
    return project_dir / "discussions" / f"{d.isoformat()}.md"


def append_message(
    project_dir: Path,
    author: str,
    content: str,
    timestamp: datetime | None = None,
) -> tuple[Path, int]:
    """Append a message to today's discussion file. Returns (file_path, message_count)."""
    ts = timestamp or datetime.now()
    d = ts.date()
    path = _discussion_path(project_dir, d)

    if path.exists():
        doc = Document.from_file(path)
        participants = set(doc.meta.get("participants", []))
        participants.add(author)
        doc.meta["participants"] = sorted(participants)
    else:
        doc = Document(
            meta={
                "date": d.isoformat(),
                "type": "discussion",
                "participants": [author],
                "topics": [],
            },
            body=f"# {d.isoformat()} Discussion\n",
            path=path,
        )

    time_str = ts.strftime("%H:%M")
    doc.body += f"\n## {time_str} - {author}\n\n{content}\n"

    count = doc.body.count("\n## ")
    doc.write(path)
    return path, count


def read_discussion(
    project_dir: Path, d: date | None = None
) -> Document | None:
    """Read a discussion file. Defaults to today."""
    target_date = d or date.today()
    path = _discussion_path(project_dir, target_date)
    if not path.exists():
        return None
    return Document.from_file(path)


def list_discussions(project_dir: Path) -> list[Document]:
    """List all discussion files, sorted by date descending."""
    disc_dir = project_dir / "discussions"
    if not disc_dir.exists():
        return []
    files = sorted(disc_dir.glob("*.md"), reverse=True)
    return [Document.from_file(f) for f in files]
