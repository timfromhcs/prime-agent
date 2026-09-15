"""Prime Agent workbench TUI (Rich, keyboard-first, offline-first).

Layout: sessions | chat/task | context. Bottom: terminal/activity line.
Slash commands + Ctrl+P style palette (via `/palette`).

Run:  prime-agent tui   (local runtime)  or  prime-agent tui --daemon http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from services.api.client import PrimeClient

console = Console()

HELP = """Slash commands:
  /help /new <title> /sessions /switch <id> /fork /archive /delete <id> /export
  /plan /build /auto /goal <text> /todo <title> /compact
  /agents /spawn <role> <task...> /context /git /diff [path] /revert <path>
  /term [command...] /terms /rag <query> /ingest <path> /mcp /models /doctor
  /palette /attach <path> /image <prompt> /quit
Keys: type to chat • @file reference supported (paste path) • Ctrl+C interrupts (via /stop)
Modes: PLAN read-only • BUILD executes plan • AUTO bounded autonomous
"""


class WorkbenchTUI:
    def __init__(self, client: PrimeClient, cwd: str = "."):
        self.client = client
        self.cwd = cwd
        self.session_id: Optional[str] = None
        self.attachments: list[str] = []

    # -- rendering --
    def header(self, ctx: dict) -> None:
        mode = ctx.get("mode", "?") if ctx else "?"
        console.print(Panel.fit(f"[bold]PRIME AGENT[/bold]  session={self.session_id or '-'}  mode=[bold cyan]{mode}[/bold cyan]  msgs={ctx.get('messages',0) if ctx else 0} tokens~{ctx.get('tokens_est',0) if ctx else 0}",
                                border_style="cyan"))

    def show_sessions(self) -> None:
        data = self.client.list_sessions()
        t = Table(title="Sessions", show_lines=False)
        t.add_column("ID", style="cyan"); t.add_column("Title"); t.add_column("Mode"); t.add_column("Status")
        for s in data.get("sessions", [])[:20]:
            mark = "●" if s["session_id"] == self.session_id else " "
            t.add_row(mark + s["session_id"], s["title"][:40], s.get("mode", ""), s.get("status", ""))
        console.print(t)

    def show_context(self) -> None:
        if not self.session_id:
            console.print("[yellow]No session. /new first.[/yellow]"); return
        ctx = self.client.context(self.session_id)
        t = Table(title="Context", show_header=False)
        for k in ("mode", "messages", "tokens_est", "tool_calls", "plan_steps", "models_configured"):
            t.add_row(str(k), str(ctx.get(k, "")))
        console.print(t)
        if ctx.get("todos"):
            tt = Table(title="Todos")
            tt.add_column("ID"); tt.add_column("Title"); tt.add_column("Status"); tt.add_column("Evidence")
            for td in ctx["todos"][-15:]:
                tt.add_row(td.get("todo_id", ""), td.get("title", "")[:50], td.get("status", ""), (td.get("evidence") or "")[:60])
            console.print(tt)

    def show_transcript(self, limit: int = 8) -> None:
        if not self.session_id:
            return
        s = self.client.get_session(self.session_id).get("session") or {}
        for m in (s.get("messages") or [])[-limit:]:
            role = m.get("role", "?")
            style = "green" if role == "assistant" else ("cyan" if role == "user" else "dim")
            console.print(Panel(Markdown(m.get("content", "")[:3000]), title=role, border_style=style))

    def ensure_session(self) -> bool:
        if self.session_id:
            return True
        data = self.client.list_sessions().get("sessions", [])
        if data:
            self.session_id = data[0]["session_id"]
            return True
        r = self.client.create_session("Workbench session", cwd=self.cwd)
        self.session_id = (r.get("session") or {}).get("session_id")
        return bool(self.session_id)

    # -- commands --
    def palette(self) -> None:
        console.print(Panel(HELP, title="Command palette  (type /<cmd>)", border_style="magenta"))

    def cmd_git(self) -> None:
        if not self.ensure_session():
            return
        g = self.client.git_state(self.session_id)
        st = g.get("status", {})
        console.print(f"[bold]branch:[/bold] {st.get('branch','')}")
        t = Table(title="Changed files")
        t.add_column("st"); t.add_column("path")
        for f in g.get("changed", [])[:40]:
            t.add_row(f.get("status", ""), f.get("path", ""))
        console.print(t)
        diff = g.get("diff", "")[:4000]
        if diff:
            console.print(Syntax(diff, "diff", line_numbers=False))

    def cmd_doctor(self) -> None:
        from pathlib import Path as _P
        import json as _j
        rows = []
        rows.append(("llama.cpp vulkan", _P("runtime/llama.cpp/vulkan/llama-server.exe").exists()))
        rows.append(("llama.cpp cpu", _P("runtime/llama.cpp/cpu/llama-server.exe").exists()))
        try:
            cfg = _j.loads(_P("config/models.json").read_text(encoding="utf-8"))
            for role, m in cfg.items():
                p = m.get("path", "")
                rows.append((f"model:{role}", _P(p).exists() if p else True))
        except Exception as e:
            rows.append(("models.json", False))
        t = Table(title="Doctor")
        t.add_column("check"); t.add_column("ok")
        for k, ok in rows:
            t.add_row(k, "[green]OK[/green]" if ok else "[red]FAIL[/red]")
        console.print(t)

    def handle_slash(self, line: str) -> bool:
        """Return False to quit."""
        try:
            parts = shlex.split(line)
        except Exception:
            parts = line.split()
        if not parts:
            return True
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("/quit", "/exit", "/q"):
            return False
        if cmd == "/help":
            console.print(Panel(HELP, border_style="cyan")); return True
        if cmd == "/palette":
            self.palette(); return True
        if cmd == "/new":
            title = " ".join(args) or "Workbench session"
            r = self.client.create_session(title, cwd=self.cwd)
            self.session_id = (r.get("session") or {}).get("session_id")
            console.print(f"[green]New session:[/green] {self.session_id}"); return True
        if cmd == "/sessions":
            self.show_sessions(); return True
        if cmd == "/switch" and args:
            self.session_id = args[0]
            console.print(f"[cyan]Switched to {self.session_id}[/cyan]"); return True
        if cmd in ("/plan", "/build", "/auto"):
            if self.ensure_session():
                r = self.client.set_mode(self.session_id, cmd[1:].upper())
                console.print(f"[cyan]Mode:[/cyan] {r}"); self.show_transcript(3)
            return True
        if cmd == "/context":
            self.show_context(); return True
        if cmd == "/git" or cmd == "/diff" and not args:
            self.cmd_git(); return True
        if cmd == "/doctor":
            self.cmd_doctor(); return True
        if cmd == "/mcp":
            if self.client.remote:
                import httpx
                d = httpx.get(f"{self.client.base_url}/api/mcp/tools", timeout=15).json()
                console.print(d)
            else:
                from services.mcp.tools import MCPToolRegistry
                console.print(sorted(MCPToolRegistry().tools.keys()))
            return True
        if cmd == "/models":
            if self.client.remote:
                import httpx
                d = httpx.get(f"{self.client.base_url}/api/models", timeout=15).json()
                console.print(d)
            else:
                import json as _j
                console.print(_j.loads(Path("config/models.json").read_text(encoding="utf-8")).keys())
            return True
        if cmd == "/rag" and args:
            q = " ".join(args)
            if self.client.remote:
                import httpx
                d = httpx.post(f"{self.client.base_url}/api/rag/search", json={"query": q}, timeout=60).json()
                for i, it in enumerate(d.get("items", [])[:5], 1):
                    console.print(f"[{i}] {it.get('citation')} ({it.get('score',0):.3f})\n  {it.get('content','')[:300]}")
            else:
                from services.runtime.core import PrimeRuntime
                rt = self.client._local
                pack = rt.rag.search(q, top_k=5)
                for i, it in enumerate(pack.items, 1):
                    console.print(f"[{i}] {it.citation} ({it.score:.3f})\n  {it.content[:300]}")
            return True
        if cmd == "/ingest" and args:
            if self.client.remote:
                import httpx
                console.print(httpx.post(f"{self.client.base_url}/api/rag/ingest", json={"path": args[0]}, timeout=120).json())
            else:
                rt = self.client._local
                import os as _os
                console.print(rt.rag.ingest_directory(args[0]) if _os.path.isdir(args[0]) else rt.rag.ingest_file(args[0]))
            return True
        if cmd == "/term":
            rt = self.client._local
            if rt is None:
                console.print("[yellow]Terminal mgmt needs local runtime; use prime-agent term run.[/yellow]")
                return True
            terms = rt.terminals.list()
            t = terms[0] if terms else rt.terminals.create(cwd=self.cwd)
            if args:
                res = rt.terminals.run(t.term_id, " ".join(args))
                console.print(Panel((res.get("stdout") or "")[-3000] + ("\n[stderr]\n" + res.get("stderr", "")[-1000] if res.get("stderr") else ""),
                                      title=f"exit={res.get('exit_code')} {res.get('duration_s')}s"))
            else:
                console.print(f"terminal {t.term_id} ({t.name}) — type /term <command>")
            return True
        if cmd == "/attach" and args:
            self.attachments.append(args[0])
            console.print(f"[cyan]Attached:[/cyan] {args[0]} (will be prepended as file context)")
            return True
        if cmd == "/todo" and args:
            if self.ensure_session():
                if self.client.remote:
                    import httpx
                    console.print(httpx.post(f"{self.client.base_url}/api/sessions/{self.session_id}/todos",
                                             json={"title": " ".join(args)}, timeout=15).json())
                else:
                    tid = self.client._local.sessions.upsert_todo(self.session_id, " ".join(args))
                    console.print(f"[green]todo:[/green] {tid}")
            return True
        if cmd == "/compact":
            if self.ensure_session():
                if self.client.remote:
                    import httpx
                    console.print(httpx.post(f"{self.client.base_url}/api/sessions/{self.session_id}/compact", timeout=30).json())
                else:
                    console.print({"ok": self.client._local.sessions.compact(self.session_id)})
            return True
        if cmd == "/stop":
            if self.session_id:
                console.print(self.client.interrupt(self.session_id))
            return True
        if cmd == "/export":
            if self.ensure_session():
                if self.client.remote:
                    import httpx
                    d = httpx.get(f"{self.client.base_url}/api/sessions/{self.session_id}/export", timeout=15).json()
                    console.print(Markdown(d.get("export", "")[:5000]))
                else:
                    console.print(Markdown((self.client._local.sessions.export(self.session_id) or "")[:5000]))
            return True
        if cmd == "/image" and args:
            console.print("[yellow]Image runs through the agent loop — send as chat, e.g. 'generate an image of ...'. Direct: prime-agent run.[/yellow]")
            return True
        console.print(f"[yellow]Unknown command {cmd}. /help for list.[/yellow]")
        return True

    def run(self) -> None:
        console.print(Panel("[bold]PRIME AGENT workbench[/bold] — sessions-first • PLAN/BUILD/AUTO • /help • /palette",
                            border_style="cyan"))
        self.ensure_session()
        self.show_sessions()
        while True:
            try:
                line = Prompt.ask(f"[bold cyan]prime[{self.session_id or '-'}][/bold cyan]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Bye. Sessions persist — resume with /sessions + /switch.[/yellow]")
                break
            if not line:
                continue
            if line.startswith("/"):
                if not self.handle_slash(line):
                    break
                continue
            # chat: prepend attachments as file context
            prompt = line
            for a in self.attachments:
                try:
                    txt = Path(a).read_text(encoding="utf-8", errors="replace")[:6000]
                    prompt = f"@{a}:\n```\n{txt}\n```\n\n{prompt}"
                except Exception as e:
                    console.print(f"[red]attach failed {a}: {e}[/red]")
            self.attachments.clear()
            if not self.ensure_session():
                console.print("[red]No session available.[/red]")
                continue
            console.print("[dim]agent running… (long tasks: detach with Ctrl+C in daemon mode; state persists)[/dim]")
            try:
                res = self.client.run_task(self.session_id, prompt)
            except KeyboardInterrupt:
                self.client.interrupt(self.session_id)
                console.print("[yellow]Interrupted — state persisted.[/yellow]")
                continue
            if res.get("ok"):
                console.print(Panel(Markdown(res.get("response", "")[:6000]), title="agent", border_style="green"))
                if res.get("verification"):
                    console.print(f"[dim]verification: {res['verification']}[/dim]")
            else:
                console.print(Panel(f"WHAT FAILED: agent turn\nWHY: {res.get('reason','unknown')}\nSTATE: session persisted\nNEXT: refine prompt or /compact, then retry",
                                    title="error", border_style="red"))


def main(daemon: str = "", cwd: str = ".") -> None:
    import os as _os
    client = PrimeClient(base_url=daemon or _os.environ.get("PRIME_DAEMON", ""))
    WorkbenchTUI(client, cwd=cwd or ".").run()


if __name__ == "__main__":
    main()
