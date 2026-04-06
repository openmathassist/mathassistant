"""YAML frontmatter document read/write utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter


@dataclass
class Document:
    meta: dict = field(default_factory=dict)
    body: str = ""
    path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> Document:
        post = frontmatter.load(str(path))
        return cls(meta=dict(post.metadata), body=post.content, path=path)

    @classmethod
    def from_string(cls, text: str) -> Document:
        post = frontmatter.loads(text)
        return cls(meta=dict(post.metadata), body=post.content)

    def to_string(self) -> str:
        post = frontmatter.Post(self.body, **self.meta)
        return frontmatter.dumps(post) + "\n"

    def write(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("No path specified")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_string(), encoding="utf-8")
        self.path = target
        return target
