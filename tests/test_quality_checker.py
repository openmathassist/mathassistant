"""Tests for quality checker with mock LLM."""

import json

import pytest

from mathassistant.quality.checker import run_quality_checks
from mathassistant.quality.models import Severity
from mathassistant.storage.frontmatter import Document


class QualityMockLLM:
    """Mock LLM that returns structured JSON for quality checks."""

    def __init__(self, overrides: dict[str, dict] | None = None):
        self.overrides = overrides or {}
        self.calls = []

    async def complete(self, system_prompt, user_message, **kwargs):
        self.calls.append(user_message[:100])

        # Default: everything passes
        if "all_defined" in user_message or "symbols" in user_message.lower():
            resp = self.overrides.get("definitions", {"all_defined": True})
        elif "implicit" in user_message.lower() or "explicit" in user_message.lower():
            resp = self.overrides.get("assumptions_explicit", {"all_explicit": True})
        elif "consistent" in user_message.lower() or "contradictions" in user_message.lower():
            resp = self.overrides.get("assumptions_consistent", {"consistent": True})
        elif "concrete" in user_message.lower() or "proposition" in user_message.lower():
            resp = self.overrides.get("goal_clarity", {"clear": True})
        elif "appropriate" in user_message.lower() or "type" in user_message.lower():
            resp = self.overrides.get("type_strength", {"appropriate": True})
        elif "formalizable" in user_message.lower() or "prover" in user_message.lower():
            resp = self.overrides.get("formalizability", {"formalizable": True, "difficulty": "medium"})
        elif "boundary" in user_message.lower() or "edge" in user_message.lower():
            resp = self.overrides.get("edge_cases", {"covered": True})
        else:
            resp = {"result": "pass"}

        return json.dumps(resp)

    async def complete_structured(self, system_prompt, user_message, response_schema, **kwargs):
        text = await self.complete(system_prompt, user_message)
        return json.loads(text)


@pytest.fixture
def good_problem():
    return Document(
        meta={"type": "conjecture", "id": "test-001"},
        body="""# 压缩映射不动点

## 定义

设 $(X, d)$ 为完备度量空间，$f: X \\to X$ 为映射。

## 假设条件

1. $X$ 是完备度量空间
2. 存在 $0 < k < 1$ 使得 $d(f(x), f(y)) \\leq k \\cdot d(x, y)$ 对所有 $x, y \\in X$ 成立

## 目标

证明：$f$ 存在唯一不动点 $x^* \\in X$，即 $f(x^*) = x^*$。
""",
    )


@pytest.mark.asyncio
async def test_all_checks_pass(good_problem):
    llm = QualityMockLLM()
    report = await run_quality_checks(good_problem, llm)
    assert report.overall == Severity.PASS
    assert report.top_issue is None
    assert len(report.results) == 7


@pytest.mark.asyncio
async def test_undefined_symbols_detected(good_problem):
    llm = QualityMockLLM(overrides={
        "definitions": {
            "all_defined": False,
            "undefined": ["T"],
            "question": "$T$ 是什么？请补充定义。",
        }
    })
    report = await run_quality_checks(good_problem, llm)
    assert report.overall == Severity.FAIL
    assert report.top_issue is not None
    assert report.top_issue.check_name == "definitions"
    assert report.top_issue.question is not None


@pytest.mark.asyncio
async def test_implicit_assumptions_detected(good_problem):
    llm = QualityMockLLM(overrides={
        "assumptions_explicit": {
            "all_explicit": False,
            "implicit": ["空间的可分性"],
            "question": "是否需要假设空间是可分的？",
        }
    })
    report = await run_quality_checks(good_problem, llm)
    assert report.overall == Severity.FAIL
    fail_checks = [r for r in report.results if r.severity == Severity.FAIL]
    assert any(r.check_name == "assumptions_explicit" for r in fail_checks)


@pytest.mark.asyncio
async def test_report_to_dict(good_problem):
    llm = QualityMockLLM()
    report = await run_quality_checks(good_problem, llm)
    d = report.to_dict()
    assert d["overall"] == "pass"
    assert "definitions" in d["checks"]
    assert len(d["checks"]) == 7
