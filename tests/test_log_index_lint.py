"""Tests for log.md, index.md, lint, and batch ingest."""

import json
from datetime import datetime

import pytest

from mathassistant.storage.log import append_log, read_log
from mathassistant.storage.index import update_index
from mathassistant.storage.discussion import append_message
from mathassistant.storage.frontmatter import Document
from mathassistant.lint import run_lint, _check_orphan_pages, _collect_project_content
from mathassistant.ingest import batch_ingest_sources
from mathassistant.project import initialize_project


# ---------------------------------------------------------------------------
# Log tests
# ---------------------------------------------------------------------------


def test_append_and_read_log(project_dir):
    append_log(project_dir, "ingest", "导入论文 A")
    append_log(project_dir, "refine", "problem-001 精炼完成")
    entries = read_log(project_dir)
    assert len(entries) == 2
    assert entries[0]["operation"] == "ingest"
    assert entries[1]["operation"] == "refine"
    assert "论文 A" in entries[0]["description"]


def test_read_log_last_n(project_dir):
    for i in range(10):
        append_log(project_dir, "test", f"entry {i}")
    entries = read_log(project_dir, last_n=3)
    assert len(entries) == 3
    assert "entry 9" in entries[-1]["description"]


def test_log_parseable_with_grep(project_dir):
    """Log entries should be grep-parseable."""
    append_log(project_dir, "ingest", "test")
    log_path = project_dir / "log.md"
    content = log_path.read_text()
    # Should match: ## [YYYY-MM-DD HH:MM] operation | description
    import re
    matches = re.findall(r"^## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] .+ \| .+$", content, re.MULTILINE)
    assert len(matches) == 1


# ---------------------------------------------------------------------------
# Index tests
# ---------------------------------------------------------------------------


def test_update_index_creates_both_files(project_dir):
    append_message(project_dir, "alice", "hello", datetime(2024, 4, 4, 10, 0))
    update_index(project_dir)

    # Check index.md
    index_md = project_dir / "index.md"
    assert index_md.exists()
    content = index_md.read_text()
    assert "项目索引" in content
    assert "讨论记录" in content
    assert "2024-04-04" in content

    # Check index.json
    index_json = project_dir / ".mathassist" / "index.json"
    assert index_json.exists()
    data = json.loads(index_json.read_text())
    assert data["discussions"]["count"] == 1


def test_index_includes_summaries(project_dir):
    # Create a conclusion with content
    doc = Document(
        meta={"id": "lemma-1", "type": "lemma", "status": "verified"},
        body="# 紧致性引理\n\n如果 $X$ 是紧致的，则...\n",
    )
    doc.write(project_dir / "conclusions" / "lemma-1.md")
    update_index(project_dir)

    content = (project_dir / "index.md").read_text()
    assert "lemma-1" in content
    assert "紧致性引理" in content


# ---------------------------------------------------------------------------
# Init project tests (schema.md, log.md)
# ---------------------------------------------------------------------------


def test_init_creates_schema_and_log(tmp_path):
    pdir = tmp_path / "new-project"
    initialize_project(pdir, "Test")
    assert (pdir / "schema.md").exists()
    assert (pdir / "log.md").exists()
    assert (pdir / "index.md").exists()
    schema = (pdir / "schema.md").read_text()
    assert "AI 行为规范" in schema


# ---------------------------------------------------------------------------
# Lint tests
# ---------------------------------------------------------------------------


def test_check_orphan_pages(project_dir):
    """Conclusions not referenced anywhere should be flagged."""
    doc = Document(
        meta={"id": "orphan-lemma", "type": "lemma"},
        body="# Orphan Lemma\n\nNo one links here.\n",
    )
    doc.write(project_dir / "conclusions" / "orphan-lemma.md")

    content = _collect_project_content(project_dir)
    issues = _check_orphan_pages(content)
    orphan_files = [i["files"][0] for i in issues]
    assert "conclusions/orphan-lemma.md" in orphan_files


def test_check_orphan_ignores_discussions(project_dir):
    """Discussions are raw sources and should not be flagged as orphans."""
    append_message(project_dir, "alice", "test", datetime(2024, 4, 4, 10, 0))
    content = _collect_project_content(project_dir)
    issues = _check_orphan_pages(content)
    orphan_files = [i["files"][0] for i in issues if i["type"] == "orphan"]
    assert not any(f.startswith("discussions/") for f in orphan_files)


class LintMockLLM:
    async def complete(self, system_prompt, user_message, **kwargs):
        return json.dumps({
            "issues": [
                {
                    "type": "contradiction",
                    "severity": "high",
                    "description": "conclusion-1 和 conclusion-2 的结论矛盾",
                    "files": ["conclusions/c1.md", "conclusions/c2.md"],
                    "suggestion": "需要检查哪个结论正确",
                }
            ],
            "next_steps": [
                {"direction": "补充关于可分性的讨论", "reason": "多处提到但没有结论"}
            ],
        })

    async def complete_structured(self, system_prompt, user_message, response_schema, **kwargs):
        text = await self.complete(system_prompt, user_message)
        return json.loads(text)


@pytest.mark.asyncio
async def test_lint_full(project_dir):
    # Add some content so LLM analysis is triggered
    doc = Document(
        meta={"id": "c1", "type": "lemma", "status": "verified"},
        body="# Conclusion 1\n\n$X$ is compact.\n",
    )
    doc.write(project_dir / "conclusions" / "c1.md")

    llm = LintMockLLM()
    result = await run_lint(project_dir, llm)
    assert result["issue_count"] > 0
    assert any(i["type"] == "contradiction" for i in result["issues"])
    assert len(result["next_steps"]) > 0


# ---------------------------------------------------------------------------
# Batch ingest tests
# ---------------------------------------------------------------------------


class IngestMockLLM:
    async def complete(self, system_prompt, user_message, **kwargs):
        return "## 关键结果\n\nTheorem 1: 如果 $X$ 满足条件，则..."

    async def complete_structured(self, system_prompt, user_message, response_schema, **kwargs):
        return {"text": "summary"}


@pytest.mark.asyncio
async def test_batch_ingest_paper(project_dir):
    llm = IngestMockLLM()
    result = await batch_ingest_sources(project_dir, [
        {
            "type": "paper",
            "title": "On Compact Operators",
            "author": "A. Smith",
            "content": "We prove that compact operators on Banach spaces...",
        },
    ], llm=llm)
    assert result["ingested"] == 1
    assert result["errors"] == 0
    # Check file was created in references/
    refs = list((project_dir / "references").glob("*.md"))
    assert len(refs) == 1
    # Check log was updated
    entries = read_log(project_dir)
    assert any("ingest" in e["operation"] for e in entries)


@pytest.mark.asyncio
async def test_batch_ingest_discussion(project_dir):
    llm = IngestMockLLM()
    result = await batch_ingest_sources(project_dir, [
        {
            "type": "discussion",
            "title": "历史讨论导入",
            "author": "alice",
            "content": "之前在邮件中讨论的内容...",
            "timestamp": "2024-01-15T10:00:00",
        },
    ], llm=llm)
    assert result["ingested"] == 1
    # Check discussion was recorded
    from mathassistant.storage.discussion import read_discussion
    from datetime import date
    doc = read_discussion(project_dir, date(2024, 1, 15))
    assert doc is not None
    assert "历史讨论导入" in doc.body
