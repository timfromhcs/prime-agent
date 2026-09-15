# hcscoder UI / UX (V3)

Two clients, one core. `PrimeRuntime` (`services/runtime/core.py`) owns all agent state;
the REPL (`hcscoder`, no args) and the TUI (`hcscoder tui`) only render it.

## Interactive REPL (primary)

```powershell
hcscoder                    # local runtime, streaming
```

- Live token streaming (`chat_stream` SSE with non-SSE fallback), tool status lines,
  final markdown panel with verification + artifacts + elapsed time.
- Footer after every turn: session, mode, message/tool/token counters (real usage counters).
- `/plan /build /auto /diff /review /commit /models /doctor /compact /export /sessions /help`
- `@path` embeds capped file context; risky prompts hit an inline approval
  (`once` / `session` /deny) backed by `PermissionEngine` (MCP policy enforces underneath).
- `Ctrl+C` interrupts; state persists; exit code 0 on `/quit`.
- All output is ASCII-safe (Windows cp1252 pipes verified).

## TUI (`hcscoder tui [--daemon URL]`)

Session table + transcript + context panel for daemon-attached or local use.

## Non-interactive (headless, fully tested)

```powershell
hcscoder run "..." --mode PLAN     # streaming one-shot
hcscoder review                    # keep/revert per file (piped stdin works)
hcscoder commit -m "msg"           # asks for git identity only if repo has none
hcscoder serve --port 8000         # HTTP+SSE API (/api/health, /api/events/stream)
hcscoder ask <session> "..."
hcscoder session new/list/fork/mode/compact/export/archive
hcscoder term new/run/list/rename/close
hcscoder perm decide/allow
hcscoder mcp | hcscoder models | hcscoder doctor
```

Headless proofs: `scripts/live_check.py` (live LLM loop, exit 0),
`scripts/stress_headless.py` (10 rounds, 0 failures), piped REPL/TUI smokes.

## Verification

`tests/test_hcscoder.py` (REPL helpers, SSE parser, lazy startup, entry points),
`tests/test_v3_workbench.py`, full suite green — see README table.
No mock data: token counts are labeled estimates from real message lengths.
