"""Tests for storage/discussion.py."""

from datetime import datetime

from mathassistant.storage.discussion import (
    append_message,
    list_discussions,
    read_discussion,
)


def test_append_and_read(project_dir):
    ts = datetime(2024, 4, 4, 10, 23)
    path, count = append_message(project_dir, "alice", "我觉得可以用归纳法", ts)
    assert path.exists()
    assert count == 1

    doc = read_discussion(project_dir, ts.date())
    assert doc is not None
    assert "alice" in doc.meta["participants"]
    assert "归纳法" in doc.body


def test_multiple_messages(project_dir):
    ts1 = datetime(2024, 4, 4, 10, 0)
    ts2 = datetime(2024, 4, 4, 11, 0)
    append_message(project_dir, "alice", "message 1", ts1)
    path, count = append_message(project_dir, "bob", "message 2", ts2)
    assert count == 2

    doc = read_discussion(project_dir, ts1.date())
    assert "alice" in doc.meta["participants"]
    assert "bob" in doc.meta["participants"]
    assert "message 1" in doc.body
    assert "message 2" in doc.body


def test_read_nonexistent(project_dir):
    from datetime import date

    doc = read_discussion(project_dir, date(2099, 1, 1))
    assert doc is None


def test_list_discussions(project_dir):
    ts1 = datetime(2024, 4, 4, 10, 0)
    ts2 = datetime(2024, 4, 5, 10, 0)
    append_message(project_dir, "alice", "day 1", ts1)
    append_message(project_dir, "bob", "day 2", ts2)
    docs = list_discussions(project_dir)
    assert len(docs) == 2
    # Should be reverse chronological
    assert docs[0].meta["date"] == "2024-04-05"
