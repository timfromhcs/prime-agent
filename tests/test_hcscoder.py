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
