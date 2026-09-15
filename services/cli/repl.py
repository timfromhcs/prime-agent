"""hcscoder interactive REPL - Claude-Code-class CLI UX, dependency-free (rich only).

Pure helpers (parse_slash, expand_file_refs, needs_approval) are unit-tested.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from services.cli.input import read_multiline, read_paste
from services.cli.ui import Renderer
from services.permissions.engine import PermissionEngine

BANNER = "[bold cyan]hcscoder[/bold cyan] [dim]v3 * local-first agent workbench[/dim]"


def app_version() -> str:
    try:
        import tomllib as _t
        return _t.load(open("pyproject.toml", "rb"))["project"]["version"]
    except Exception:
        return "?"


def primary_model() -> str:
    try:
        import json as _j
        cfg = _j.loads(Path("config/models.json").read_text(encoding="utf-8"))
        return cfg.get("primary", {}).get("name", "?")
    except Exception:
        return "?"

HELP = """[bold]Slash commands[/bold]
  /help              this help            /new [title]       new session
  /sessions          list sessions        /switch <id>       switch session
  /plan|/build|/auto switch mode          /diff              changed files + diff
  /review            approve/revert files /commit [-m msg]    safe git commit
  /models            model catalog        /doctor            diagnostics
  /compact           compact context      /export            markdown export
  /paste             multiline paste      /clear             clear screen
  /quit              exit
