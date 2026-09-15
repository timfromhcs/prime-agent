"""Prime daemon HTTP API (FastAPI + SSE).

One backend for UI/CLI/TUI. Streaming via SSE for agent/tool/subagent/
terminal progress events; polling fallback via /api/events?cursor=N.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from services.runtime.core import PrimeRuntime


from services.runtime.core import PrimeRuntime


class CreateSession(BaseModel):
    title: str = "Untitled session"
    project: str = ""
    cwd: str = "."
    goal: str = ""
    mode: str = "BUILD"


class Message(BaseModel):
    role: str
    content: str


class RunTask(BaseModel):
    prompt: str
    max_turns: int = 8
    max_tool_calls: int = 40
    max_seconds: int = 600


class SpawnAgent(BaseModel):
    task: str
    name: str = "child"
    role: str = "research"


class TodoIn(BaseModel):
    title: str
    status: str = "pending"
    evidence: str = ""


class TermRun(BaseModel):
    command: str
    timeout: int = 120


def create_app(runtime: Optional[PrimeRuntime] = None) -> FastAPI:
    rt = runtime or PrimeRuntime()
    app = FastAPI(title="Prime Agent Daemon", version="3.0.0")
    app.state.runtime = rt

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "service": "prime-daemon", "version": "3.0.0"}

    @app.get("/api/sessions")
    def list_sessions() -> Dict[str, Any]:
        return {"sessions": [s.__dict__ for s in rt.sessions.list()]}

    @app.post("/api/sessions")
    def create_session(body: CreateSession) -> Dict[str, Any]:
        s = rt.sessions.create(title=body.title, project=body.project,
                               cwd=body.cwd or ".", goal=body.goal, mode=body.mode)
        rt.emit("session.created", s.session_id, {"title": s.title})
        return {"session": s.__dict__}

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str) -> JSONResponse:
        s = rt.sessions.get(sid)
        if not s:
            return JSONResponse({"ok": False, "reason": "unknown session"}, status_code=404)
        return JSONResponse({"session": s.__dict__})

    @app.delete("/api/sessions/{sid}")
    def delete_session(sid: str) -> Dict[str, Any]:
        return {"ok": rt.sessions.delete(sid)}

    @app.post("/api/sessions/{sid}/archive")
    def archive_session(sid: str) -> Dict[str, Any]:
        return {"ok": rt.sessions.archive(sid)}

    @app.post("/api/sessions/{sid}/fork")
    def fork_session(sid: str) -> Dict[str, Any]:
        s = rt.sessions.fork(sid)
        if not s:
            return {"ok": False}
        rt.emit("session.created", s.session_id, {"forked_from": sid})
        return {"ok": True, "session": s.__dict__}

    @app.post("/api/sessions/{sid}/compact")
    def compact_session(sid: str) -> Dict[str, Any]:
        return {"ok": rt.sessions.compact(sid)}

    @app.get("/api/sessions/{sid}/export")
    def export_session(sid: str, fmt: str = "markdown") -> Dict[str, Any]:
        out = rt.sessions.export(sid, fmt=fmt)
        if out is None:
            return {"ok": False}
        return {"ok": True, "export": out}

    @app.post("/api/sessions/{sid}/mode")
    def set_mode(sid: str, body: Dict[str, str]) -> Dict[str, Any]:
        return rt.modes.set_mode(sid, body.get("mode", "BUILD"))

    @app.post("/api/sessions/{sid}/message")
    def post_message(sid: str, body: Message) -> Dict[str, Any]:
        return {"ok": rt.sessions.append_message(sid, body.role, body.content)}

    @app.post("/api/sessions/{sid}/run")
    async def run_task(sid: str, body: RunTask) -> Dict[str, Any]:
        from services.agent.modes import AutoBudget
        b = AutoBudget(max_turns=body.max_turns, max_tool_calls=body.max_tool_calls,
                       max_seconds=body.max_seconds)
        return await rt.run_task(sid, body.prompt, budget=b)

    @app.post("/api/sessions/{sid}/interrupt")
    def interrupt(sid: str) -> Dict[str, Any]:
        return rt.interrupt(sid)

    @app.post("/api/sessions/{sid}/spawn")
    def spawn(sid: str, body: SpawnAgent) -> Dict[str, Any]:
        return rt.spawn_subagent(sid, body.task, body.name, body.role)

    @app.get("/api/sessions/{sid}/context")
    def context(sid: str) -> Dict[str, Any]:
        return rt.context_info(sid)

    @app.get("/api/sessions/{sid}/git")
    def git_state(sid: str) -> Dict[str, Any]:
        return rt.git_state(sid)

    @app.post("/api/sessions/{sid}/todos")
    def add_todo(sid: str, body: TodoIn) -> Dict[str, Any]:
        tid = rt.sessions.upsert_todo(sid, body.title, body.status, body.evidence)
        return {"ok": tid is not None, "todo_id": tid}

    # -- terminals --
    @app.get("/api/terminals")
    def list_terms() -> Dict[str, Any]:
        return {"terminals": [t.__dict__ for t in rt.terminals.list()]}

    @app.post("/api/terminals")
    def create_term(body: Dict[str, str]) -> Dict[str, Any]:
        t = rt.terminals.create(name=body.get("name", "Terminal 1"), cwd=body.get("cwd", "."))
        return {"terminal": t.__dict__}

    @app.post("/api/terminals/{tid}/run")
    def term_run(tid: str, body: TermRun) -> Dict[str, Any]:
        return rt.terminals.run(tid, body.command, timeout=body.timeout)

    # -- rag / mcp / models / permissions --
    @app.post("/api/rag/search")
    def rag_search(body: Dict[str, Any]) -> Dict[str, Any]:
        pack = rt.rag.search(str(body.get("query", "")), top_k=int(body.get("top_k", 5)))
        return {"items": [i.__dict__ for i in pack.items]}

    @app.post("/api/rag/ingest")
    def rag_ingest(body: Dict[str, str]) -> Dict[str, Any]:
        path = body.get("path", "")
        import os as _os
        if _os.path.isdir(path):
            return {"files": rt.rag.ingest_directory(path)}
        return rt.rag.ingest_file(path)

    @app.get("/api/mcp/tools")
    def mcp_tools() -> Dict[str, Any]:
        from services.mcp.tools import MCPToolRegistry
        reg = MCPToolRegistry()
        return {"tools": sorted(reg.tools.keys())}

    @app.get("/api/models")
    def models() -> Dict[str, Any]:
        import json as _j
        from pathlib import Path as _P
        cfg = _j.loads(_P("config/models.json").read_text(encoding="utf-8"))
        out = {}
        for role, m in cfg.items():
            p = m.get("path", "")
            exists = _P(p).exists() if p else True
            out[role] = {**m, "present": exists,
                         "status": "installed" if exists else "missing"}
        return {"models": out}

    @app.post("/api/permissions/decide")
    def perm_decide(body: Dict[str, str]) -> Dict[str, Any]:
        return rt.permissions.decide(body.get("action", ""), body.get("target", ""),
                                     body.get("session_id", ""), body.get("agent", ""))

    @app.get("/api/events")
    def events(cursor: int = 0) -> Dict[str, Any]:
        return rt.events_since(cursor)

    @app.get("/api/events/stream")
    async def event_stream(cursor: int = 0):
        async def gen():
            seen = cursor
            for _ in range(600):  # ~10 min max per connection
                data = rt.events_since(seen)
                seen = data["cursor"]
                for ev in data["events"]:
                    yield f"data: {json.dumps(ev)}\n\n"
                await asyncio.sleep(1.0)
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()
