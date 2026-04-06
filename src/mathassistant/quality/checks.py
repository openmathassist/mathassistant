"""Individual quality check implementations.

Each check analyzes a problem Document and returns a CheckResult.
Checks use LLM for non-trivial semantic analysis.
"""

from __future__ import annotations

import json
import re

from ..llm.base import LLMBackend
from ..storage.frontmatter import Document
from .models import CheckResult, Severity

MATH_SYSTEM_PROMPT = """\
You are a mathematical quality checker. Analyze the given problem statement
and answer precisely. Output ONLY the JSON requested, no other text."""


def _extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from LLM response text.

    Handles: code fences, surrounding text, multiple lines.
    """
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try stripping markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue
    # Try finding a JSON object in the text with regex
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


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

    data = _extract_json(response)
    if data is None:
        return CheckResult("definitions", Severity.WARN, "Could not parse definition check result.",
                          "Please check that all mathematical symbols in the problem are defined.")
    if data.get("all_defined", True):
        return CheckResult("definitions", Severity.PASS, "All symbols defined.")
    undefined = data.get("undefined", [])
    question = data.get("question", f"The following symbols are undefined: {', '.join(str(s) for s in undefined)}. Please provide definitions.")
    return CheckResult("definitions", Severity.FAIL, f"Undefined symbols: {undefined}", question)


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
    data = _extract_json(response)
    if data is None:
        return CheckResult("assumptions_explicit", Severity.WARN, "Could not parse check result.",
                          "Please check whether there are implicit assumptions not explicitly stated.")
    if data.get("all_explicit", True):
        return CheckResult("assumptions_explicit", Severity.PASS, "All assumptions explicit.")
    implicit = data.get("implicit", [])
    question = data.get("question", f"The following assumptions may be implicit: {', '.join(str(s) for s in implicit)}. Should they be stated explicitly?")
    return CheckResult("assumptions_explicit", Severity.FAIL, f"Implicit assumptions: {implicit}", question)


async def check_assumptions_consistent(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 3: Consistency of assumptions."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Are the stated assumptions mutually consistent? Are there any contradictions or redundancies? "
        f'Respond as JSON: {{"consistent": true/false, "issues": ["..."], "question": "..."}}'
    )
    data = _extract_json(response)
    if data is None:
        return CheckResult("assumptions_consistent", Severity.WARN, "Could not parse check result.",
                          "Please check whether the assumptions are contradictory or redundant.")
    if data.get("consistent", True):
        return CheckResult("assumptions_consistent", Severity.PASS, "Assumptions are consistent.")
    issues = data.get("issues", [])
    question = data.get("question", f"The assumptions have the following issues: {'; '.join(str(s) for s in issues)}")
    return CheckResult("assumptions_consistent", Severity.FAIL, f"Consistency issues: {issues}", question)


async def check_goal_clarity(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 4: Is the goal a concrete proposition."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Is the goal/conclusion a concrete, well-defined mathematical proposition "
        f"(that can be either true or false), or is it vague/directional? "
        f'Respond as JSON: {{"clear": true/false, "issue": "...", "question": "..."}}'
    )
    data = _extract_json(response)
    if data is None:
        return CheckResult("goal_clarity", Severity.WARN, "Could not parse check result.",
                          "Please confirm that the proof goal is a precise mathematical proposition.")
    if data.get("clear", True):
        return CheckResult("goal_clarity", Severity.PASS, "Goal is clear.")
    question = data.get("question", "The goal is not clear enough. Please refine it into a precise, falsifiable mathematical proposition.")
    return CheckResult("goal_clarity", Severity.FAIL, data.get("issue", "Goal is unclear"), question)


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
    data = _extract_json(response)
    if data is None:
        return CheckResult("type_strength", Severity.PASS, "Type check inconclusive, proceeding.")
    if data.get("appropriate", True):
        return CheckResult("type_strength", Severity.PASS, "Type is appropriate.")
    question = data.get("question", data.get("suggestion", "The proposition type may not be appropriate. Please confirm."))
    return CheckResult("type_strength", Severity.WARN, data.get("suggestion", "Type may be inappropriate"), question)


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
    data = _extract_json(response)
    if data is None:
        return CheckResult("formalizability", Severity.PASS, "Formalizability check inconclusive.")
    difficulty = data.get("difficulty", "medium")
    if data.get("formalizable", True) and difficulty != "hard":
        return CheckResult("formalizability", Severity.PASS, f"Formalizable (difficulty: {difficulty}).")
    notes = data.get("notes", "")
    question = data.get("question", f"Formalization difficulty is high: {notes}")
    return CheckResult("formalizability", Severity.WARN, notes, question)


async def check_edge_cases(doc: Document, llm: LLMBackend) -> CheckResult:
    """Check 7: Boundary conditions and degenerate cases."""
    response = await llm.complete(
        MATH_SYSTEM_PROMPT,
        f"Given this mathematical problem:\n\n{doc.body}\n\n"
        f"Are there boundary conditions, degenerate cases, or special cases "
        f"that are not addressed? E.g., n=0, empty set, zero operator, etc. "
        f'Respond as JSON: {{"covered": true/false, "missing": ["..."], "question": "..."}}'
    )
    data = _extract_json(response)
    if data is None:
        return CheckResult("edge_cases", Severity.PASS, "Edge case check inconclusive.")
    if data.get("covered", True):
        return CheckResult("edge_cases", Severity.PASS, "Edge cases covered.")
    missing = data.get("missing", [])
    question = data.get("question", f"The following edge cases are not addressed: {', '.join(str(s) for s in missing)}")
    return CheckResult("edge_cases", Severity.WARN, f"Missing edge cases: {missing}", question)


ALL_CHECKS = [
    check_definitions,
    check_assumptions_explicit,
    check_assumptions_consistent,
    check_goal_clarity,
    check_type_strength,
    check_formalizability,
    check_edge_cases,
]
