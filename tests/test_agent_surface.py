"""Agent surface tests: web fetch (real local HTTP), bridge op routing, prompt honesty."""

import threading

import pytest

from services.rlm.bridge import ImageBridge, McpBridge, RagBridge, RlmBridge, WebBridge


class FakeHost:
    def __init__(self):
        self.ops = []

    async def __call__(self, payload):
        self.ops.append(payload["op"])
        return {"status": "ok", "op": payload["op"]}


def _bridge_cases():
    h = FakeHost()
    return h, [
        (RlmBridge(h).spawn("t", name="n", role="research"), "subagent_spawn"),
        (RlmBridge(h).collect("s1"), "subagent_collect"),
        (RlmBridge(h).list_subagents(), "subagent_list"),
        (RlmBridge(h).send_message("a", "b"), "subagent_message"),
        (RlmBridge(h).get_harness_state(), "harness_get_state"),
        (RlmBridge(h).harness.create_skill("s", "d", "c"), "harness_create_skill"),
        (RlmBridge(h).harness.create_memory("k", "v"), "harness_create_memory"),
        (RagBridge(h).search("q"), "rag_search"),
        (RagBridge(h).ingest("p"), "rag_ingest"),
        (ImageBridge(h).generate("p"), "image_generate"),
        (ImageBridge(h).edit("p", "i.png"), "image_edit"),
        (ImageBridge(h).describe("i.png"), "image_describe"),
        (McpBridge(h).call("s", "read_file", path="x"), "mcp_call"),
        (WebBridge(h).fetch("http://x"), "web_fetch"),
    ]


@pytest.mark.asyncio
async def test_bridge_ops_route_correctly():
    h, cases = _bridge_cases()
    for coro, expected in cases:
        res = await coro
        assert res["op"] == expected, expected
    assert h.ops == [e for _, e in cases]


def test_web_fetch_real_local_http(tmp_path):
    import functools
    import http.server
    (tmp_path / "page.html").write_text(
        "<html><head><title>Hello Test</title></head>"
        "<body><script>var x=1;</script><p>Visible text here.</p></body></html>",
        encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        from services.webutils.fetch import fetch_url
        r = fetch_url(f"http://127.0.0.1:{port}/page.html")
        assert r.get("status") == 200
        assert r.get("title") == "Hello Test"
        assert "Visible text here." in r.get("text", "")
        assert "var x=1" not in r.get("text", "")
        bad = fetch_url("file:///etc/passwd")
        assert "error" in bad
    finally:
        srv.shutdown()


def test_system_prompt_only_documents_real_apis():
    import re
    from services.agent.root_agent import SYSTEM_PROMPT
    from services.rlm.repl import ReplSession
    sess = ReplSession("prompt_audit")
    try:
        ns = sess.namespace
        allowed_roots = set(ns.keys())
        fences = re.findall(r"```python(.*?)```", SYSTEM_PROMPT, re.DOTALL)
        assert fences, "prompt must contain executable examples"
        doc_calls = set(re.findall(r"await\s+(\w+)\.(\w+)", SYSTEM_PROMPT))
        # rlm.harness.* is attribute-of-attribute; check separately
        for root, meth in doc_calls:
            assert root in allowed_roots, f"prompt invents namespace: {root}"
            if root == "rlm" and meth == "harness":
                continue
            obj = ns[root]
            assert hasattr(obj, meth), f"prompt invents API: {root}.{meth}"
        assert hasattr(ns["rlm"], "harness")
        for m in ("create_skill", "create_memory", "create_strategy"):
            assert hasattr(ns["rlm"].harness, m), m
    finally:
        pass
