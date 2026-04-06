"""Tests for storage/frontmatter.py."""

from pathlib import Path

from mathassistant.storage.frontmatter import Document


def test_roundtrip(tmp_path: Path):
    doc = Document(
        meta={"type": "discussion", "date": "2024-04-04", "tags": ["algebra"]},
        body="# Hello\n\nSome content.",
    )
    path = doc.write(tmp_path / "test.md")
    loaded = Document.from_file(path)
    assert loaded.meta["type"] == "discussion"
    assert loaded.meta["date"] == "2024-04-04"
    assert "Hello" in loaded.body
    assert "Some content" in loaded.body


def test_from_string():
    text = """---
type: lemma
status: draft
---

# Lemma 1

If $f$ is continuous then...
"""
    doc = Document.from_string(text)
    assert doc.meta["type"] == "lemma"
    assert doc.meta["status"] == "draft"
    assert "$f$" in doc.body


def test_write_creates_parent_dirs(tmp_path: Path):
    doc = Document(meta={"id": "test"}, body="content")
    path = doc.write(tmp_path / "a" / "b" / "test.md")
    assert path.exists()
    loaded = Document.from_file(path)
    assert loaded.meta["id"] == "test"
