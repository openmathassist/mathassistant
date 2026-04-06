"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    author: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: str | None = None
    message_id: str | None = None


@dataclass
class ProjectStats:
    discussion_count: int = 0
    conclusion_count: int = 0
    problem_count: int = 0
    attempt_count: int = 0
    reference_count: int = 0
