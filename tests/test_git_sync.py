"""Tests for git_sync.py and project.py."""

from datetime import datetime

from mathassistant.git_sync import auto_commit
from mathassistant.project import initialize_project, project_state
from mathassistant.storage.discussion import append_message


def test_auto_commit_nothing(project_dir):
    result = auto_commit(project_dir)
    assert not result["committed"]


def test_auto_commit_with_discussion(project_dir):
    append_message(project_dir, "alice", "test message", datetime(2024, 4, 4, 10, 0))
    result = auto_commit(project_dir)
    assert result["committed"]
    assert result["commit_hash"]
    assert "discussions" in result["message"]


def test_auto_commit_custom_message(project_dir):
    append_message(project_dir, "alice", "msg", datetime(2024, 4, 4, 10, 0))
    result = auto_commit(project_dir, "custom commit message")
    assert result["committed"]
    assert result["message"] == "custom commit message"


def test_initialize_project(tmp_path):
    pdir = tmp_path / "new-project"
    result = initialize_project(pdir, "Test Project")
    assert result["git_initialized"]
    assert (pdir / "discussions").is_dir()
    assert (pdir / "problems").is_dir()
    assert (pdir / "README.md").exists()
    assert (pdir / "problem.md").exists()


def test_project_state(project_dir):
    append_message(project_dir, "alice", "hello", datetime(2024, 4, 4, 10, 0))
    state = project_state(project_dir)
    assert state["discussions"]["count"] == 1
    assert state["problems"]["count"] == 0
