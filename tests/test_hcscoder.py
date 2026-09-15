"""hcscoder CLI tests: SSE parsing, REPL helpers, lazy runtime, entry points."""

import tomllib
from pathlib import Path

from services.cli.repl import expand_file_refs, needs_approval, parse_slash
from services.llm.client import parse_sse_deltas
from services.runtime.core import PrimeRuntime


def test_parse_sse_deltas():
    payload = (
        'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
        'data: {"choices": [{"delta": {"content": " world"}}]}\n\n'
        'data: [DONE]\n'
    )
    assert parse_sse_deltas(payload) == ["Hello", " world"]
    assert parse_sse_deltas("garbage\n\n") == []
    assert parse_sse_deltas('data: not-json\n\ndata: [DONE]\n') == []


def test_parse_slash():
    assert parse_slash("/plan") == ("plan", [])
    assert parse_slash("/switch abc123") == ("switch", ["abc123"])
    assert parse_slash("hello") == ("", [])


def test_expand_file_refs(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("secret-content-42", encoding="utf-8")
    out, embedded = expand_file_refs(f"read @{f} please", cwd=".")
    assert "secret-content-42" in out and len(embedded) == 1
    out2, emb2 = expand_file_refs("read @/nope/missing.txt x", cwd=".")
    assert emb2 == [] and "@" in out2


def test_needs_approval():
    assert needs_approval("please refactor main.py") is None
    assert needs_approval("rm -rf / tmp") is not None
    assert needs_approval("read my .env file") is not None
    assert needs_approval("git push --force origin main") is not None


def test_runtime_lazy_heavy_subsystems():
    rt = PrimeRuntime()
    try:
        assert rt._rag is None and rt._subagents is None and rt._agent is None
    finally:
        rt.shutdown()


def test_entry_points_hcscoder():
    d = tomllib.load(open("pyproject.toml", "rb"))
    scripts = d["project"]["scripts"]
    assert scripts["hcscoder"] == "cli:cli"
    assert scripts["prime-agent"] == "cli:cli"  # alias kept


def test_terminal_rename_close(tmp_path):
    from services.terminal.sessions import TerminalManager
    tm = TerminalManager(store_dir=str(tmp_path / "t"))
    t = tm.create(name="orig", cwd=".")
    assert tm.rename(t.term_id, "renamed") is True
    assert tm.terminals[t.term_id].name == "renamed"
    assert tm.rename("term_nope", "x") is False
    assert tm.close(t.term_id) is True
    assert tm.close(t.term_id) is False


def test_permission_sensitive_paths_gated(tmp_path):
    from services.permissions.engine import PermissionEngine
    eng = PermissionEngine(policy_file=str(tmp_path / "perms.json"))
    assert eng.decide("read_file", "notes.txt", "s1")["decision"] == "allow"
    assert eng.decide("read_file", ".env", "s1")["decision"] in ("ask", "deny")
    assert eng.decide("shell_exec", "rm -rf /*", "s1")["decision"] == "deny"


def test_extract_code_blocks_tolerates_truncation():
    from services.agent.root_agent import extract_code_blocks
    full = "text ```python\nx = 1\n``` more ```python\ny = 2\n``` end"
    assert extract_code_blocks(full) == ["x = 1", "y = 2"]
    truncated = "prose ```python\nmcp.write_file('a', 'b'"
    assert extract_code_blocks(truncated) == ["mcp.write_file('a', 'b'"]
    assert extract_code_blocks("just prose, no code") == []


def test_find_app_home_priority(tmp_path, monkeypatch):
    import sys
    from services import paths as P
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "syspython"))
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "models.json").write_text("{}", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    cli_py = src / "cli.py"
    cli_py.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PRIME_HOME", str(home))
    assert P.find_app_home(str(cli_py), str(tmp_path)) == home.resolve()
    monkeypatch.delenv("PRIME_HOME")
    (src / "config").mkdir()
    (src / "config" / "models.json").write_text("{}", encoding="utf-8")
    assert P.find_app_home(str(cli_py), str(tmp_path)) == src.resolve()
    assert P.find_app_home("/nonexistent/cli.py", str(tmp_path)) == tmp_path.resolve()


def test_resolve_user_path(tmp_path):
    from services.paths import resolve_user_path
    assert resolve_user_path(".", str(tmp_path)) == str(tmp_path.resolve())
    assert resolve_user_path("sub", str(tmp_path)).endswith("sub")
    abs_p = str((tmp_path / "f.txt").resolve())
    assert resolve_user_path(abs_p, "/elsewhere") == abs_p


def test_find_app_home_venv_relative(tmp_path, monkeypatch):
    import sys
    from services import paths as P
    install = tmp_path / "prime-agent"
    (install / "config").mkdir(parents=True)
    (install / "config" / "models.json").write_text("{}", encoding="utf-8")
    venv = install / ".venv"
    venv.mkdir()
    monkeypatch.delenv("PRIME_HOME", raising=False)
    monkeypatch.setattr(sys, "prefix", str(venv))
    assert P.find_app_home("/nonexistent/cli.py", str(tmp_path)) == install.resolve()


def test_multiline_continuation():
    from services.cli.input import join_continuation, needs_continuation, read_multiline
    assert needs_continuation("foo \\") is True
    assert needs_continuation("foo") is False
    assert needs_continuation("f(a,") is True
    assert needs_continuation("f(a)") is False
    assert needs_continuation('x = "abc') is True
    assert needs_continuation("x = '''abc") is True
    assert needs_continuation("x = '''abc'''") is False
    assert join_continuation(["a \\", "b"]) == "a \nb"
    out = read_multiline(source=["total = (", "1 +", "2)"])
    assert out == "total = (\n1 +\n2)"
    assert read_multiline(source=[]) is None


def test_paste_mode():
    from services.cli.input import read_paste
    assert read_paste(source=["line1", "line2", ".", "ignored"]) == "line1\nline2"
    assert read_paste(source=[]) is None


def test_ui_renders_ascii_safe():
    from rich.console import Console as _C
    from services.cli.ui import Renderer
    c = _C(record=True, width=80)
    ui = Renderer(c)
    ui.banner("3.2.0", "Qwen3-4B", "C:/proj")
    ui.tool_card("kernel_exec", "x = 1", state="ok", elapsed_s=1.2)
    ui.final("hello **world**", ok=True, elapsed="3")
    ui.error_card("boom")
    ui.approval("shell", "why", "high", "rm f")
    out = c.export_text()
    for token in ["hcscoder", "3.2.0", "kernel_exec", "hello", "WHAT FAILED", "Approval"]:
        assert token in out, token
    # our own strings must be pure ASCII (rich borders auto-downgrade on pipes)
    import io as _io
    for fn in ["services/cli/ui.py", "services/cli/input.py", "services/cli/repl.py"]:
        src = _io.open(fn, encoding="utf-8").read()
        bad = sorted({ch for ch in src if ord(ch) > 127})
        assert bad == [], (fn, bad)


class _FakeSessions:
    def __init__(self, mgr):
        self._mgr = mgr

    def __getattr__(self, name):
        return getattr(self._mgr, name)


class _FakeRuntime:
    def __init__(self, tmp_path):
        from services.session.manager import SessionManager
        self.sessions = SessionManager(sessions_dir=str(tmp_path / "s"))
        self.interrupted = []

    async def run_task_stream(self, session_id, prompt):
        yield {"type": "status", "text": "working"}
        yield {"type": "delta", "text": "hello "}
        yield {"type": "delta", "text": "streamed"}
        yield {"type": "tool", "text": "x = 1"}
        yield {"type": "done", "response": "hello streamed",
               "elapsed_s": 0.1, "verification": {"status": "PASS"},
               "artifacts": []}

    def interrupt(self, session_id):
        self.interrupted.append(session_id)
        return {"ok": True}


def test_repl_streaming_pipeline_headless(tmp_path):
    from rich.console import Console as _C
    from services.cli.repl import HCSRepl
    rt = _FakeRuntime(tmp_path)
    repl = HCSRepl(rt, cwd=str(tmp_path))
    repl.console = _C(record=True, width=100)
    repl.ui = __import__("services.cli.ui", fromlist=["Renderer"]).Renderer(repl.console)
    repl.run_streaming("safe test prompt")
    out = repl.console.export_text()
    assert "hello streamed" in out
    assert "verification" in out
    assert "session sess_" in out
    assert rt.interrupted == []


def test_repl_streaming_error_path(tmp_path):
    from rich.console import Console as _C
    from services.cli.repl import HCSRepl

    class _ErrRt(_FakeRuntime):
        async def run_task_stream(self, session_id, prompt):
            yield {"type": "error", "reason": "boom-test"}

    repl = HCSRepl(_ErrRt(tmp_path), cwd=str(tmp_path))
    repl.console = _C(record=True, width=100)
    repl.ui = __import__("services.cli.ui", fromlist=["Renderer"]).Renderer(repl.console)
    repl.run_streaming("safe test prompt")
    assert "boom-test" in repl.console.export_text()
