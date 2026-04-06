"""Batch ingest: import multiple sources (papers, historical discussions).

Supports two source types:
- "paper": creates a reference page in references/
- "discussion": appends to discussions/ as historical record
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .llm.base import LLMBackend, get_llm_backend
from .storage.frontmatter import Document
from .storage.index import update_index
from .storage.log import append_log

PAPER_SUMMARY_PROMPT = """\
You are a mathematical research assistant. Summarize this paper/article for a
research wiki. Include:
1. Key results (theorems, lemmas) with precise statements
2. Relevance to ongoing research
3. Techniques that might be useful

Use LaTeX for math ($...$)."""


async def _ingest_paper(
    project_dir: Path,
    source: dict,
    llm: LLMBackend,
) -> dict:
    """Ingest a paper source into references/."""
    title = source.get("title", "untitled")
    content = source.get("content", "")
    author = source.get("author", "")

    # Generate summary via LLM
    summary = await llm.complete(
        PAPER_SUMMARY_PROMPT,
        f"Paper title: {title}\nAuthor: {author}\n\nContent:\n{content[:8000]}",
    )

    # Create slug for filename
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s]+", "-", slug.strip())[:50]

    doc = Document(
        meta={
            "id": slug,
            "type": "paper",
            "title": title,
            "author": author,
            "ingested": datetime.now().isoformat(),
            "source": source.get("source", ""),
        },
        body=f"# {title}\n\n**Author**: {author}\n\n## Summary and Key Results\n\n{summary}\n\n## Excerpt\n\n{content[:3000]}\n",
    )
    path = doc.write(project_dir / "references" / f"{slug}.md")
    return {"type": "paper", "file": str(path), "title": title}


def _ingest_discussion(
    project_dir: Path,
    source: dict,
) -> dict:
    """Ingest a historical discussion."""
    from .storage.discussion import append_message

    content = source.get("content", "")
    author = source.get("author", "unknown")
    title = source.get("title", "")
    ts_str = source.get("timestamp")
    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now()

    full_content = f"[Import] {title}\n\n{content}" if title else content
    path, count = append_message(project_dir, author, full_content, ts)
    return {"type": "discussion", "file": str(path), "message_count": count}


async def batch_ingest_sources(
    project_dir: Path,
    sources: list[dict],
    llm: LLMBackend | None = None,
) -> dict:
    """Batch ingest multiple sources.

    Each source: {"type": "paper"|"discussion", "content": "...", "title": "...", "author": "..."}
    """
    llm = llm or get_llm_backend()
    results = []

    for source in sources:
        source_type = source.get("type", "discussion")
        try:
            if source_type == "paper":
                r = await _ingest_paper(project_dir, source, llm)
            else:
                r = _ingest_discussion(project_dir, source)
            results.append(r)
            append_log(
                project_dir,
                "ingest",
                f"{source_type}: {source.get('title', source.get('content', '')[:40])}",
            )
        except Exception as e:
            results.append({
                "type": source_type,
                "error": str(e),
                "title": source.get("title", ""),
            })

    # Rebuild index after batch
    update_index(project_dir)

    return {
        "ingested": len([r for r in results if "error" not in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results,
    }
