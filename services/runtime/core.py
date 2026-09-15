"""Unified Prime runtime core.

Single ownership point for task/goal/plan/execution/tool/subagent/memory
state. The FastAPI daemon, the Rich TUI, and the CLI all call PrimeRuntime —
never forked business logic.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from services.agent.memory import AgentMemorySystem
from services.agent.modes import AutoBudget, ModeRunner, check_auto_budget
from services.agent.root_agent import PrimeAgent
from services.diff.review import changed_files, file_diff, full_diff, git_status, revert_file
from services.permissions.engine import PermissionEngine
from services.rag.index import HybridRAGIndex
from services.session.manager import SessionManager
from services.subagents.manager import SubagentManager
from services.terminal.sessions import TerminalManager


class PrimeRuntime:
    def __init__(self, workspace_root: str = "E:/HCS Chat"):
        self.workspace_root = workspace_root
        self.sessions = SessionManager()
        self.modes = ModeRunner(self.sessions)
        self.permissions = PermissionEngine()
        self.terminals = TerminalManager()
        self.memory = AgentMemorySystem()
        self.rag = HybridRAGIndex()
        self.subagents = SubagentManager()
        self._agent: Optional[PrimeAgent] = None
        self._events: List[Dict[str, Any]] = []
        self._cancel: Dict[str, bool] = {}

    # -- events (normalized event model) --
    def emit(self, etype: str, session_id: str = "", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ev = {"type": etype, "session_id": session_id,
              "at": time.time(), "payload": payload or {}}
        self._events.append(ev)
        if len(self._events) > 2000:
            self._events = self._events[-2000:]
        return ev

    def events_since(self, cursor: int = 0) -> Dict[str, Any]:
        return {"cursor": len(self._events), "events": self._events[cursor:]}

    # -- lazy heavy agent --
    def agent(self) -> PrimeAgent:
        if self._agent is None:
            self._agent = PrimeAgent(workspace_root=self.workspace_root)
        return self._agent

    def interrupt(self, session_id: str) -> Dict[str, Any]:
        self._cancel[session_id] = True
        self.emit("task.interrupted", session_id, {})
        return {"ok": True}

    # -- chat / run (single core path for UI + CLI + TUI) --
    async def run_task(self, session_id: str, prompt: str,
                       budget: Optional[AutoBudget] = None) -> Dict[str, Any]:
        sess = self.sessions.get(session_id)
        if not sess:
            return {"ok": False, "reason": "unknown session"}
        budget = budget or AutoBudget()
        t0 = time.time()
        self._cancel.pop(session_id, None)
        self.sessions.append_message(session_id, "user", prompt)
        self.modes.ensure_plan(session_id)
        self.emit("message.started", session_id, {"prompt": prompt[:500]})

        mode = (sess.mode or "BUILD").upper()
        if mode == "PLAN":
            # inspect-only: RAG context + no writes
            pack = self.rag.search(prompt, top_k=3)
            cites = [f"[{i.citation}] {i.content[:300]}" for i in pack.items]
            resp = ("PLAN (read-only) — no files modified.\n\nEvidence:\n" +
                    ("\n".join(f"- {c}" for c in cites) if cites else "- no indexed evidence yet"))
            self.sessions.append_message(session_id, "assistant", resp)
            self.emit("message.completed", session_id, {"mode": "PLAN"})
            return {"ok": True, "mode": "PLAN", "response": resp}

        # BUILD / AUTO: delegate one bounded agent turn through the real RLM loop
        agent = self.agent()
        stop = check_auto_budget(
            {"turns": sess.usage.get("turns", 0), "tool_calls": sess.usage.get("tool_calls", 0),
             "subagents": len(sess.subagents)}, budget, 0)
        if stop:
            self.sessions.append_message(session_id, "system", f"AUTO halted: {stop}.")
            return {"ok": False, "reason": stop}
        max_steps = 5 if mode == "BUILD" else min(budget.max_turns, 8)
        try:
            self.emit("task.started", session_id, {"mode": mode})
            # permission gate for shell-affecting tasks is advisory here; kernel tools enforce per-call
            turn = await agent.execute_task(prompt, session_id=f"rlm-{session_id}", max_steps=max_steps)
            if self._cancel.get(session_id):
                self.sessions.append_message(session_id, "system", "Interrupted by user; state persisted.")
                self.emit("task.interrupted", session_id, {})
                return {"ok": False, "reason": "interrupted", "response": turn.response}
            self.sessions.append_message(session_id, "assistant", turn.response,
                                         {"verification": turn.verification})
            for a in turn.artifacts_created:
                s = self.sessions.get(session_id)
                if s and a not in s.artifacts:
                    self.sessions.update(session_id, artifacts=s.artifacts + [a])
            self.sessions.log_tool(session_id, "rlm.execute_task", "completed",
                                   f"{len(turn.actions_taken)} actions")
            # refresh files changed from git
            try:
                files = [f["path"] for f in changed_files(sess.cwd)]
                self.sessions.record_files_changed(session_id, files)
            except Exception:
                pass
            self.emit("task.completed", session_id, {"verification": turn.verification})
            return {"ok": True, "mode": mode, "response": turn.response,
                    "actions": turn.actions_taken, "artifacts": turn.artifacts_created,
                    "verification": turn.verification,
                    "elapsed_s": round(time.time() - t0, 2)}
        except Exception as e:  # structured error UX, never raw-only
            self.sessions.append_message(session_id, "system",
                                         f"WHAT FAILED: agent turn. WHY: {e}. STATE: session persisted. RETRY: /retry or interrupt with stop.")
            self.emit("task.failed", session_id, {"error": str(e)[:500]})
            return {"ok": False, "reason": str(e)[:500]}

    # -- subagents (real delegation) --
    def spawn_subagent(self, session_id: str, task: str, name: str, role: str = "research") -> Dict[str, Any]:
        handle = self.subagents.spawn(prompt=task, name=name, role=role, parent_id=session_id)
        sess = self.sessions.get(session_id)
        if sess:
            self.sessions.update(session_id, subagents=sess.subagents + [handle.subagent_id])
        self.emit("agent.spawned", session_id, {"subagent_id": handle.subagent_id, "name": name, "role": role})
        return {"ok": True, "subagent_id": handle.subagent_id, "name": handle.name}

    # -- git/diff passthrough --
    def git_state(self, session_id: str) -> Dict[str, Any]:
        sess = self.sessions.get(session_id)
        cwd = sess.cwd if sess else self.workspace_root
        return {"status": git_status(cwd), "changed": changed_files(cwd), "diff": full_diff(cwd)[:20000]}

    # -- context panel (real metrics only) --
    def context_info(self, session_id: str) -> Dict[str, Any]:
        sess = self.sessions.get(session_id)
        models = {}
        try:
            import json as _j
            models = _j.loads(Path("config/models.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        return {
            "session": session_id,
            "mode": sess.mode if sess else "?",
            "messages": len(sess.messages) if sess else 0,
            "tokens_est": (sess.usage.get("tokens_est", 0) if sess else 0),
            "tool_calls": (sess.usage.get("tool_calls", 0) if sess else 0),
            "todos": sess.todos if sess else [],
            "plan_steps": len(sess.plan) if sess else 0,
            "subagents": sess.subagents if sess else [],
            "models_configured": sorted(models.keys()),
        }

    def shutdown(self) -> None:
        try:
            if self._agent is not None:
                self._agent.shutdown()
        except Exception:
            pass
