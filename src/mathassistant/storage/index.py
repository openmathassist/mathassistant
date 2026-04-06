"""Maintain .mathassist/index.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def update_index(project_dir: Path) -> dict:
    """Rebuild and save the project index."""
    index = {
        "last_updated": datetime.now().isoformat(),
    }

    for subdir in ["discussions", "conclusions", "problems", "attempts", "references"]:
        d = project_dir / subdir
        if d.exists():
            files = list(d.glob("*.md"))
            index[subdir] = {
                "count": len(files),
                "files": [f.name for f in sorted(files)],
            }
        else:
            index[subdir] = {"count": 0, "files": []}

    index_path = project_dir / ".mathassist" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index
