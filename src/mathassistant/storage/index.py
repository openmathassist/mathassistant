"""Maintain index.md (human-readable) and .mathassist/index.json (machine-readable).

index.md is the LLM's primary navigation entry point — it reads this first
before drilling into specific pages.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .frontmatter import Document


def _one_line_summary(doc: Document) -> str:
    """Extract a one-line summary from a Document."""
    # Try first heading
    match = re.search(r"^#\s+(.+)$", doc.body, re.MULTILINE)
    title = match.group(1).strip() if match else doc.meta.get("id", "untitled")

    # Try first non-heading, non-empty line as description
    desc = ""
    for line in doc.body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            desc = line[:80]
            if len(line) > 80:
                desc += "..."
            break

    status = doc.meta.get("status", "")
    status_str = f" [{status}]" if status else ""
    return f"{title}{status_str}" + (f" — {desc}" if desc else "")


def _section_entries(project_dir: Path, subdir: str) -> list[dict]:
    """Collect entries for a subdirectory."""
    d = project_dir / subdir
    if not d.exists():
        return []
    entries = []
    for f in sorted(d.glob("*.md")):
        try:
            doc = Document.from_file(f)
            entries.append({
                "file": f"{subdir}/{f.name}",
                "id": doc.meta.get("id", f.stem),
                "type": doc.meta.get("type", ""),
                "status": doc.meta.get("status", ""),
                "summary": _one_line_summary(doc),
            })
        except Exception:
            entries.append({
                "file": f"{subdir}/{f.name}",
                "id": f.stem,
                "summary": "(parse error)",
            })
    return entries


def update_index(project_dir: Path) -> dict:
    """Rebuild both index.md and .mathassist/index.json."""
    sections = {}
    for subdir in ["problems", "conclusions", "discussions", "attempts", "references"]:
        sections[subdir] = _section_entries(project_dir, subdir)

    # --- Write index.md (human-readable, LLM navigation entry) ---
    lines = [
        "# Project Index",
        "",
        f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    section_labels = {
        "problems": "Problems",
        "conclusions": "Conclusions",
        "discussions": "Discussions",
        "attempts": "Attempts",
        "references": "References",
    }

    for subdir, label in section_labels.items():
        entries = sections[subdir]
        lines.append(f"## {label} ({len(entries)})")
        lines.append("")
        if entries:
            for e in entries:
                lines.append(f"- [{e['id']}]({e['file']}) — {e['summary']}")
            lines.append("")
        else:
            lines.append("(none)")
            lines.append("")

    index_md_path = project_dir / "index.md"
    index_md_path.write_text("\n".join(lines), encoding="utf-8")

    # --- Write .mathassist/index.json (machine-readable) ---
    index_json = {
        "last_updated": datetime.now().isoformat(),
    }
    for subdir, entries in sections.items():
        index_json[subdir] = {
            "count": len(entries),
            "entries": entries,
        }

    json_path = project_dir / ".mathassist" / "index.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(index_json, indent=2, ensure_ascii=False), encoding="utf-8")

    return index_json
