"""Prime HTTP client used by TUI/CLI when a daemon is running.

Falls back to in-process PrimeRuntime when no daemon URL is configured,
so UI and CLI always share one core path.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class PrimeClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 600.0):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self._local = None
        if not self.base_url:
            from services.runtime.core import PrimeRuntime
            self._local = PrimeRuntime()

    @property
    def remote(self) -> bool:
        return bool(self.base_url)

    # -- sessions --
    def list_sessions(self) -> Dict[str, Any]:
        if self._local:
            return {"sessions": [s.__dict__ for s in self._local.sessions.list()]}
        return httpx.get(f"{self.base_url}/api/sessions", timeout=15).json()

    def create_session(self, title: str, cwd: str = ".", goal: str = "",
                       mode: str = "BUILD", project: str = "") -> Dict[str, Any]:
        if self._local:
            s = self._local.sessions.create(title=title, project=project, cwd=cwd, goal=goal, mode=mode)
            return {"session": s.__dict__}
        r = httpx.post(f"{self.base_url}/api/sessions",
                       json={"title": title, "cwd": cwd, "goal": goal, "mode": mode, "project": project},
                       timeout=15)
        return r.json()

    def get_session(self, sid: str) -> Dict[str, Any]:
        if self._local:
            s = self._local.get(sid)
            return {"session": s.__dict__ if s else None}
        return httpx.get(f"{self.base_url}/api/sessions/{sid}", timeout=15).json()

    def run_task(self, sid: str, prompt: str) -> Dict[str, Any]:
        if self._local:
            import asyncio as _a
            return _a.run(self._local.run_task(sid, prompt))
        r = httpx.post(f"{self.base_url}/api/sessions/{sid}/run",
                       json={"prompt": prompt}, timeout=self.timeout)
        return r.json()

    def set_mode(self, sid: str, mode: str) -> Dict[str, Any]:
        if self._local:
            return self._local.modes.set_mode(sid, mode)
        return httpx.post(f"{self.base_url}/api/sessions/{sid}/mode",
                          json={"mode": mode}, timeout=15).json()

    def interrupt(self, sid: str) -> Dict[str, Any]:
        if self._local:
            return self._local.interrupt(sid)
        return httpx.post(f"{self.base_url}/api/sessions/{sid}/interrupt", timeout=15).json()

    def context(self, sid: str) -> Dict[str, Any]:
        if self._local:
            return self._local.context_info(sid)
        return httpx.get(f"{self.base_url}/api/sessions/{sid}/context", timeout=15).json()

    def git_state(self, sid: str) -> Dict[str, Any]:
        if self._local:
            return self._local.git_state(sid)
        return httpx.get(f"{self.base_url}/api/sessions/{sid}/git", timeout=30).json()
