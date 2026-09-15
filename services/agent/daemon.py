"""Background Daemon Architecture for Prime Agent.

Supports detached sessions, attach/resume, heartbeat loops,
and background execution of persistent goals.
"""

from __future__ import annotations
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.agent.memory import AgentMemorySystem
from services.agent.scheduler import AgentScheduler


@dataclass
class SessionState:
    session_id: str
    status: str  # "RUNNING" | "DETACHED" | "STOPPED"
    goal_id: Optional[str]
    created_at: str
    last_heartbeat: str
    turn_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PrimeDaemon:
    """Manages background sessions, persistent heartbeats, and daemon state."""

    def __init__(self, state_dir: str = "state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.state_dir / "daemon_sessions.json"
        self.sessions: Dict[str, SessionState] = {}
        self.scheduler = AgentScheduler()
        self.memory = AgentMemorySystem()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._load()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self):
        if self.session_file.exists():
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.sessions = {k: SessionState(**v) for k, v in data.items()}
            except Exception as e:
                print(f"[Daemon] Warning loading sessions: {e}")

    def save(self):
        data = {k: asdict(v) for k, v in self.sessions.items()}
        temp_file = self.session_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.session_file)

    def create_session(self, goal_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> SessionState:
        session_id = f"sess_{uuid4().hex[:8]}"
        ts = self._now()
        sess = SessionState(
            session_id=session_id,
            status="RUNNING",
            goal_id=goal_id,
            created_at=ts,
            last_heartbeat=ts,
            metadata=metadata or {}
        )
        self.sessions[session_id] = sess
        self.save()
        return sess

    def detach_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].status = "DETACHED"
            self.save()

    def resume_session(self, session_id: str) -> Optional[SessionState]:
        if session_id in self.sessions:
            self.sessions[session_id].status = "RUNNING"
            self.sessions[session_id].last_heartbeat = self._now()
            self.save()
            return self.sessions[session_id]
        return None

    def stop_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id].status = "STOPPED"
            self.save()

    async def start(self, heartbeat_interval: float = 15.0):
        self._running = True
        await self.scheduler.start()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(heartbeat_interval))

    async def stop(self):
        self._running = False
        self.scheduler.stop()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        for sess in self.sessions.values():
            if sess.status == "RUNNING":
                sess.status = "DETACHED"
        self.save()

    async def _heartbeat_loop(self, interval: float):
        heartbeat_log = self.state_dir / "heartbeat.log"
        while self._running:
            now = self._now()
            # 1. Update session heartbeats
            for sid, sess in list(self.sessions.items()):
                if sess.status in ["RUNNING", "DETACHED"]:
                    sess.last_heartbeat = now
                    sess.turn_count += 1
            self.save()

            # 2. Inspect active goals
            active_goals = [g for g in self.memory.goals.values() if g.status in ["PENDING", "IN_PROGRESS"]]

            # 3. Append state-aware heartbeat telemetry
            with open(heartbeat_log, "a", encoding="utf-8") as f:
                f.write(f"[{now}] HEARTBEAT: active_sessions={len(self.sessions)}, active_goals={len(active_goals)}\n")

            # 4. Compaction check for episodic memory if large
            if len(self.memory.episodes) > 100:
                self.memory.compact_memory(keep_recent=50)

            await asyncio.sleep(interval)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "total_sessions": len(self.sessions),
            "active_sessions": [s.session_id for s in self.sessions.values() if s.status in ["RUNNING", "DETACHED"]],
            "scheduled_tasks": len(self.scheduler.tasks)
        }
