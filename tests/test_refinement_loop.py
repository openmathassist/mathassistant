"""End-to-end test for problem refinement loop with mock LLM."""

import json

import pytest

from mathassistant.refinement.detector import detect
from mathassistant.refinement.drafter import create_draft
from mathassistant.refinement.loop import finalize, refine


class RefinementMockLLM:
    """Mock LLM for refinement loop testing."""

    def __init__(self):
        self.round = 0

    async def complete(self, system_prompt, user_message, **kwargs):
        # Detection
        if "signals" in user_message.lower() or "detected" in user_message.lower():
            return json.dumps({
                "detected": True,
                "candidates": [{
                    "signal_text": "对所有紧致算子 T，谱半径趋于 0",
                    "problem_type": "conjecture",
                    "confidence": 0.9,
                }],
            })

        # Drafting
        if "提取问题" in user_message or "从以下讨论" in user_message:
            return json.dumps({
                "title": "紧致算子谱半径收敛",
                "definitions": "设 $X$ 为 Banach 空间，$T: X \\to X$ 为紧致算子。",
                "assumptions": "1. $X$ 是 Banach 空间\n2. $T$ 是紧致算子",
                "goal": "证明：$\\lim_{n \\to \\infty} r(T^n) = 0$",
                "known_results": "",
                "notes": "讨论中提到可能需要 r(T) < 1 的条件",
            })

        # Refinement (updating draft with user response)
        if "更新后的完整问题文档" in user_message:
            return (
                "# 紧致算子谱半径收敛\n\n"
                "## 定义\n\n设 $X$ 为 Banach 空间，$T: X \\to X$ 为紧致算子，$r(T)$ 为谱半径。\n\n"
                "## 假设条件\n\n1. $X$ 是 Banach 空间\n2. $T$ 是紧致算子\n3. $r(T) < 1$\n\n"
                "## 目标\n\n证明：$\\lim_{n \\to \\infty} r(T^n) = 0$\n"
            )

        # Quality checks - simulate different rounds
        self.round += 1

        if "all_defined" in user_message or "symbols" in user_message.lower():
            if self.round <= 7:
                return json.dumps({"all_defined": False, "undefined": ["r(T)"], "question": "$r(T)$ 表示什么？请定义谱半径。"})
            return json.dumps({"all_defined": True})

        if "implicit" in user_message.lower() or "explicit" in user_message.lower():
            return json.dumps({"all_explicit": True})
        if "consistent" in user_message.lower():
            return json.dumps({"consistent": True})
        if "concrete" in user_message.lower() or "clear" in user_message.lower():
            return json.dumps({"clear": True})
        if "appropriate" in user_message.lower():
            return json.dumps({"appropriate": True})
        if "formalizable" in user_message.lower():
            return json.dumps({"formalizable": True, "difficulty": "medium"})
        if "boundary" in user_message.lower() or "edge" in user_message.lower():
            return json.dumps({"covered": True})

        return json.dumps({"result": "pass"})

    async def complete_structured(self, system_prompt, user_message, response_schema, **kwargs):
        text = await self.complete(system_prompt, user_message)
        return json.loads(text)


@pytest.mark.asyncio
async def test_detect_problems(project_dir):
    llm = RefinementMockLLM()
    result = await detect(
        project_dir,
        "我觉得对所有紧致算子 T，T^n 的谱半径趋于 0",
        llm=llm,
    )
    assert result["detected"] is True
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["problem_type"] == "conjecture"


@pytest.mark.asyncio
async def test_create_draft(project_dir):
    llm = RefinementMockLLM()
    result = await create_draft(
        project_dir,
        "对所有紧致算子 T，谱半径趋于 0",
        problem_type="conjecture",
        llm=llm,
    )
    assert result["draft_id"].startswith("draft-")
    assert "title" in result
    # Check draft file was persisted
    draft_path = project_dir / ".mathassist" / "drafts" / f"{result['draft_id']}.json"
    assert draft_path.exists()


@pytest.mark.asyncio
async def test_full_refinement_loop(project_dir):
    """Test: draft -> check (fails) -> refine -> check (passes) -> finalize."""
    llm = RefinementMockLLM()

    # Step 1: Create draft
    draft_result = await create_draft(
        project_dir,
        "对所有紧致算子 T，谱半径趋于 0",
        problem_type="conjecture",
        llm=llm,
    )
    draft_id = draft_result["draft_id"]

    # Step 2: Refine with user response (this triggers quality check)
    refine_result = await refine(
        project_dir,
        draft_id,
        "r(T) 是谱半径，加上 r(T) < 1 的条件",
        llm=llm,
    )
    assert "check_results" in refine_result
    assert refine_result["draft_id"] == draft_id

    # Step 3: Finalize
    final_result = await finalize(project_dir, draft_id)
    assert "file_path" in final_result
    assert final_result["file_path"].endswith(".md")
    # Draft should be cleaned up
    draft_path = project_dir / ".mathassist" / "drafts" / f"{draft_id}.json"
    assert not draft_path.exists()


@pytest.mark.asyncio
async def test_finalize_nonexistent_draft(project_dir):
    result = await finalize(project_dir, "draft-nonexistent")
    assert "error" in result
