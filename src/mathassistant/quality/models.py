"""Quality check data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    check_name: str
    severity: Severity
    message: str
    question: str | None = None  # Question for user if severity != PASS

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "severity": self.severity.value,
            "message": self.message,
            "question": self.question,
        }


@dataclass
class QualityReport:
    results: list[CheckResult]

    @property
    def overall(self) -> Severity:
        if any(r.severity == Severity.FAIL for r in self.results):
            return Severity.FAIL
        if any(r.severity == Severity.WARN for r in self.results):
            return Severity.WARN
        return Severity.PASS

    @property
    def top_issue(self) -> CheckResult | None:
        """Return the most critical failing check."""
        fails = [r for r in self.results if r.severity == Severity.FAIL]
        if fails:
            return fails[0]
        warns = [r for r in self.results if r.severity == Severity.WARN]
        if warns:
            return warns[0]
        return None

    def to_dict(self) -> dict:
        top = self.top_issue
        return {
            "overall": self.overall.value,
            "checks": {r.check_name: r.to_dict() for r in self.results},
            "top_issue": top.to_dict() if top else None,
        }
