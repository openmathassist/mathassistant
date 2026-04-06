"""OpenClaw agent client for mathassistant.

Calls OpenClaw agents instead of direct LLM APIs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class OpenClawClient:
    """Client for calling OpenClaw agents via CLI."""
    
    def __init__(
        self, 
        project_dir: Optional[Path] = None, 
        timeout: int = 300,
        default_model: str = "gemini/gemini-2.5-pro",
        default_thinking: str = "xhigh",
    ):
        self.project_dir = project_dir
        self.timeout = timeout
        self._default_agent = os.environ.get("MATHASSIST_OPENCLAW_AGENT", "coder")
        self._default_model = default_model
        self._default_thinking = default_thinking
    
    def _run_openclaw(self, args: list[str], cwd: Optional[Path] = None, model: Optional[str] = None, thinking: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run openclaw CLI command.
        
        Args:
            args: Command arguments
            cwd: Working directory
            model: Model override (e.g., "gemini/gemini-2.5-pro")
            thinking: Thinking level (off|minimal|low|medium|high|xhigh)
        """
        cmd = ["openclaw"] + args
        
        # Build environment with overrides
        env = {**os.environ}
        if self.project_dir:
            env["MATHASSIST_PROJECT"] = str(self.project_dir)
        if model:
            env["OPENCLAW_AGENT_MODEL"] = model
        if thinking:
            env["OPENCLAW_AGENT_THINKING"] = thinking
            
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=cwd or self.project_dir,
            env=env
        )
    
    def call_agent(
        self, 
        agent_id: str, 
        message: str, 
        timeout: Optional[int] = None,
        local: bool = True,
        model: Optional[str] = None,
        thinking: Optional[str] = None,
    ) -> str:
        """Call an OpenClaw agent with a message.
        
        Args:
            agent_id: Agent ID (coder, helper, main, etc.)
            message: Message to send to the agent
            timeout: Override default timeout
            local: Run locally (True) or via Gateway (False)
            model: Model override (default: gemini/gemini-2.5-pro)
            thinking: Thinking level (default: xhigh for maximum)
            
        Returns:
            Agent's response text
        """
        # Use instance defaults if not provided
        if model is None:
            model = self._default_model
        if thinking is None:
            thinking = self._default_thinking
            
        args = ["agent", "--agent", agent_id, "--message", message]
        if local:
            args.append("--local")
        
        result = self._run_openclaw(args, cwd=self.project_dir, model=model, thinking=thinking)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"Agent {agent_id} failed with code {result.returncode}"
            raise RuntimeError(f"OpenClaw agent error: {error_msg}")
        
        return result.stdout.strip()
    
    def detect_problem_signals(
        self, 
        content: str, 
        context_messages: list[str] | None = None,
        model: Optional[str] = None,
        thinking: Optional[str] = None,
    ) -> dict:
        """Use coder agent to detect mathematical problem signals.
        
        This replaces the direct LLM call in refinement/detector.py
        """
        context_str = ""
        if context_messages:
            context_str = "\n\nRecent context:\n" + "\n".join(context_messages[-5:])
        
        prompt = f"""Analyze this mathematical discussion for problem signals.

Content to analyze:
{content}{context_str}

Look for:
1. Conjectures ("we conjecture that...", "猜想...")
2. Lemma/theorem proposals ("we need to prove...", "需要证明...")
3. Questions about truth value ("is it true that...", "是否成立...")
4. Proof requests ("can we show...", "能否证明...")

IMPORTANT: Respond with valid JSON only, no markdown formatting.

JSON format:
{{
    "detected": true/false,
    "candidates": [
        {{
            "signal_text": "exact text showing the signal",
            "problem_type": "conjecture|lemma|theorem|proposition",
            "confidence": 0.0-1.0
        }}
    ]
}}

If no signals detected, return {{"detected": false, "candidates": []}}."""
        
        try:
            response = self.call_agent("coder", prompt, model=model, thinking=thinking)
            # Try to extract JSON from response
            return self._extract_json(response)
        except Exception as e:
            # Fallback: return empty detection
            return {
                "detected": False,
                "candidates": [],
                "error": str(e)
            }
    
    def draft_problem(
        self, 
        source_text: str, 
        problem_type: str = "conjecture",
        model: Optional[str] = None,
        thinking: Optional[str] = None,
    ) -> dict:
        """Use multi-agent workflow to draft a problem.
        
        Phase 1: coder drafts framework
        Phase 2: helper finds references  
        Phase 3: main formats final output
        """
        # Step 1: coder drafts
        draft_prompt = f"""Draft a {problem_type} based on this mathematical statement:

{source_text}

Your task:
1. Formalize the statement clearly
2. Identify key definitions needed
3. List explicit assumptions
4. State the goal/conclusion

Respond with structured text (not JSON), ready to be formatted as a problem file."""
        
        draft = self.call_agent("coder", draft_prompt, model=model, thinking=thinking)
        
        # Step 2: helper looks for references (lightweight)
        ref_prompt = f"""Quick check: what mathematical areas or key terms appear in this problem?

Problem draft:
{draft[:500]}...

List any relevant mathematical concepts, theorems, or references that might be useful.
Keep it brief (bullet points)."""
        
        try:
            refs = self.call_agent("helper", ref_prompt, model=model, thinking=thinking)
        except Exception:
            refs = "(reference lookup skipped)"
        
        # Step 3: main formats final
        format_prompt = f"""Format this as a proper problem definition:

DRAFT:
{draft}

REFERENCES:
{refs}

Create a well-structured problem file with:
- Clear problem statement
- Necessary definitions
- Explicit assumptions
- Goal/conclusion
- Brief motivation/context

Format as markdown with YAML frontmatter."""
        
        final = self.call_agent("main", format_prompt, model=model, thinking=thinking)
        
        return {
            "draft_id": f"draft-{hash(source_text) % 10000:04d}",
            "title": self._extract_title(final),
            "body": final,
            "body_preview": final[:600] + "..." if len(final) > 600 else final
        }
    
    def _extract_json(self, text: str) -> dict:
        """Extract JSON from agent response."""
        # Try direct parsing first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON block
        import re
        # Look for ```json ... ``` or just {...}
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[\s\S]*\})'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        # Fallback: return empty
        return {"detected": False, "candidates": [], "raw": text[:200]}
    
    def _extract_title(self, text: str) -> str:
        """Extract title from problem draft."""
        import re
        # Look for # Title or first heading
        match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        # Fallback: first line
        return text.split('\n')[0][:60] if text else "Untitled Problem"


# Singleton instance
_openclaw_client: OpenClawClient | None = None


def get_openclaw_client(project_dir: Optional[Path] = None) -> OpenClawClient:
    """Get or create OpenClaw client singleton."""
    global _openclaw_client
    if _openclaw_client is None or (project_dir and _openclaw_client.project_dir != project_dir):
        _openclaw_client = OpenClawClient(project_dir=project_dir)
    return _openclaw_client
