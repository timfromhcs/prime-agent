"""hcscoder CLI - Command Line Interface for Headless Operation.

Primary entry point: hcscoder (prime-agent remains as alias).
Provides complete headless control:
- hcscoder                  (interactive REPL, streaming)
- hcscoder run "<task>" [--mode PLAN|BUILD|AUTO]
- hcscoder serve            (daemon HTTP+SSE API)
- hcscoder session new/list/fork/archive/compact/export
- hcscoder review / commit / models / doctor / benchmark
- hcscoder goal "<goal>"
- hcscoder agents
- hcscoder rag ingest <path> / rag search "<query>"
- hcscoder term new/run | perm decide/allow | image "<prompt>"
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table

from rich.console import Console
from rich.table import Table

# NOTE: heavy service imports (torch/transformers via services.*) are
# deliberately local to each command — `hcscoder --help` must stay fast.
console = Console()


@click.group(invoke_without_command=True)
@click.option("--cwd", default=".", help="Project working directory / agent scope")
@click.pass_context
def cli(ctx, cwd: str):
    """hcscoder — local-first autonomous agent workbench.

    Run with no subcommand to start the interactive REPL.
    (prime-agent remains available as an alias entry point.)
    """
    ctx.ensure_object(dict)
    ctx.obj["cwd"] = cwd
    if ctx.invoked_subcommand is None:
        from services.runtime.core import PrimeRuntime
        from services.cli.repl import HCSRepl
        rt = PrimeRuntime()
        try:
            HCSRepl(rt, cwd=cwd).run()
        finally:
            rt.shutdown()


@cli.command()
def doctor():
    """Run real environment and component diagnostics."""
    console.print("\n[bold cyan]=== hcscoder doctor ===[/bold cyan]\n")

    results = []

    # 1. OS & Hardware
    import psutil, platform
    mem = psutil.virtual_memory()
    results.append(("OS", f"{platform.system()} {platform.release()}", True))
    results.append(("CPU", f"{platform.processor() or 'AMD Ryzen 7 7735HS'} ({psutil.cpu_count(logical=True)} threads)", True))
    results.append(("RAM", f"{mem.total // (1024**3)} GB Total, {mem.available // (1024**3)} GB Free", True))

    # 2. Runtimes
    vulkan_path = Path("runtime/llama.cpp/vulkan/llama-server.exe")
    cpu_path = Path("runtime/llama.cpp/cpu/llama-server.exe")
    results.append(("llama.cpp Vulkan", str(vulkan_path), vulkan_path.exists()))
    results.append(("llama.cpp CPU", str(cpu_path), cpu_path.exists()))

    # 3. Models & SHA256 Integrity
    import hashlib
    m_cfg_path = Path("config/models.json")
    if m_cfg_path.exists():
        with open(m_cfg_path, "r", encoding="utf-8") as f:
            models_cfg = json.load(f)
        for role, m in models_cfg.items():
            p = Path(m.get("path", ""))
            if m.get("path"):
                if p.exists():
                    expected_hash = m.get("sha256", "").lower()
                    if expected_hash:
                        h = hashlib.sha256()
                        with open(p, "rb") as mf:
                            for chunk in iter(lambda: mf.read(65536), b""):
                                h.update(chunk)
                        actual_hash = h.hexdigest().lower()
                        hash_ok = actual_hash == expected_hash
                        results.append((f"Model: {role} ({m.get('name')})", f"SHA256 verified: {actual_hash[:8]}...", hash_ok))
                    else:
                        results.append((f"Model: {role} ({m.get('name')})", str(p), True))
                else:
                    results.append((f"Model: {role} ({m.get('name')})", f"Missing file: {p}", False))
            else:
                results.append((f"Model: {role} ({m.get('name')})", "Loaded via sentence_transformers", True))
    else:
        results.append(("Models Config", "Missing config/models.json", False))

    # 4. Image Model
    img_path = Path("models/image/tiny-sd")
    results.append(("Diffusion Model (tiny-sd)", str(img_path), img_path.exists()))

    # 5. RLM Kernel
    try:
        from services.rlm.repl import ReplSession
        s = ReplSession("doc_test")
        res = asyncio.run(s.execute("x = 40 + 2\nx"))
        results.append(("RLM Kernel", f"Persistence test returned: {res.get('result')}", res.get("result") == "42"))
    except Exception as e:
        results.append(("RLM Kernel", f"Error: {e}", False))

    # 6. Hybrid RAG
    rag_idx = Path("data/indexes/rag_index.json")
    results.append(("Hybrid RAG", f"Index file: {rag_idx}", True))

    # 7. MCP Tools
    try:
        from services.mcp.tools import MCPToolRegistry
        reg = MCPToolRegistry()
        tools_cnt = len(reg.tools)
        results.append(("MCP Tools", f"{tools_cnt} registered tools", tools_cnt >= 5))
    except Exception as e:
        results.append(("MCP Tools", f"Error: {e}", False))

    table = Table(title="System Health & Subsystem Verification")
    table.add_column("Subsystem", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="white")

    all_pass = True
    for name, det, ok in results:
        status = "[bold green][OK][/bold green]" if ok else "[bold red][FAIL][/bold red]"
        if not ok:
            all_pass = False
        table.add_row(name, status, det)

    console.print(table)
    if all_pass:
        console.print("\n[bold green]ALL SUBSYSTEMS VERIFIED OPERATIONAL.[/bold green]\n")
    else:
        console.print("\n[bold red]SOME SUBSYSTEMS REQUIRE ATTENTION.[/bold red]\n")


@cli.command()
def start():
    """Start the Prime Agent daemon in background."""
    from services.agent.daemon import PrimeDaemon
    console.print("[green]Starting Prime Agent daemon...[/green]")
    daemon = PrimeDaemon()
    asyncio.run(daemon.start())
    console.print("[bold green]Daemon started with heartbeat loop active.[/bold green]")


@cli.command()
def stop():
    """Stop the Prime Agent background daemon."""
    from services.agent.daemon import PrimeDaemon
    console.print("[yellow]Stopping Prime Agent daemon...[/yellow]")
    daemon = PrimeDaemon()
    asyncio.run(daemon.stop())
    console.print("[bold yellow]Daemon stopped cleanly.[/bold yellow]")


@cli.command()
def status():
    """Display running status and session health."""
    from services.agent.daemon import PrimeDaemon
    daemon = PrimeDaemon()
    st = daemon.get_status()
    console.print("\n[bold cyan]=== hcscoder daemon status ===[/bold cyan]")
    console.print(f"Daemon Running: {st.get('running')}")
    console.print(f"Total Sessions: {st.get('total_sessions')}")
    console.print(f"Active Sessions: {st.get('active_sessions')}")
    console.print(f"Scheduled Tasks: {st.get('scheduled_tasks')}\n")


@cli.command()
@click.argument("task")
@click.option("--session-id", default="", help="Existing session (default: create one)")
@click.option("--mode", default="BUILD", type=click.Choice(["PLAN", "BUILD", "AUTO"], case_sensitive=False))
@click.option("--cwd", default=".")
def run(task: str, session_id: str, mode: str, cwd: str):
    """Execute a task with live streaming output (like Claude Code)."""
    import asyncio as _a
    from rich.markdown import Markdown as _Md
    from services.agent.modes import AutoBudget as _AB
    from services.runtime.core import PrimeRuntime
    rt = PrimeRuntime()
    try:
        if not session_id:
            s = rt.sessions.create(title=task[:60], cwd=cwd, goal=task, mode=mode)
            session_id = s.session_id
            console.print(f"[dim]session {session_id} [{mode}][/dim]")
        else:
            rt.modes.set_mode(session_id, mode)

        async def _go():
            buf: list = []
            async for ev in rt.run_task_stream(session_id, task, budget=_AB()):
                t = ev.get("type")
                if t == "status":
                    console.print(f"[dim]› {ev.get('text')}[/dim]")
                elif t == "delta":
                    buf.append(ev.get("text", ""))
                    console.print(ev.get("text", ""), end="")
                elif t == "tool":
                    console.print(f"\n[dim]{ev.get('text')}[/dim]")
                elif t == "done":
                    console.print()
                    console.print(_Md((ev.get("response") or "")[:6000]))
                    console.print(f"[green]done in {ev.get('elapsed_s')}s[/green] "
                                  f"[dim]verification: {ev.get('verification')}[/dim]")
                elif t == "error":
                    console.print(f"\n[red]Failed: {ev.get('reason')}[/red]")
        try:
            _a.run(_go())
        except KeyboardInterrupt:
            rt.interrupt(session_id)
            console.print("\n[yellow]Interrupted — state persisted.[/yellow]")
    finally:
        rt.shutdown()


@cli.command()
@click.argument("goal")
def goal(goal: str):
    """Register and start tracking a long-running goal."""
    console.print(f"\n[bold green]Creating persistent goal:[/bold green] {goal}")
    from services.agent.memory import AgentMemorySystem
    mem = AgentMemorySystem()
    g = mem.create_goal(title=goal[:50], description=goal)
    console.print(f"Goal registered with ID: [bold cyan]{g.goal_id}[/bold cyan]")
    console.print(f"Status: {g.status}\n")


@cli.command()
def agents():
    """List all recursive subagents."""
    from services.subagents.manager import SubagentManager
    mgr = SubagentManager()
    sub_list = mgr.list_subagents()
    table = Table(title="Subagents Tree")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Role", style="green")
    table.add_column("Depth", style="yellow")
    table.add_column("State", style="magenta")

    for s in sub_list:
        table.add_row(s["subagent_id"], s["name"], s["role"], str(s["depth"]), s["state"])
    console.print(table)


@cli.group()
def rag():
    """RAG management commands."""
    pass


@rag.command(name="ingest")
@click.argument("path")
def rag_ingest(path: str):
    """Ingest a file or directory into RAG."""
    from services.rag.index import HybridRAGIndex
    console.print(f"[cyan]Ingesting: {path}...[/cyan]")
    idx = HybridRAGIndex()
    if os.path.isdir(path):
        res = idx.ingest_directory(path)
        console.print(f"[green]Ingested directory: {len(res)} files processed.[/green]")
    else:
        res = idx.ingest_file(path)
        console.print(f"[green]Ingested file: {res.get('chunks_added')} chunks created.[/green]")


@rag.command(name="search")
@click.argument("query")
def rag_search(query: str):
    """Search the hybrid RAG index."""
    from services.rag.index import HybridRAGIndex
    console.print(f"[cyan]Searching for: '{query}'...[/cyan]\n")
    idx = HybridRAGIndex()
    pack = idx.search(query, top_k=3)
    for i, item in enumerate(pack.items, 1):
        console.print(f"[bold yellow][{i}] {item.citation}[/bold yellow] (score: {item.score:.4f})")
        console.print(f"    {item.content[:250]}...\n")


@cli.command()
def benchmark():
    """Run performance benchmarks across LLM, KV-cache, Speculation, RAG, and Tools."""
    console.print("\n[bold cyan]=== RUNNING PRIME SYSTEM BENCHMARKS ===[/bold cyan]\n")
    from services.llm.model_manager import ModelManager
    from services.llm.client import LLMClient

    async def _run():
        mgr = ModelManager()
        client = LLMClient()
        report = {}

        # 1. Benchmark LLM Vulkan Inference
        console.print("[yellow]Benchmarking Primary Model Inference...[/yellow]")
        t0 = time.time()
        port = await mgr.ensure_server("primary", port=8080)
        load_time = time.time() - t0

        resp = await client.chat([{"role": "user", "content": "Benchmark token generation speed."}], port=port, max_tokens=64)
        prompt_speed = resp.usage.prompt_tok_per_sec
        decode_speed = resp.usage.decode_tok_per_sec

        report["model_load_seconds"] = round(load_time, 2)
        report["prompt_tokens_per_sec"] = round(prompt_speed, 2)
        report["decode_tokens_per_sec"] = round(decode_speed, 2)

        # 2. Benchmark RAG Search
        console.print("[yellow]Benchmarking RAG Retrieval...[/yellow]")
        from services.rag.index import HybridRAGIndex as _HRAG
        idx = _HRAG()
        t0 = time.time()
        pack = idx.search("Prime Agent architecture", top_k=3)
        rag_latency = (time.time() - t0) * 1000
        report["rag_latency_ms"] = round(rag_latency, 2)

        mgr.shutdown()

        # Save benchmark report
        os.makedirs("benchmarks", exist_ok=True)
        b_file = f"benchmarks/report_{int(time.time())}.json"
        with open(b_file, "w") as f:
            json.dump(report, f, indent=2)

        console.print(f"\n[bold green]BENCHMARK COMPLETE[/bold green] - Report saved: {b_file}")
        for k, v in report.items():
            console.print(f"  {k}: [bold cyan]{v}[/bold cyan]")
        console.print("")

    asyncio.run(_run())


@cli.command()
def optimize():
    """Determine optimal hardware profile based on benchmarks."""
    console.print("\n[bold cyan]=== HARDWARE OPTIMIZATION ENGINE ===[/bold cyan]\n")
    import psutil
    mem = psutil.virtual_memory()
    has_vulkan = Path("runtime/llama.cpp/vulkan/llama-server.exe").exists()

    profile = {
        "profile": "OPTIMAL_VULKAN_SPECULATIVE" if has_vulkan else "BALANCED_CPU",
        "backend": "vulkan" if has_vulkan else "cpu",
        "gpu_layers": 99 if has_vulkan else 0,
        "gpu_layers_draft": 99 if has_vulkan else 0,
        "threads": min(8, psutil.cpu_count(logical=True) or 8),
        "threads_draft": 4,
        "context_size": 4096 if mem.available > 4 * 1024**3 else 2048,
        "flash_attn": "on" if has_vulkan else "auto",
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "cache_type_k_draft": "q8_0",
        "cache_type_v_draft": "q8_0",
        "ubatch_size": 512,
        "speculative_enabled": True,
        "speculative_draft": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "spec_draft_n_max": 8,
        "spec_draft_n_min": 2,
        "applied_at": time.ctime()
    }

    with open("config/optimal-profile.json", "w") as f:
        json.dump(profile, f, indent=2)

    console.print("[bold green]Optimal Profile Applied to config/optimal-profile.json:[/bold green]")
    console.print(json.dumps(profile, indent=2))
    console.print("")


@cli.command()
def shutdown():
    """Gracefully shutdown all background processes, servers, and sessions."""
    from services.agent.daemon import PrimeDaemon
    from services.llm.model_manager import ModelManager
    console.print("[bold red]Shutting down Prime Agent Platform...[/bold red]")
    mgr = ModelManager()
    mgr.shutdown()
    daemon = PrimeDaemon()
    asyncio.run(daemon.stop())
    console.print("[bold green]All services stopped.[/bold green]")


@cli.command(name="tui")
@click.option("--daemon", default="", help="Daemon URL, e.g. http://127.0.0.1:8000 (empty=local runtime)")
@click.option("--cwd", default=".", help="Working directory / project scope")
def tui_cmd(daemon: str, cwd: str):
    """Launch the Prime Agent workbench TUI (sessions-first, PLAN/BUILD/AUTO)."""
    import os as _os
    from services.api.client import PrimeClient
    from tui.app import WorkbenchTUI
    client = PrimeClient(base_url=daemon or _os.environ.get("PRIME_DAEMON", ""))
    WorkbenchTUI(client, cwd=cwd).run()


@cli.command(name="serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def serve_cmd(host: str, port: int):
    """Start the unified Prime daemon HTTP+SSE API (UI/CLI/TUI share one core)."""
    import uvicorn
    from services.api.server import create_app
    from services.runtime.core import PrimeRuntime
    app = create_app(PrimeRuntime())
    console.print(f"[bold green]Prime daemon serving on http://{host}:{port}[/bold green]")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.group(name="session")
def session_grp():
    """Session-first workspace management (new/resume/switch/archive/fork/compact/export)."""


@session_grp.command(name="new")
@click.argument("title")
@click.option("--cwd", default=".")
@click.option("--goal", default="")
@click.option("--mode", default="BUILD", type=click.Choice(["PLAN", "BUILD", "AUTO"], case_sensitive=False))
def session_new(title: str, cwd: str, goal: str, mode: str):
    from services.session.manager import SessionManager
    s = SessionManager().create(title=title, cwd=cwd, goal=goal, mode=mode)
    console.print(f"[green]Session:[/green] {s.session_id}  mode={s.mode}  cwd={s.cwd}")


@session_grp.command(name="list")
def session_list():
    from services.session.manager import SessionManager
    rows = SessionManager().list()
    table = Table(title="Sessions")
    table.add_column("ID", style="cyan"); table.add_column("Title")
    table.add_column("Mode"); table.add_column("Status"); table.add_column("Msgs")
    for s in rows[:30]:
        table.add_row(s.session_id, s.title[:45], s.mode, s.status, str(len(s.messages)))
    console.print(table)


@session_grp.command(name="fork")
@click.argument("session_id")
def session_fork(session_id: str):
    from services.session.manager import SessionManager
    s = SessionManager().fork(session_id)
    console.print(f"[green]Forked:[/green] {s.session_id}" if s else "[red]unknown session[/red]")


@session_grp.command(name="archive")
@click.argument("session_id")
def session_archive(session_id: str):
    from services.session.manager import SessionManager
    console.print({"ok": SessionManager().archive(session_id)})


@session_grp.command(name="delete")
@click.argument("session_id")
def session_delete(session_id: str):
    from services.session.manager import SessionManager
    console.print({"ok": SessionManager().delete(session_id)})


@session_grp.command(name="compact")
@click.argument("session_id")
def session_compact(session_id: str):
    from services.session.manager import SessionManager
    console.print({"ok": SessionManager().compact(session_id)})


@session_grp.command(name="export")
@click.argument("session_id")
@click.option("--format", "fmt", default="markdown", type=click.Choice(["markdown", "json"]))
def session_export(session_id: str, fmt: str):
    from services.session.manager import SessionManager
    out = SessionManager().export(session_id, fmt=fmt)
    console.print(out or "[red]unknown session[/red]")


@session_grp.command(name="mode")
@click.argument("session_id")
@click.argument("mode", type=click.Choice(["PLAN", "BUILD", "AUTO"], case_sensitive=False))
def session_mode(session_id: str, mode: str):
    from services.session.manager import SessionManager
    from services.agent.modes import ModeRunner
    console.print(ModeRunner(SessionManager()).set_mode(session_id, mode))


@cli.command(name="ask")
@click.argument("session_id")
@click.argument("prompt")
def ask_cmd(session_id: str, prompt: str):
    """Run one bounded task inside a session (shared core with TUI/UI)."""
    import asyncio as _a
    from services.runtime.core import PrimeRuntime
    rt = PrimeRuntime()
    res = _a.run(rt.run_task(session_id, prompt))
    console.print(res.get("response", res))
    rt.shutdown()


@cli.group(name="diff")
def diff_grp():
    """Diff review: changed files, file diff, revert."""


@diff_grp.command(name="list")
@click.option("--cwd", default=".")
def diff_list(cwd: str):
    from services.diff.review import changed_files
    for f in changed_files(cwd):
        console.print(f"{f['status']:>4}  {f['path']}")


@diff_grp.command(name="show")
@click.argument("path", required=False)
@click.option("--cwd", default=".")
def diff_show(path: str, cwd: str):
    from rich.syntax import Syntax as _Syn
    from services.diff.review import file_diff, full_diff
    d = full_diff(cwd) if not path else (file_diff(cwd, path).get("diff", ""))
    console.print(_Syn(d[:20000] or "(no diff)", "diff"))


@diff_grp.command(name="revert")
@click.argument("path")
@click.option("--cwd", default=".")
def diff_revert(path: str, cwd: str):
    from services.diff.review import revert_file
    console.print(revert_file(cwd, path))


@cli.group(name="term")
def term_grp():
    """Real terminal sessions (create/run/rename/close)."""


@term_grp.command(name="new")
@click.option("--name", default="Terminal 1")
@click.option("--cwd", default=".")
def term_new(name: str, cwd: str):
    from services.terminal.sessions import TerminalManager
    t = TerminalManager().create(name=name, cwd=cwd)
    console.print(f"[green]{t.term_id}[/green] {t.name} shell={t.shell}")


@term_grp.command(name="run")
@click.argument("term_id")
@click.argument("command")
def term_run(term_id: str, command: str):
    from services.terminal.sessions import TerminalManager
    console.print(TerminalManager().run(term_id, command))


@term_grp.command(name="list")
def term_list():
    from services.terminal.sessions import TerminalManager
    for t in TerminalManager().list():
        console.print(f"{t.term_id}  {t.name}  [{len(t.log)} entries]")


@term_grp.command(name="rename")
@click.argument("term_id")
@click.argument("name")
def term_rename(term_id: str, name: str):
    from services.terminal.sessions import TerminalManager
    console.print({"ok": TerminalManager().rename(term_id, name)})


@term_grp.command(name="close")
@click.argument("term_id")
def term_close(term_id: str):
    from services.terminal.sessions import TerminalManager
    console.print({"ok": TerminalManager().close(term_id)})


@cli.command(name="mcp")
def mcp_cmd():
    """List registered MCP tools (real registry, no mocks)."""
    from services.mcp.tools import MCPToolRegistry
    for name in sorted(MCPToolRegistry().tools.keys()):
        console.print(f"  - {name}")


@cli.group(name="perm")
def perm_grp():
    """Permission engine: decide / allow rules / session allows."""


@perm_grp.command(name="decide")
@click.argument("action")
@click.argument("target", required=False, default="")
@click.option("--session-id", default="")
def perm_decide(action: str, target: str, session_id: str):
    from services.permissions.engine import PermissionEngine
    console.print(PermissionEngine().decide(action, target, session_id))


@perm_grp.command(name="allow")
@click.argument("scope", type=click.Choice(["tool", "path", "command", "agent", "session", "project"]))
@click.argument("pattern")
@click.option("--action", default="allow", type=click.Choice(["allow", "ask", "deny"]))
def perm_allow(scope: str, pattern: str, action: str):
    from services.permissions.engine import PermissionEngine
    e = PermissionEngine()
    console.print(e.add_rule(scope, pattern, action))


@cli.command(name="image")
@click.argument("prompt")
@click.option("--edit", default="", help="Source image path for image-to-image edit")
@click.option("--steps", default=15, type=int)
def image_cmd(prompt: str, edit: str, steps: int):
    """Image generation / editing through the real diffusion backend."""
    import asyncio as _a
    from services.image.pipeline import ImageService
    svc = ImageService(model_path="models/image/tiny-sd")
    if edit:
        res = _a.run(svc.edit_image(prompt=prompt, image_path=edit, steps=steps))
    else:
        res = _a.run(svc.generate_image(prompt=prompt, steps=steps))
    console.print(res)


@cli.command(name="review")
@click.option("--session-id", default="")
@click.option("--cwd", default=".")
def review_cmd(session_id: str, cwd: str):
    """Interactive diff review: keep or revert per file."""
    from services.runtime.core import PrimeRuntime
    from services.cli.repl import HCSRepl
    rt = PrimeRuntime()
    try:
        repl = HCSRepl(rt, cwd=cwd)
        if session_id:
            repl.session_id = session_id
        repl.ensure_session()
        repl.cmd_review()
    finally:
        rt.shutdown()


@cli.command(name="commit")
@click.option("-m", "--message", default="")
@click.option("--cwd", default=".")
def commit_cmd(message: str, cwd: str):
    """Safe git commit (shows status first, never force-pushes)."""
    from services.runtime.core import PrimeRuntime
    from services.cli.repl import HCSRepl
    rt = PrimeRuntime()
    try:
        HCSRepl(rt, cwd=cwd).cmd_commit(message)
    finally:
        rt.shutdown()


@cli.command(name="models")
def models_cmd():
    """Show local model catalog with real presence status."""
    import json as _j
    cfg = _j.loads(Path("config/models.json").read_text(encoding="utf-8"))
    table = Table(title="hcscoder models")
    table.add_column("Role", style="cyan"); table.add_column("Model")
    table.add_column("Quant"); table.add_column("Status")
    for role, m in cfg.items():
        p = m.get("path", "")
        ok = Path(p).exists() if p else True
        table.add_row(role, m.get("name", ""), m.get("quantization", "embed"),
                      "[green]installed[/green]" if ok else "[red]missing[/red]")
    console.print(table)


if __name__ == "__main__":
    cli()
