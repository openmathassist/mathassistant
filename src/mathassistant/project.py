"""Project initialization and state queries."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .storage.frontmatter import Document

PROJECT_DIRS = ["discussions", "conclusions", "problems", "attempts", "references", ".mathassist"]


def initialize_project(project_dir: Path, project_name: str) -> dict:
    """Initialize a new math research project."""
    project_dir.mkdir(parents=True, exist_ok=True)

    created_dirs = []
    for d in PROJECT_DIRS:
        p = project_dir / d
        p.mkdir(exist_ok=True)
        created_dirs.append(d)

    # Create README
    readme = Document(
        meta={
            "type": "project",
            "created": __import__("datetime").date.today().isoformat(),
            "status": "active",
        },
        body=f"# {project_name}\n\n数学研究项目。\n",
    )
    readme.write(project_dir / "README.md")

    # Create problem.md template
    problem = Document(
        meta={
            "type": "problem",
            "status": "open",
            "participants": [],
            "keywords": [],
        },
        body="# 问题定义\n\n## 陈述\n\n[待填写]\n\n## 动机\n\n[待填写]\n",
    )
    problem.write(project_dir / "problem.md")

    # Create schema.md (project-level AI behavior spec, evolves over time)
    schema_path = project_dir / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(
            f"# {project_name} — AI 行为规范\n\n"
            "此文件定义 AI 在本项目中的行为规范，随项目演进可更新。\n\n"
            "## 领域约定\n\n[待填写：本项目涉及的数学领域、常用记号约定]\n\n"
            "## 工作偏好\n\n- 语言：中文为主，数学术语保留英文\n"
            "- 证明风格：[待定]\n"
            "- 问题精炼：优先确保自包含性\n\n"
            "## 优先级\n\n[待填写：当前阶段的重点方向]\n",
            encoding="utf-8",
        )

    # Create log.md
    log_path = project_dir / "log.md"
    if not log_path.exists():
        log_path.write_text("# 项目日志\n\n", encoding="utf-8")

    # Build initial index
    from .storage.index import update_index
    update_index(project_dir)

    # Git init if not already
    git_initialized = False
    if not (project_dir / ".git").exists():
        result = subprocess.run(
            ["git", "init"], cwd=project_dir, capture_output=True, text=True
        )
        git_initialized = result.returncode == 0
    else:
        git_initialized = True

    return {
        "project_dir": str(project_dir),
        "project_name": project_name,
        "created_dirs": created_dirs,
        "git_initialized": git_initialized,
    }


def project_state(project_dir: Path) -> dict:
    """Get project overview."""

    def count_md(subdir: str) -> int:
        d = project_dir / subdir
        return len(list(d.glob("*.md"))) if d.exists() else 0

    def list_items(subdir: str) -> list[dict]:
        d = project_dir / subdir
        if not d.exists():
            return []
        items = []
        for f in sorted(d.glob("*.md")):
            try:
                doc = Document.from_file(f)
                items.append({
                    "file": f.name,
                    "id": doc.meta.get("id", f.stem),
                    "type": doc.meta.get("type", ""),
                    "status": doc.meta.get("status", ""),
                })
            except Exception:
                items.append({"file": f.name, "error": "parse failed"})
        return items

    return {
        "discussions": {
            "count": count_md("discussions"),
            "files": list_items("discussions"),
        },
        "conclusions": {
            "count": count_md("conclusions"),
            "items": list_items("conclusions"),
        },
        "problems": {
            "count": count_md("problems"),
            "items": list_items("problems"),
        },
        "attempts": {
            "count": count_md("attempts"),
            "items": list_items("attempts"),
        },
        "references": {
            "count": count_md("references"),
            "items": list_items("references"),
        },
    }