[dim]@path/to/file embeds file context
multiline: trailing \\ continues, unclosed brackets keep reading, /paste ends with `.`
Ctrl+C interrupts a run[/dim]"""

RISKY_PROMPT_PATTERNS = [
    r"rm\s+-rf\s+[/~]",
    r"git\s+push\s+--force",
    r"mkfs",
    r"del\s+/[fs]",
    r"format\s+[a-z]:",
    r"\.env",
]


def parse_slash(line: str) -> Tuple[str, List[str]]:
    """Split '/cmd arg1 arg2' -> ('cmd', ['arg1', 'arg2']). Pure + tested."""
    parts = line.strip().split()
    if not parts or not parts[0].startswith("/"):
        return ("", [])
    return (parts[0][1:].lower(), parts[1:])


def expand_file_refs(text: str, cwd: str = ".") -> Tuple[str, List[str]]:
    """Replace @path tokens with capped file contents. Returns (new_text, embedded)."""
    embedded: List[str] = []
    base = Path(cwd)

    def _sub(m: re.Match) -> str:
        raw = m.group(1)
        p = (base / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")[:6000]
        except Exception:
            return m.group(0)  # leave untouched + warn caller
        embedded.append(str(p))
        return f"\n--- @{raw} ---\n```\n{content}\n```\n"

    out = re.sub(r"@([\w\-./\\:]+)", _sub, text)
    return out, embedded


def needs_approval(prompt: str) -> Optional[str]:
    """Return matched risky pattern or None. Pure + tested."""
    for pat in RISKY_PROMPT_PATTERNS:
        if re.search(pat, prompt, re.IGNORECASE):
            return pat
    return None


class HCSRepl:
    def __init__(self, runtime, cwd: str = ".", file_base: str = ""):
        self.rt = runtime
        self.cwd = cwd
        self.file_base = file_base or cwd  # @file refs resolve here (invocation dir)
        self.console = Console()
        self.ui = Renderer(self.console)
        self.model = primary_model()
        self.version = app_version()
        self.session_id: Optional[str] = None
        self.perms = PermissionEngine()

    # -- session --
    def ensure_session(self) -> bool:
        if self.session_id and self.rt.sessions.get(self.session_id):
            return True
        existing = self.rt.sessions.list()
        if existing:
            self.session_id = existing[0].session_id
            return True
        s = self.rt.sessions.create(title="hcscoder session", cwd=self.cwd)
        self.session_id = s.session_id
        return True

    def footer(self) -> str:
        s = self.rt.sessions.get(self.session_id) if self.session_id else None
        if not s:
            return "[dim]no session[/dim]"
        return (f"[dim]session {s.session_id} * mode [cyan]{s.mode}[/cyan] * "
                f"model {self.model} * msgs {len(s.messages)} * "
                f"tools {s.usage.get('tool_calls', 0)} * "
                f"tok~{s.usage.get('tokens_est', 0)}[/dim]")

    # -- approval gate (UX layer; MCP policy still enforces underneath) --
    def approval_gate(self, prompt: str) -> bool:
        pat = needs_approval(prompt)
        if not pat:
            return True
        dec = self.perms.decide("shell_exec", prompt[:200], self.session_id or "")
        card = self.perms.approval_card("shell_exec", prompt[:200],
                                        f"matched {pat} ({dec['reason']})",
                                        dec["risk"], prompt[:200])
        self.ui.approval(card["action"], card["reason"], card["risk"],
                         card.get("proposed_command", ""))
        if dec["decision"] == "deny":
            self.console.print("[red]Denied by policy.[/red]")
            return False
        choice = Prompt.ask("Allow?", choices=["once", "session", "deny"], default="deny")
        if choice == "deny":
            return False
        if choice == "session" and self.session_id:
            self.perms.allow_session_pattern(self.session_id, "*")
        return True

    # -- streaming run with live UX (spinner until first output, then Live) --
    def run_streaming(self, prompt: str) -> None:
        if not self.ensure_session():
            self.console.print("[red]No session available.[/red]")
            return
        if not self.approval_gate(prompt):
            return
        stream = self.ui.new_stream()
        live_on = False
        spin = self.ui.thinking("Agent working...")
        status = spin.__enter__()
        t_start = time.time()

        def _first_output():
            nonlocal live_on
            if not live_on:
                live_on = True
                status.stop()
                stream.start()

        async def _drain():
            async for ev in self.rt.run_task_stream(self.session_id, prompt):
                t = ev.get("type")
                if t == "status":
                    _first_output()
                    stream.pause()
                    self.ui.status_line(ev.get("text", ""))
                    stream.resume()
                elif t == "delta":
                    _first_output()
                    stream.append(ev.get("text", ""))
                elif t == "tool":
                    _first_output()
                    stream.pause()
                    self.console.print()
                    self.ui.tool_card("tool", ev.get("text", ""), state="running",
                                      elapsed_s=time.time() - t_start)
                    stream.resume()
                elif t == "done":
                    _first_output()
                    full = stream.finish()
                    self.console.print()
                    self.ui.final(ev.get("response") or full, ok=True,
                                  elapsed=str(ev.get("elapsed_s", "?")),
                                  verification=ev.get("verification"),
                                  artifacts=ev.get("artifacts"))
                elif t == "error":
                    stream.finish()
                    self.ui.error_card(ev.get("reason", "unknown"))

        try:
            asyncio.run(_drain())
        except KeyboardInterrupt:
            self.rt.interrupt(self.session_id)
            self.console.print("\n[yellow]Interrupted - state persisted.[/yellow]")
        finally:
            try:
                status.stop()
            except Exception:
                pass
            stream.finish()
        self.console.print(self.footer())

    # -- review / commit --
    def cmd_review(self) -> None:
        from services.diff.review import changed_files, file_diff, revert_file
        s = self.rt.sessions.get(self.session_id) if self.session_id else None
        cwd = s.cwd if s else self.cwd
        files = changed_files(cwd)
        if not files:
            self.console.print("[green]Clean - no changes.[/green]")
            return
        for f in files:
            d = file_diff(cwd, f["path"]).get("diff", "")[:3000]
            self.console.print(Panel(d or "(binary/empty diff)", title=f"{f['status']} {f['path']}"))
            act = Prompt.ask("keep / revert / stop?", choices=["keep", "revert", "stop"], default="keep")
            if act == "stop":
                break
            if act == "revert":
                r = revert_file(cwd, f["path"])
                self.console.print(str(r))

    def cmd_commit(self, message: str = "") -> None:
        s = self.rt.sessions.get(self.session_id) if self.session_id else None
        cwd = s.cwd if s else self.cwd
        st = subprocess.run(["git", "status", "--short"], cwd=cwd, capture_output=True, text=True)
        if st.returncode != 0:
            self.console.print("[red]Not a git repo.[/red]")
            return
        self.console.print(Panel(st.stdout or "(clean)", title="git status"))
        if not st.stdout.strip():
            return
        msg = message or Prompt.ask("Commit message")
        if not msg.strip():
            return
        ident = subprocess.run(["git", "config", "user.name"], cwd=cwd,
                               capture_output=True, text=True)
        if ident.returncode != 0 or not ident.stdout.strip():
            self.console.print("[yellow]No git identity in this repo.[/yellow]")
            name = Prompt.ask("Your name for commits", default="hcscoder")
            email = Prompt.ask("Your email for commits", default="hcscoder@localhost")
            subprocess.run(["git", "config", "user.name", name], cwd=cwd)
            subprocess.run(["git", "config", "user.email", email], cwd=cwd)
        add = subprocess.run(["git", "add", "-A"], cwd=cwd, capture_output=True, text=True)
        if add.returncode != 0:
            self.console.print(f"[red]git add failed: {add.stderr}[/red]")
            return
        cm = subprocess.run(["git", "commit", "-m", msg], cwd=cwd, capture_output=True, text=True)
        self.console.print(cm.stdout[-2000:] or cm.stderr[-2000:])

    # -- slash --
    def handle_slash(self, cmd: str, args: List[str]) -> bool:
        """Return False to quit."""
        if cmd in ("quit", "exit", "q"):
            return False
        if cmd == "help":
            self.console.print(Panel(HELP, border_style="cyan"))
        elif cmd == "clear":
            self.console.clear()
        elif cmd == "new":
            s = self.rt.sessions.create(title=" ".join(args) or "hcscoder session", cwd=self.cwd)
            self.session_id = s.session_id
            self.console.print(f"[green]New session:[/green] {s.session_id}")
        elif cmd == "sessions":
            for x in self.rt.sessions.list()[:20]:
                mark = "*" if x.session_id == self.session_id else " "
                self.console.print(f"{mark} {x.session_id}  {x.title[:45]}  [{x.mode}] {x.status}")
        elif cmd == "switch" and args:
            self.session_id = args[0]
        elif cmd in ("plan", "build", "auto"):
            if self.ensure_session():
                self.console.print(self.rt.modes.set_mode(self.session_id, cmd.upper()))
        elif cmd == "diff":
            self._cmd_diff()
        elif cmd == "review":
            if self.ensure_session():
                self.cmd_review()
        elif cmd == "commit":
            if self.ensure_session():
                msg = " ".join(args).lstrip("-m ").strip() if args and args[0] == "-m" else " ".join(args)
                self.cmd_commit(msg)
        elif cmd == "models":
            import json as _j
            cfg = _j.loads(Path("config/models.json").read_text(encoding="utf-8"))
            for role, m in cfg.items():
                p = m.get("path", "")
                ok = Path(p).exists() if p else True
                self.console.print(f"{'ok' if ok else 'FAIL'} {role}: {m.get('name')} [{m.get('quantization', '')}]")
        elif cmd == "doctor":
            from rich.table import Table as _T
            rows = [("vulkan", Path("runtime/llama.cpp/vulkan/llama-server.exe").exists()),
                    ("cpu", Path("runtime/llama.cpp/cpu/llama-server.exe").exists())]
            t = _T(title="doctor")
            t.add_column("check")
            t.add_column("ok")
            for k, ok in rows:
                t.add_row(k, "OK" if ok else "FAIL")
            self.console.print(t)
        elif cmd == "compact":
            if self.ensure_session():
                self.console.print({"ok": self.rt.sessions.compact(self.session_id)})
        elif cmd == "export":
            if self.ensure_session():
                self.console.print(Markdown((self.rt.sessions.export(self.session_id) or "")[:4000]))
        else:
            self.console.print(f"[yellow]Unknown /{cmd} - /help[/yellow]")
        return True

    def _cmd_diff(self) -> None:
        from rich.syntax import Syntax as _S
        from services.diff.review import full_diff
        s = self.rt.sessions.get(self.session_id) if self.session_id else None
        self.console.print(_S(full_diff(s.cwd if s else self.cwd)[:15000] or "(no diff)", "diff"))

    def run(self) -> None:
        self.ui.banner(self.version, self.model, self.cwd)
        self.ensure_session()
        self.console.print(self.footer())
        while True:
            try:
                line = read_multiline("[bold cyan]hcscoder>[/bold cyan] ",
                                      console=self.console)
            except KeyboardInterrupt:
                self.console.print("\n[dim]Sessions persist - resume anytime. Bye.[/dim]")
                break
            if line is None:  # EOF (piped stdin exhausted)
                self.console.print("\n[dim]Sessions persist - resume anytime. Bye.[/dim]")
                break
            line = line.strip()
            if not line:
                continue
            if line.startswith("/"):
                cmd, args = parse_slash(line)
                if cmd == "paste":
                    pasted = read_paste()
                    if pasted is None or not pasted.strip():
                        continue
                    line = pasted.strip()
                else:
                    if not self.handle_slash(cmd, args):
                        break
                    continue
            prompt, embedded = expand_file_refs(line, self.file_base)
            for e in embedded:
                self.console.print(f"[dim]attached: {e}[/dim]")
            self.run_streaming(prompt)
