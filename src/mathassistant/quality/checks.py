"""Individual quality check implementations.

Each check analyzes a problem Document and returns a CheckResult.
Checks use LLM for non-trivial semantic analysis.
"""

from __future__ import annotations

import re

from ..llm.base import LLMBackend
from ..storage.frontmatter import Document
from .models import CheckResult, Severity

MATH_SYSTEM_PROMPT = """\
You are a mathematical quality checker. Analyze the given problem statement
and answer precisely. Output ONLY the JSON requested, no other text."""


def _extract_math_symbols(text: str) -> set[str]:
    """Extract symbols from LaTeX $...$ and $$...$$ blocks."""
    inline = re.findall(r"\$([^$]+)\$", text)
    symbols = set()
    for expr in inline:
        # Extract single letter symbols (possibly with subscripts/superscripts)
        symbols.update(re.findall(r"[A-Za-z](?:_\{?[^}]*\}?)?", expr))
    return symbols


async def check_definitions(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 1: Symbol & definition completeness."""
    body = doc.body
    symbols = _extract_math_symbols(body)

    if not symbols:
        return CheckResult(
            check_name="definitions",
            severity=Severity.PASS,
            message="No mathematical symbols detected.",
        )

    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{body}\n\n"
        f"Detected symbols: {sorted(symbols)}\n\n"
        f"Are all mathematical objects/symbols properly defined in the text? "
        f"If any are undefined, list them. "
        f'Respond as JSON: {{"all_defined": true/false, "undefined": ["sym1", ...], "question": "..."}}'
    )

    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("all_defined", True):
            return CheckResult("definitions", Severity.PASS, "All symbols defined.")
        undefined = data.get("undefined", [])
        question = data.get("question", f"以下符号未定义: {', '.join(undefined)}，请补充定义。")
        return CheckResult("definitions", Severity.FAIL, f"Undefined symbols: {undefined}", question)
    except (json.JSONDecodeError, KeyError):
        return CheckResult("definitions", Severity.WARN, "Could not parse definition check result.",
                          "请检查问题中所有数学符号是否都有定义。")


async def check_assumptions_explicit(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 2: Are assumptions explicit (no implicit 'everyone knows')."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Are there any implicit assumptions that are not explicitly stated? "
        f"Consider: topological properties, algebraic structure, finiteness, "
        f"measurability, regularity conditions, etc. "
        f'Respond as JSON: {{"all_explicit": true/false, "implicit": ["..."], "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("all_explicit", True):
            return CheckResult("assumptions_explicit", Severity.PASS, "All assumptions explicit.")
        implicit = data.get("implicit", [])
        question = data.get("question", f"以下假设可能是隐含的: {', '.join(implicit)}，是否需要显式声明？")
        return CheckResult("assumptions_explicit", Severity.FAIL, f"Implicit assumptions: {implicit}", question)
    except Exception:
        return CheckResult("assumptions_explicit", Severity.WARN, "Could not parse check result.",
                          "请检查是否有隐含的假设条件未明确写出。")


async def check_assumptions_consistent(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 3: Consistency of assumptions."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Are the stated assumptions mutually consistent? Are there any contradictions or redundancies? "
        f'Respond as JSON: {{"consistent": true/false, "issues": ["..."], "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("consistent", True):
            return CheckResult("assumptions_consistent", Severity.PASS, "Assumptions are consistent.")
        issues = data.get("issues", [])
        question = data.get("question", f"假设存在以下问题: {'; '.join(issues)}")
        return CheckResult("assumptions_consistent", Severity.FAIL, f"Consistency issues: {issues}", question)
    except Exception:
        return CheckResult("assumptions_consistent", Severity.WARN, "Could not parse check result.",
                          "请检查假设条件之间是否存在矛盾或冗余。")


async def check_goal_clarity(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 4: Is the goal a concrete proposition."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Is the goal/conclusion a concrete, well-defined mathematical proposition "
        f"(that can be either true or false), or is it vague/directional? "
        f'Respond as JSON: {{"clear": true/false, "issue": "...", "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("clear", True):
            return CheckResult("goal_clarity", Severity.PASS, "Goal is clear.")
        question = data.get("question", "目标不够明确，请将其精确为一个可证伪的数学命题。")
        return CheckResult("goal_clarity", Severity.FAIL, data.get("issue", "Goal is unclear"), question)
    except Exception:
        return CheckResult("goal_clarity", Severity.WARN, "Could not parse check result.",
                          "请确认证明目标是一个明确的数学命题。")


async def check_type_strength(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 5: Is the claimed type consistent with strength."""
    problem_type = doc.meta.get("type", "conjecture")
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem (claimed type: {problem_type}):\n\n{doc.body}\n\n"
        f"Is the claimed type (lemma/conjecture/proposition/theorem) appropriate "
        f"for the strength and scope of the conclusion? "
        f'Respond as JSON: {{"appropriate": true/false, "suggestion": "...", "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("appropriate", True):
            return CheckResult("type_strength", Severity.PASS, "Type is appropriate.")
        question = data.get("question", data.get("suggestion", "命题类型可能不太合适，请确认。"))
        return CheckResult("type_strength", Severity.WARN, data.get("suggestion", "Type may be inappropriate"), question)
    except Exception:
        return CheckResult("type_strength", Severity.PASS, "Type check inconclusive, proceeding.")


async def check_formalizability(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 6: Can this be handled by an automated prover."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Assess whether this problem can be processed by an automated theorem prover "
        f"(like Lean with Mathlib). Consider: are the concepts formalizable? "
        f"Are there well-known libraries covering this area? "
        f'Respond as JSON: {{"formalizable": true/false, "difficulty": "easy|medium|hard", "notes": "...", "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        difficulty = data.get("difficulty", "medium")
        if data.get("formalizable", True) and difficulty != "hard":
            return CheckResult("formalizability", Severity.PASS, f"Formalizable (difficulty: {difficulty}).")
        notes = data.get("notes", "")
        question = data.get("question", f"形式化难度较高: {notes}")
        severity = Severity.WARN if data.get("formalizable", True) else Severity.WARN
        return CheckResult("formalizability", severity, notes, question)
    except Exception:
        return CheckResult("formalizability", Severity.PASS, "Formalizability check inconclusive.")


async def check_edge_cases(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 7: Boundary conditions and degenerate cases."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Are there boundary conditions, degenerate cases, or special cases "
        f"that are not addressed? E.g., n=0, empty set, zero operator, etc. "
        f'Respond as JSON: {{"covered": true/false, "missing": ["..."], "question": "..."}}'
    )
    try:
        import json
        data = json.loads(response.strip().strip("`").strip())
        if data.get("covered", True):
            return CheckResult("edge_cases", Severity.PASS, "Edge cases covered.")
        missing = data.get("missing", [])
        question = data.get("question", f"以下边界情况未处理: {', '.join(missing)}")
        return CheckResult("edge_cases", Severity.WARN, f"Missing edge cases: {missing}", question)
    except Exception:
        return CheckResult("edge_cases", Severity.PASS, "Edge case check inconclusive.")


ALL_CHECKS = [
    check_definitions,
    check_assumptions_explicit,
    check_assumptions_consistent,
    check_goal_clarity,
    check_type_strength,
    check_formalizability,
    check_edge_cases,
]
