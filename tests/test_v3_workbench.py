"""V3 workbench acceptance: sessions, permissions, modes, API, terminals, TUI client.

Real behavior only — no mocks. Uses temp dirs for session/terminal stores.
"""

import asyncio

from fastapi.testclient import TestClient

from services.agent.modes import AutoBudget, ModeRunner, build_plan_from_goal, check_auto_budget
from services.api.server import create_app
from services.permissions.engine import PermissionEngine
from services.runtime.core import PrimeRuntime
from services.session.manager import SessionManager
from services.terminal.sessions import TerminalManager


def test_session_lifecycle(tmp_path):
    sm = SessionManager(sessions_dir=str(tmp_path / "sess"))
    s = sm.create(title="t", cwd=".", goal="g", mode="PLAN")
    assert s.session_id.startswith("sess_")
    assert sm.get(s.session_id).title == "t"
    sm.append_message(s.session_id, "user", "hello")
    sm.log_tool(s.session_id, "shell", "completed", "ls")
    sm.set_plan(s.session_id, build_plan_from_goal("g"))
    tid = sm.upsert_todo(s.session_id, "do thing")
    assert sm.set_todo_status(s.session_id, tid, "completed", evidence="tests passed") is True
    # completed without evidence must be rejected (no premature completion)
    tid2 = sm.upsert_todo(s.session_id, "other")
    assert sm.set_todo_status(s.session_id, tid2, "completed", evidence="") is False
    f = sm.fork(s.session_id)
    assert f.session_id != s.session_id and len(f.messages) == len(sm.get(s.session_id).messages)
    assert sm.compact(s.session_id) is True
    assert "Transcript" in (sm.export(s.session_id) or "")
    # persistence across instances
    sm2 = SessionManager(sessions_dir=str(tmp_path / "sess"))
    assert sm2.get(s.session_id) is not None


def test_permissions_sensitive_and_deny():
    eng = PermissionEngine(policy_file=str(__import__("pathlib").Path("config/permissions.json")))
    r = eng.decide("read_file", ".env")
    assert r["decision"] in ("ask", "deny")
    r2 = eng.decide("shell_exec", "rm -rf /*")
    assert r2["decision"] == "deny"
    r3 = eng.decide("read_file", "README.md")
    assert r3["decision"] == "allow"


def test_modes_and_budget():
    over = check_auto_budget({"agent_turns": 99}, AutoBudget(max_turns=8), 0)
    assert over is not None and "turn budget exhausted" in over
    assert check_auto_budget({"agent_turns": 0}, AutoBudget(), 99999) == "time budget exhausted"
    assert check_auto_budget({"agent_turns": 0, "tool_calls": 0, "subagents": 0}, AutoBudget(), 1) is None
    # messages alone must never exhaust the turn budget (regression: bricked sessions)
    assert check_auto_budget({"agent_turns": 0, "messages": 1300}, AutoBudget(), 1) is None


def test_terminal_real_exec(tmp_path):
    tm = TerminalManager(store_dir=str(tmp_path / "terms"))
    t = tm.create(name="T1", cwd=".")
    res = tm.run(t.term_id, "echo prime-v3-ok")
    assert res["ok"] is True and "prime-v3-ok" in (res.get("stdout") or "")


def test_api_sessions_and_events():
    rt = PrimeRuntime()
    app = create_app(rt)
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"] is True
    s = c.post("/api/sessions", json={"title": "api-t", "cwd": ".", "mode": "PLAN"}).json()["session"]
    sid = s["session_id"]
    assert c.post(f"/api/sessions/{sid}/message", json={"role": "user", "content": "hi"}).json()["ok"] is True
    r = c.post(f"/api/sessions/{sid}/run", json={"prompt": "summarize plan mode"}).json()
    assert r["ok"] is True and r["mode"] == "PLAN"
    ev = c.get("/api/events", params={"cursor": 0}).json()
    assert ev["cursor"] > 0 and any(e["type"] == "message.completed" for e in ev["events"])
    ctx = c.get(f"/api/sessions/{sid}/context").json()
    assert ctx["session"] == sid
    rt.shutdown()


def test_runtime_plan_is_readonly():
    rt = PrimeRuntime()
    s = rt.sessions.create(title="planonly", cwd=".", goal="inspect", mode="PLAN")
    res = asyncio.run(rt.run_task(s.session_id, "what is this repo?"))
    assert res["ok"] is True and "PLAN" in res["response"]
    rt.shutdown()
