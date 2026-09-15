"""Session-first manager for Prime Agent V3 workbench.

Each session owns: title, project, cwd, branch, goal, mode,
messages, tool activity, plan, todos, files_changed, subagents,
artifacts, memory refs, usage, context stats, status, timestamps.

Persisted as JSON under data/sessions/<id>.json + index.
Survives restart. No UI/CLI logic duplicated: both consume this.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TodoItem:
    todo_id: str
    title: str
    status: str = "pending"  # pending|running|blocked|completed|failed|verified
    evidence: Optional[str] = None
    updated_at: str = ""


@dataclass
class PlanStep:
    step_id: str
    title: str
    status: str = "pending"
    files_likely: List[str] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    title: str
    project: str
    cwd: str
    branch: str
    goal: str
    mode: str  # PLAN|BUILD|AUTO
    status: str  # active|paused|archived|completed|failed
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_activity: List[Dict[str, Any]] = field(default_factory=list)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    todos: List[Dict[str, Any]] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    subagents: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


def _git_branch(cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


class SessionManager:
    """CRUD + fork + compact + export for workbench sessions."""

    def __init__(self, sessions_dir: str = "data/sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.sessions_dir / "index.json"

    # -- persistence --
    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _load_index(self) -> Dict[str, Any]:
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_index(self, index: Dict[str, Any]) -> None:
        tmp = self.index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
        tmp.replace(self.index_file)

    def _write(self, sess: Session) -> None:
        sess.updated_at = _now()
        tmp = self._path(sess.session_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(sess), indent=2), encoding="utf-8")
        tmp.replace(self._path(sess.session_id))
        index = self._load_index()
        index[sess.session_id] = {
            "title": sess.title, "project": sess.project,
            "status": sess.status, "mode": sess.mode,
            "updated_at": sess.updated_at,
        }
        self._save_index(index)

    def _read(self, session_id: str) -> Session:
        data = json.loads(self._path(session_id).read_text(encoding="utf-8"))
        return Session(**data)

    # -- CRUD --
    def create(self, title: str, project: str = "", cwd: str = ".",
               goal: str = "", mode: str = "BUILD") -> Session:
        sid = f"sess_{uuid4().hex[:8]}"
        ts = _now()
        cwd_abs = str(Path(cwd).resolve()) if cwd else "."
        sess = Session(
            session_id=sid, title=title[:120] or "Untitled session",
            project=project or Path(cwd_abs).name,
            cwd=cwd_abs, branch=_git_branch(cwd_abs),
            goal=goal, mode=mode.upper() if mode.upper() in ("PLAN", "BUILD", "AUTO") else "BUILD",
            status="active",
            usage={"turns": 0, "tool_calls": 0, "tokens_est": 0},
            created_at=ts, updated_at=ts,
        )
        self._write(sess)
        return sess

    def get(self, session_id: str) -> Optional[Session]:
        try:
            return self._read(session_id)
        except Exception:
            return None

    def list(self, include_archived: bool = False) -> List[Session]:
        out: List[Session] = []
        for p in sorted(self.sessions_dir.glob("sess_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                s = Session(**json.loads(p.read_text(encoding="utf-8")))
                if not include_archived and s.status == "archived":
                    continue
                out.append(s)
            except Exception:
                continue
        return out

    def update(self, session_id: str, **fields) -> Optional[Session]:
        sess = self.get(session_id)
        if not sess:
            return None
        for k, v in fields.items():
            if hasattr(sess, k):
                setattr(sess, k, v)
        self._write(sess)
        return sess

    def archive(self, session_id: str) -> bool:
        return self.update(session_id, status="archived") is not None

    def delete(self, session_id: str) -> bool:
        try:
            self._path(session_id).unlink(missing_ok=True)
            index = self._load_index()
            index.pop(session_id, None)
            self._save_index(index)
            return True
        except Exception:
            return False

    def fork(self, session_id: str, title_suffix: str = " (fork)") -> Optional[Session]:
        src = self.get(session_id)
        if not src:
            return None
        clone = self.create(
            title=src.title + title_suffix, project=src.project,
            cwd=src.cwd, goal=src.goal, mode=src.mode,
        )
        clone.messages = list(src.messages)
        clone.plan = list(src.plan)
        clone.todos = list(src.todos)
        clone.tool_activity = list(src.tool_activity)
        self._write(clone)
        return clone

    # -- activity --
    def append_message(self, session_id: str, role: str, content: str,
                       meta: Optional[Dict[str, Any]] = None) -> bool:
        sess = self.get(session_id)
        if not sess:
            return False
        sess.messages.append({"role": role, "content": content,
                              "at": _now(), **(meta or {})})
        sess.usage["turns"] = sess.usage.get("turns", 0) + 1
        sess.usage["tokens_est"] = sess.usage.get("tokens_est", 0) + max(1, len(content) // 4)
        self._write(sess)
        return True

    def log_tool(self, session_id: str, tool: str, status: str,
                 detail: str = "") -> bool:
        sess = self.get(session_id)
        if not sess:
            return False
        sess.tool_activity.append({"tool": tool, "status": status,
                                   "detail": detail[:2000], "at": _now()})
        sess.usage["tool_calls"] = sess.usage.get("tool_calls", 0) + 1
        self._write(sess)
        return True

    def set_plan(self, session_id: str, steps: List[Dict[str, Any]]) -> bool:
        sess = self.get(session_id)
        if not sess:
            return False
        sess.plan = steps
        self._write(sess)
        return True

    def upsert_todo(self, session_id: str, title: str,
                    status: str = "pending", evidence: str = "") -> Optional[str]:
        sess = self.get(session_id)
        if not sess:
            return None
        tid = f"todo_{uuid4().hex[:6]}"
        sess.todos.append({"todo_id": tid, "title": title, "status": status,
                           "evidence": evidence, "updated_at": _now()})
        self._write(sess)
        return tid

    def set_todo_status(self, session_id: str, todo_id: str,
                        status: str, evidence: str = "") -> bool:
        sess = self.get(session_id)
        if not sess:
            return False
        valid = {"pending", "running", "blocked", "completed", "failed", "verified"}
        if status not in valid:
            return False
        # completed requires evidence (no premature completion)
        if status in ("completed", "verified") and not evidence:
            return False
        for t in sess.todos:
            if t.get("todo_id") == todo_id:
                t["status"] = status
                t["evidence"] = evidence
                t["updated_at"] = _now()
                self._write(sess)
                return True
        return False

    def record_files_changed(self, session_id: str, files: List[str]) -> bool:
        sess = self.get(session_id)
        if not sess:
            return False
        seen = set(sess.files_changed)
        for f in files:
            if f not in seen:
                sess.files_changed.append(f)
                seen.add(f)
        self._write(sess)
        return True

    def compact(self, session_id: str, keep_recent: int = 20) -> bool:
        """Safe compaction: keep goal/plan/todos, trim old messages/tool logs."""
        sess = self.get(session_id)
        if not sess:
            return False
        if len(sess.messages) > keep_recent:
            kept = sess.messages[-keep_recent:]
            summary = {"role": "system",
                       "content": f"[compacted {len(sess.messages) - keep_recent} older messages; goal preserved: {sess.goal[:200]}]",
                       "at": _now()}
            sess.messages = [summary] + kept
        if len(sess.tool_activity) > 100:
            sess.tool_activity = sess.tool_activity[-100:]
        self._write(sess)
        return True

    def export(self, session_id: str, fmt: str = "markdown") -> Optional[str]:
        sess = self.get(session_id)
        if not sess:
            return None
        if fmt == "json":
            return json.dumps(asdict(sess), indent=2)
        lines = [f"# {sess.title}", f"Project: {sess.project} | Branch: {sess.branch} | Mode: {sess.mode}",
                 f"Goal: {sess.goal}", f"Status: {sess.status}", "", "## Plan"]
        for i, s in enumerate(sess.plan, 1):
            lines.append(f"{i}. [{s.get('status', 'pending')}] {s.get('title', '')}")
        lines.append("\n## Todos")
        for t in sess.todos:
            lines.append(f"- [{t.get('status')}] {t.get('title')}" + (f" — {t.get('evidence')}" if t.get('evidence') else ""))
        lines.append("\n## Transcript")
        for m in sess.messages:
            lines.append(f"**{m.get('role')}**: {m.get('content')[:2000]}")
        lines.append("\n## Files changed")
        for f in sess.files_changed:
            lines.append(f"- {f}")
        return "\n".join(lines)
