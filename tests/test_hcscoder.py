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
