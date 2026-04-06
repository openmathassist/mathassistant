"""Append-only project log (log.md).

Format: ## [YYYY-MM-DD] operation | Description
Parseable with: grep "^## \\[" log.md | tail -5
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_log(
    project_dir: Path,
    operation: str,
    description: str,
    timestamp: datetime | None = None,
) -> None:
    """Append an entry to log.md."""
    ts = timestamp or datetime.now()
    date_str = ts.strftime("%Y-%m-%d")
    time_str = ts.strftime("%H:%M")

    log_path = project_dir / "log.md"

    if not log_path.exists():
        log_path.write_text("# 项目日志\n\n", encoding="utf-8")

    entry = f"## [{date_str} {time_str}] {operation} | {description}\n\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def read_log(project_dir: Path, last_n: int | None = None) -> list[dict]:
    """Read log entries. Optionally return only the last N entries."""
    log_path = project_dir / "log.md"
    if not log_path.exists():
        return []

    entries = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            # Parse: ## [YYYY-MM-DD HH:MM] operation | description
            try:
                bracket_end = line.index("]")
                timestamp_str = line[4:bracket_end]
                rest = line[bracket_end + 2:]
                if " | " in rest:
                    operation, description = rest.split(" | ", 1)
                else:
                    operation = rest
                    description = ""
                entries.append({
                    "timestamp": timestamp_str,
                    "operation": operation.strip(),
                    "description": description.strip(),
                })
            except (ValueError, IndexError):
                continue

    if last_n is not None:
        entries = entries[-last_n:]
    return entries
