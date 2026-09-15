"""Claude-class terminal UI primitives for hcscoder (rich only, ASCII-safe).

Renderer centralizes: banner, spinners, live streaming buffer, tool cards,
approval prompts, final panels, footers. Everything renders acceptably both
on a real terminal and with piped stdin/stdout (headless-tested).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.text import Text


class StreamBuffer:
    """Throttled live text buffer: appends deltas, refreshes a Live display.

    On finish, returns the full text for final markdown rendering.
    """

    def __init__(self, console: Console, refresh_per_second: int = 4):
        self.console = console
        self.parts: List[str] = []
        self.length = 0
        self._live = Live(Text(""), console=console, transient=True,
                          refresh_per_second=refresh_per_second)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._live.start()

    def append(self, delta: str) -> None:
        if not delta:
            return
        self.parts.append(delta)
        self.length += len(delta)
        if self._started:
            self._live.update(Text("".join(self.parts)[-2000:]))

    def pause(self) -> None:
        if self._started:
            self._live.stop()
            self._started = False

    def resume(self) -> None:
        self.start()

    def text(self) -> str:
        return "".join(self.parts)

    def finish(self) -> str:
        self.pause()
        return self.text()


class Renderer:
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    # -- chrome --
    def banner(self, version: str, model: str, cwd: str) -> None:
        self.console.print(Panel(
            f"[bold cyan]hcscoder[/bold cyan] [dim]v{version} * local-first agent workbench[/dim]\n"
            f"[dim]model {model} * cwd {cwd}[/dim]\n"
            f"[dim]/help * @file to attach * \\-continued or bracket-aware multiline * /paste * Ctrl+C interrupts[/dim]",
            border_style="cyan"))

    def footer(self, session_id: str, mode: str, model: str,
               msgs: int, tools: int, tokens: int) -> None:
        self.console.print(
            f"[dim]session {session_id} * mode [cyan]{mode}[/cyan] * model {model} * "
            f"msgs {msgs} * tools {tools} * tok~{tokens}[/dim]")

    # -- progress --
    @contextmanager
    def thinking(self, label: str = "Thinking...") -> Iterator[Status]:
        with self.console.status(f"[cyan]{label}[/cyan]", spinner="dots") as st:
            yield st

    def status_line(self, text: str) -> None:
        self.console.print(f"[dim]> {text}[/dim]")

    def tool_card(self, title: str, preview: str = "",
                  state: str = "running", elapsed_s: float = 0.0) -> None:
        mark = {"running": "[..]", "ok": "[ok]", "fail": "[!!]"}.get(state, "[..]")
        style = {"running": "dim", "ok": "green", "fail": "red"}.get(state, "dim")
        body = preview[:400] if preview else ""
        suffix = f" ({elapsed_s:.1f}s)" if elapsed_s else ""
        self.console.print(Panel(body or "(no preview)", title=f"{mark} {title}{suffix}",
                                 border_style=style))

    def approval(self, action: str, reason: str, risk: str,
                 proposed: str = "") -> None:
        lines = (f"[bold]Approval required[/bold] (risk: {risk})\n"
                 f"action: {action}\nreason: {reason}")
        if proposed:
            lines += f"\nproposed: {proposed[:300]}"
        self.console.print(Panel(lines, title="permissions", border_style="yellow"))

    def final(self, response: str, ok: bool, elapsed: str = "",
              verification: Optional[Dict] = None,
              artifacts: Optional[List[str]] = None) -> None:
        title = f"hcscoder ok {elapsed}s" if ok else "hcscoder"
        self.console.print(Panel(Markdown((response or "")[:6000]), title=title,
                                 border_style="green" if ok else "red"))
        if verification:
            self.console.print(f"[dim]verification: {verification}[/dim]")
        if artifacts:
            self.console.print(f"[dim]artifacts: {artifacts}[/dim]")

    def error_card(self, reason: str) -> None:
        hint = ""
        if "budget" in reason:
            hint = "\nNEXT: /budget to inspect, /budget reset to continue, /compact to trim history"
        else:
            hint = "\nNEXT: refine prompt or /compact, then retry"
        self.console.print(Panel(
            f"WHAT FAILED: agent turn\nWHY: {reason}\n"
            f"STATE: session persisted{hint}",
            title="error", border_style="red"))

    def new_stream(self) -> StreamBuffer:
        return StreamBuffer(self.console)
