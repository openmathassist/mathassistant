"""手动测试脚本 — 用真实 LLM 测试完整工作流。

用法:
    export GOOGLE_API_KEY="你的key"
    uv run python test_manual.py
"""

import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


async def main():
    # 自动检测 API key 并选择后端
    if not os.environ.get("MATHASSIST_LLM_BACKEND"):
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            os.environ["MATHASSIST_LLM_BACKEND"] = "gemini"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["MATHASSIST_LLM_BACKEND"] = "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            os.environ["MATHASSIST_LLM_BACKEND"] = "openai"

    backend = os.environ.get("MATHASSIST_LLM_BACKEND", "gemini")
    api_key = (
        os.environ.get("MATHASSIST_LLM_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
        print("请设置 API key 环境变量（GOOGLE_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY）")
        return
    print(f"使用 LLM 后端: {backend}")

    from mathassistant.project import initialize_project
    from mathassistant.storage.discussion import append_message
    from mathassistant.storage.log import read_log
    from mathassistant.storage.index import update_index
    from mathassistant.refinement.detector import detect
    from mathassistant.refinement.drafter import create_draft
    from mathassistant.refinement.loop import refine, finalize
    from mathassistant.quality.checker import run_quality_checks
    from mathassistant.storage.frontmatter import Document
    from mathassistant.lint import run_lint

    # 1. 初始化项目
    project = Path("/tmp/test-math-project")
    if project.exists():
        shutil.rmtree(project)
    print("\n=== 1. 初始化项目 ===")
    result = initialize_project(project, "紧致算子研究")
    print(f"✓ 项目创建于: {result['project_dir']}")

    # 2. 模拟讨论
    print("\n=== 2. 记录讨论 ===")
    messages = [
        ("hoxide", "我觉得对 Banach 空间上的紧致算子 T，如果谱半径 r(T) < 1，那么 ||T^n|| → 0"),
        ("collaborator", "这个对一般有界算子也成立吧？谱半径公式给出 r(T) = lim ||T^n||^{1/n}"),
        ("hoxide", "不一定，有界算子需要的是 r(T) < 1，但紧致性可能给出更强的结论"),
    ]
    for author, content in messages:
        path, count = append_message(project, author, content, datetime.now())
        print(f"  [{author}]: {content[:50]}...")
    print(f"✓ 记录了 {count} 条消息")

    # 3. 检测问题
    print("\n=== 3. 检测待证问题 ===")
    detect_result = await detect(
        project,
        "对 Banach 空间上的紧致算子 T，如果谱半径 r(T) < 1，那么 ||T^n|| → 0",
        context_messages=[msg[1] for msg in messages],
    )
    print(f"  检测到问题: {detect_result['detected']}")
    if detect_result["candidates"]:
        for c in detect_result["candidates"]:
            print(f"  - [{c.get('problem_type', '?')}] {c.get('signal_text', '')[:60]}... (置信度: {c.get('confidence', '?')})")

    # 4. 生成问题草稿
    print("\n=== 4. 生成问题草稿 ===")
    draft_result = await create_draft(
        project,
        "对 Banach 空间上的紧致算子 T，如果谱半径 r(T) < 1，那么 ||T^n|| → 0",
        context_messages=[msg[1] for msg in messages],
        problem_type="conjecture",
    )
    draft_id = draft_result["draft_id"]
    print(f"  草稿 ID: {draft_id}")
    print(f"  标题: {draft_result.get('title', '')}")
    print(f"  预览:\n{draft_result['body_preview'][:500]}")

    # 5. 质量检查
    print("\n=== 5. 质量检查 ===")
    draft_path = project / ".mathassist" / "drafts" / f"{draft_id}.json"
    draft_data = json.loads(draft_path.read_text())
    doc = Document(meta=draft_data["meta"], body=draft_data["body"])
    report = await run_quality_checks(doc)
    report_dict = report.to_dict()
    print(f"  总体: {report_dict['overall']}")
    for name, check in report_dict["checks"].items():
        icon = "✓" if check["severity"] == "pass" else "⚠" if check["severity"] == "warn" else "✗"
        print(f"  {icon} {name}: {check['message'][:60]}")
    if report_dict["top_issue"]:
        print(f"\n  → 最关键问题: {report_dict['top_issue']['question']}")

    # 6. 精炼（模拟一轮用户回复）
    if report_dict["top_issue"] and report_dict["top_issue"].get("question"):
        print("\n=== 6. 精炼循环 ===")
        print(f"  AI 问: {report_dict['top_issue']['question']}")
        user_answer = "谱半径 r(T) 定义为 T 的谱 σ(T) 中模最大的元素的模，即 r(T) = sup{|λ| : λ ∈ σ(T)}。这里 T 是 Banach 空间 X 到自身的紧致线性算子。"
        print(f"  用户答: {user_answer[:60]}...")
        refine_result = await refine(project, draft_id, user_answer)
        print(f"  精炼后检查: {refine_result.get('check_results', {}).get('overall', '?')}")
        if refine_result.get("ready_to_finalize"):
            print("  ✓ 所有检查通过，可以定稿")
        elif refine_result.get("next_question"):
            print(f"  → 下一个问题: {refine_result['next_question']}")
        draft_id = refine_result["draft_id"]

    # 7. 定稿
    print("\n=== 7. 定稿 ===")
    final = await finalize(project, draft_id)
    print(f"  ✓ 写入: {final.get('file_path', '')}")
    print(f"  Git commit: {final.get('commit_hash', '')}")

    # 8. 项目 Lint
    print("\n=== 8. 项目健康检查 ===")
    lint_result = await run_lint(project)
    print(f"  发现 {lint_result['issue_count']} 个问题")
    for issue in lint_result["issues"][:3]:
        print(f"  - [{issue.get('severity', '?')}] {issue.get('description', '')[:60]}")
    if lint_result.get("next_steps"):
        print("  建议下一步:")
        for step in lint_result["next_steps"][:2]:
            print(f"  → {step.get('direction', '')[:60]}")

    # 9. 查看日志
    print("\n=== 9. 项目日志 ===")
    entries = read_log(project, last_n=5)
    for e in entries:
        print(f"  [{e['timestamp']}] {e['operation']} | {e['description'][:50]}")

    # 10. 查看最终文件
    print("\n=== 10. 生成的文件 ===")
    for f in sorted(project.rglob("*.md")):
        rel = f.relative_to(project)
        if not str(rel).startswith("."):
            print(f"  {rel}")

    print("\n✓ 测试完成!")


if __name__ == "__main__":
    asyncio.run(main())
