"""Kernel Manager for Prime RLM.

Coordinates persistent REPL sessions, lifecycle hooks, and bridge dispatch.
"""

from __future__ import annotations
import asyncio
import os
from typing import Any, Callable, Dict, Optional
from services.rlm.repl import ReplSession
from services.rlm.winjob import WindowsJobGroup


class KernelManager:
    """Manages active RLM kernels and session lifecycles."""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = workspace_root
        self.sessions: Dict[str, ReplSession] = {}
        self.job_group = WindowsJobGroup("PrimeKernelJob")
        self._host_dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None

    def set_host_dispatcher(self, dispatcher: Callable[[str, Dict[str, Any]], Any]):
        self._host_dispatcher = dispatcher
        for session_id, session in self.sessions.items():
            session.set_host_handler(self._create_handler(session_id))

    def _create_handler(self, session_id: str):
        async def _handler(req: Dict[str, Any]) -> Any:
            return await self._dispatch_host(session_id, req)
        return _handler

    async def _dispatch_host(self, session_id: str, request: Dict[str, Any]) -> Any:
        if self._host_dispatcher:
            res = self._host_dispatcher(session_id, request)
            if asyncio.iscoroutine(res):
                return await res
            return res
        return {"error": "Host dispatcher not configured"}

    def get_or_create_session(self, session_id: str) -> ReplSession:
        if session_id not in self.sessions:
            session = ReplSession(
                session_id=session_id,
                host_handler=self._create_handler(session_id)
            )
            self.sessions[session_id] = session
        return self.sessions[session_id]

    async def execute(self, session_id: str, code: str) -> Dict[str, Any]:
        session = self.get_or_create_session(session_id)
        return await session.execute(code)

    def snapshot_session(self, session_id: str, path: str) -> Dict[str, Any]:
        session = self.get_or_create_session(session_id)
        return session.snapshot(path)

    def restore_session(self, session_id: str, path: str) -> Dict[str, Any]:
        session = self.get_or_create_session(session_id)
        return session.restore(path)

    def shutdown(self):
        self.sessions.clear()
        self.job_group.close()
