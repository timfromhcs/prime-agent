"""Multiline input engine for the hcscoder REPL (stdlib only, no prompt_toolkit).

Features:
- Backslash continuation: line ending in \\ joins with the next line.
- Bracket/quote-aware continuation: unbalanced (), [], {} or an open
  triple-quote keeps reading with a `... ` prompt.
- `/paste` mode (handled by the REPL): reads until a single `.` line.
- Headless-friendly: works with piped stdin; EOFError -> None.
- Testable: pass `source` (list/iterator of lines) instead of real stdin.
"""

from __future__ import annotations

from typing import Iterable, Iterator, List, Optional


def _balance_state(text: str) -> tuple:
    """Scan text, return (depth, in_single, in_double, in_triple)."""
    depth = 0
    in_s = False
    in_d = False
    in_t: Optional[str] = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_t:
            if text.startswith(in_t, i):
                in_t = None
                i += 3
                continue
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c == "'" and text.startswith("'''", i):
            in_t = "'''"
            i += 3
            continue
        if c == '"' and text.startswith('"""', i):
            in_t = '"""'
            i += 3
            continue
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            in_d = not in_d
        elif not in_s and not in_d:
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(0, depth - 1)
        i += 1
    return depth, in_s, in_d, in_t


def needs_continuation(buf: str) -> bool:
    """True if the buffer wants more lines. Pure + tested."""
    lines = buf.split("\n")
    if lines and lines[-1].rstrip().endswith("\\"):
        return True
    depth, in_s, in_d, in_t = _balance_state(buf)
    return depth > 0 or in_s or in_d or in_t is not None


def join_continuation(lines: List[str]) -> str:
    """Join continued lines: a trailing backslash is a join marker (dropped,
    lines stay separated by newline). Pure + tested."""
    out: List[str] = []
    for ln in lines:
        stripped = ln.rstrip()
        if stripped.endswith("\\") and not ln.strip().startswith("/"):
            out.append(stripped[:-1])
        else:
            out.append(ln)
    return "\n".join(out)


def read_multiline(prompt: str = "hcscoder> ",
                   cont_prompt: str = "... ",
                   source: Optional[Iterable[str]] = None) -> Optional[str]:
    """Read (possibly multi-line) input. Returns None on EOF/interrupt-abort.

    Raises KeyboardInterrupt to the caller for Ctrl+C handling.
    """
    it: Optional[Iterator[str]] = iter(source) if source is not None else None

    def _read(p: str) -> Optional[str]:
        if it is not None:
            try:
                return next(it)
            except StopIteration:
                return None
        try:
            return input(p)
        except EOFError:
            return None

    first = _read(prompt)
    if first is None:
        return None
    lines = [first]
    while needs_continuation("\n".join(lines)):
        nxt = _read(cont_prompt)
        if nxt is None:
            break
        lines.append(nxt)
    return join_continuation(lines)


def read_paste(source: Optional[Iterable[str]] = None) -> Optional[str]:
    """Read lines until a single `.` line (paste mode). None on EOF with no lines."""
    it: Optional[Iterator[str]] = iter(source) if source is not None else None
    collected: List[str] = []
    first = True
    while True:
        if it is not None:
            try:
                line = next(it)
            except StopIteration:
                line = None
        else:
            try:
                line = input("... " if not first else "paste (end with . on its own line): ")
            except EOFError:
                line = None
        first = False
        if line is None:
            return "\n".join(collected) if collected else None
        if line.strip() == ".":
            return "\n".join(collected)
        collected.append(line)
