"""PLAN / BUILD / AUTO execution modes with bounded autonomy budgets.

- PLAN: inspect-only (read/search/retrieve/reason), no project writes.
- BUILD: execute approved plan steps with verification.
- AUTO: autonomous loop bounded by turn/token/time/tool/subagent budgets.

This module is backend-only; UI/CLI/TUI render its state, never duplicate it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.session.manager import SessionManager


@dataclass
class AutoBudget:
    max_turns: int = 8
    max_tool_calls: int = 40
    max_subagents: int = 5
    max_seconds: int = 600


MODE_DESCRIPTIONS = {
    "PLAN": "Inspect-only: read, search, reason, retrieve. No project file writes.",
    "BUILD": "Execute the approved plan step-by-step with verification.",
    "AUTO": "Bounded autonomous loop (turn/tool/time/subagent budgets enforced).",
}


def build_plan_from_goal(goal: str, files_hint: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Deterministic plan scaffold the agent/LLM refines; always includes acceptance criteria."""
    goal = goal.strip() or "Unspecified goal"
    steps = [
        {"step_id": "s1", "title": f"Inspect context relevant to: {goal[:80]}", "status": "pending", "files_likely": files_hint or []},
        {"step_id": "s2", "title": "Draft minimal change set", "status": "pending", "files_likely": files_hint or []},
        {"step_id": "s3", "title": "Implement + self-review diff", "status": "pending", "files_likely": files_hint or []},
        {"step_id": "s4", "title": "Run targeted tests and verify", "status": "pending", "files_likely": []},
    ]
    return steps


def check_auto_budget(usage: Dict[str, Any], budget: AutoBudget, elapsed_s: float) -> Optional[str]:
    if usage.get("turns", 0) >= budget.max_turns:
        return "turn budget exhausted"
    if usage.get("tool_calls", 0) >= budget.max_tool_calls:
        return "tool budget exhausted"
    if usage.get("subagents", 0) >= budget.max_subagents:
        return "subagent budget exhausted"
    if elapsed_s >= budget.max_seconds:
        return "time budget exhausted"
    return None


class ModeRunner:
    """Owns mode transitions + autonomous loop state for a session."""

    def __init__(self, sessions: SessionManager):
        self.sessions = sessions

    def set_mode(self, session_id: str, mode: str) -> Dict[str, Any]:
        mode = mode.upper()
        if mode not in ("PLAN", "BUILD", "AUTO"):
            return {"ok": False, "reason": f"unknown mode {mode}"}
        sess = self.sessions.update(session_id, mode=mode)
        if not sess:
            return {"ok": False, "reason": "unknown session"}
        self.sessions.append_message(session_id, "system", f"Mode switched to {mode}: {MODE_DESCRIPTIONS[mode]}")
        return {"ok": True, "mode": mode}

    def ensure_plan(self, session_id: str) -> List[Dict[str, Any]]:
        sess = self.sessions.get(session_id)
        if not sess:
            return []
        if not sess.plan:
            steps = build_plan_from_goal(sess.goal or sess.title)
            self.sessions.set_plan(session_id, steps)
            return steps
        return sess.plan
