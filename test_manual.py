"""Manual test script — test full workflow with a real LLM.

Usage:
    export GOOGLE_API_KEY="your-key"
    uv run python test_manual.py
"""

import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


async def main():
    # Auto-detect API key and select backend
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
        print("Please set an API key env var (GOOGLE_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY)")
        return
    print(f"LLM backend: {backend}")

    from mathassistant.project import initialize_project
    from mathassistant.storage.discussion import append_message
    from mathassistant.storage.log import append_log, read_log
    from mathassistant.storage.index import update_index
    from mathassistant.refinement.detector import detect
    from mathassistant.refinement.drafter import create_draft
    from mathassistant.refinement.loop import refine, finalize
    from mathassistant.quality.checker import run_quality_checks
    from mathassistant.storage.frontmatter import Document
    from mathassistant.lint import run_lint

    # 1. Init project
    project = Path("/tmp/test-math-project")
    if project.exists():
        shutil.rmtree(project)
    print("\n=== 1. Initialize project ===")
    result = initialize_project(project, "Compact Operator Research")
    print(f"  Project created at: {result['project_dir']}")

    # 2. Record discussion
    print("\n=== 2. Record discussion ===")
    messages = [
        ("alice", "I think for a compact operator T on a Banach space X, if the spectral radius r(T) < 1, then ||T^n|| -> 0 as n -> infinity."),
        ("bob", "Isn't that true for general bounded operators? The spectral radius formula gives r(T) = lim ||T^n||^{1/n}."),
        ("alice", "Not necessarily. For bounded operators you need r(T) < 1 to get convergence, but compactness might give a stronger result — perhaps even exponential decay of ||T^n||."),
    ]
    for author, content in messages:
        path, count = append_message(project, author, content, datetime.now())
        append_log(project, "message", f"{author}: {content[:50]}")
        print(f"  [{author}]: {content[:70]}...")
    update_index(project)
    print(f"  Recorded {count} messages")

    # 3. Detect problems
    print("\n=== 3. Detect provable problems ===")
    detect_result = await detect(
        project,
        "For a compact operator T on a Banach space, if spectral radius r(T) < 1, then ||T^n|| -> 0",
        context_messages=[msg[1] for msg in messages],
    )
    print(f"  Detected: {detect_result['detected']}")
    if detect_result["candidates"]:
        for c in detect_result["candidates"]:
            print(f"  - [{c.get('problem_type', '?')}] {c.get('signal_text', '')[:70]}... (confidence: {c.get('confidence', '?')})")
    append_log(project, "detect", f"Detected {len(detect_result.get('candidates', []))} problem signal(s)")

    # 4. Draft problem
    print("\n=== 4. Generate problem draft ===")
    draft_result = await create_draft(
        project,
        "For a compact operator T on a Banach space X, if the spectral radius r(T) < 1, then ||T^n|| -> 0 as n -> infinity.",
        context_messages=[msg[1] for msg in messages],
        problem_type="conjecture",
    )
    draft_id = draft_result["draft_id"]
    print(f"  Draft ID: {draft_id}")
    print(f"  Title: {draft_result.get('title', '(none)')}")
    print(f"  Preview:\n{draft_result['body_preview'][:600]}")
    append_log(project, "draft", f"Created draft {draft_id}")

    # 5. Quality check
    print("\n=== 5. Quality check ===")
    draft_path = project / ".mathassist" / "drafts" / f"{draft_id}.json"
    draft_data = json.loads(draft_path.read_text())
    doc = Document(meta=draft_data["meta"], body=draft_data["body"])
    report = await run_quality_checks(doc)
    report_dict = report.to_dict()
    print(f"  Overall: {report_dict['overall']}")
    for name, check in report_dict["checks"].items():
        icon = "PASS" if check["severity"] == "pass" else "WARN" if check["severity"] == "warn" else "FAIL"
        print(f"  [{icon}] {name}: {check['message'][:70]}")
    if report_dict["top_issue"]:
        print(f"\n  Top issue: {report_dict['top_issue']['question']}")

    # 6. Refinement loop (simulate up to 3 rounds)
    max_rounds = 3
    current_draft_id = draft_id
    for round_num in range(1, max_rounds + 1):
        if report_dict["overall"] == "pass":
            print(f"\n=== 6. All checks passed after round {round_num - 1} ===")
            break

        print(f"\n=== 6.{round_num} Refinement round {round_num} ===")
        top = report_dict.get("top_issue")
        if not top or not top.get("question"):
            print("  No actionable question, skipping refinement")
            break

        print(f"  AI asks: {top['question'][:80]}")

        # Simulated user responses for each check type
        user_responses = {
            "definitions": "The spectral radius r(T) is defined as r(T) = sup{|lambda| : lambda in sigma(T)}, where sigma(T) is the spectrum of T. T is a bounded linear operator on X.",
            "assumptions_explicit": "Yes, X should be a complex Banach space. T is a compact bounded linear operator. We assume r(T) < 1 strictly.",
            "assumptions_consistent": "The assumptions are consistent — compactness implies boundedness, and spectral radius is well-defined for bounded operators on complex Banach spaces.",
            "goal_clarity": "The goal is: Prove that ||T^n|| -> 0 as n -> infinity, i.e., the operator norm of T^n converges to zero.",
            "type_strength": "This should be a theorem, not a conjecture — it is a well-known result in functional analysis.",
            "formalizability": "This is formalizable in Lean with Mathlib, which has Banach space theory and spectral theory.",
            "edge_cases": "For n=0, T^0 = I (identity), so ||T^0|| = 1, which is fine. The convergence starts from n=1.",
        }

        check_name = top.get("check_name", "")
        user_answer = user_responses.get(check_name, "Please proceed with the current formulation.")
        print(f"  User: {user_answer[:80]}...")

        refine_result = await refine(project, current_draft_id, user_answer)
        report_dict = refine_result.get("check_results", {})
        print(f"  After refinement: {report_dict.get('overall', '?')}")

        if refine_result.get("ready_to_finalize"):
            print("  All checks passed!")
            break
        elif refine_result.get("next_question"):
            print(f"  Next question: {refine_result['next_question'][:80]}")

        append_log(project, "refine", f"Round {round_num}: {check_name}")
        current_draft_id = refine_result["draft_id"]

    # 7. Finalize
    print("\n=== 7. Finalize ===")
    final = await finalize(project, current_draft_id)
    if final.get("error"):
        print(f"  Error: {final['error']}")
    else:
        print(f"  Written to: {final.get('file_path', '')}")
        print(f"  Git commit: {final.get('commit_hash', '')}")
        append_log(project, "finalize", f"Problem written to {final.get('file_path', '')}")

    # 8. Read the final problem file
    if final.get("file_path") and Path(final["file_path"]).exists():
        print("\n=== 8. Final problem file ===")
        content = Path(final["file_path"]).read_text()
        print(content[:1500])
        if len(content) > 1500:
            print(f"  ... ({len(content)} chars total)")

    # 9. Project lint
    print("\n=== 9. Project health check ===")
    lint_result = await run_lint(project)
    print(f"  Found {lint_result['issue_count']} issue(s)")
    for issue in lint_result["issues"][:5]:
        print(f"  - [{issue.get('severity', '?')}] {issue.get('description', '')[:70]}")
    if lint_result.get("next_steps"):
        print("  Suggested next steps:")
        for step in lint_result["next_steps"][:3]:
            print(f"    -> {step.get('direction', '')[:70]}")

    # 10. Project log
    print("\n=== 10. Project log ===")
    update_index(project)
    entries = read_log(project, last_n=10)
    for e in entries:
        print(f"  [{e['timestamp']}] {e['operation']} | {e['description'][:60]}")

    # 11. List generated files
    print("\n=== 11. Generated files ===")
    for f in sorted(project.rglob("*.md")):
        rel = f.relative_to(project)
        if not str(rel).startswith("."):
            size = f.stat().st_size
            print(f"  {rel} ({size} bytes)")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
