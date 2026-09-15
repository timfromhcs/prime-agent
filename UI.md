# Prime Agent Workbench UI (V3)

Session-first developer workbench. The UI is a **client** of `PrimeRuntime`
(`services/runtime/core.py`) — the same core the CLI and daemon API use.
No agent logic is duplicated in the UI layer.

## Entry points

```powershell
.\prime.ps1 tui                                  # local runtime
.\prime.ps1 tui --daemon http://127.0.0.1:8000   # attached to daemon
.\prime.ps1 serve --port 8000                    # daemon HTTP+SSE API
```

## Layout (Rich TUI, `tui/app.py`)

- Header: session id, PLAN/BUILD/AUTO mode, message/token estimates (real usage counters).
- Sessions table, chat transcript (markdown), context panel (mode, todos, tool calls, models).
- Bottom: prompt loop with slash commands + `@file` attach (file text prepended, capped at 6k chars).

## Modes

- **PLAN** — read-only: RAG evidence summary, no writes (enforced in `PrimeRuntime.run_task`).
- **BUILD** — one bounded RLM turn (default 5 steps) + verification + git files-changed refresh.
- **AUTO** — bounded by `AutoBudget` (turns/tools/subagents/seconds); halts with reason.

## Supporting services

| Concern | Module | Notes |
|---|---|---|
| Sessions | `services/session/manager.py` | JSON-persisted, fork/compact/export, survives restart |
| Permissions | `services/permissions/engine.py` | allow/ask/deny, deny-wins, sensitive-path escalation, session allows |
| Diff/review | `services/diff/review.py` | git status/changed/diff/revert (safe: never deletes untracked) |
| Terminals | `services/terminal/sessions.py` | real PowerShell subprocesses, exit/duration logs, persisted metadata |
| Daemon API | `services/api/server.py` | FastAPI + SSE `/api/events/stream`, polling fallback |
| API client | `services/api/client.py` | remote (httpx) or in-process fallback — same core path |

## Slash commands

`/help /new /sessions /switch /fork /archive /delete /export /plan /build /auto
/goal /todo /compact /agents /spawn /context /git /diff /revert /term /terms
/rag /ingest /mcp /models /doctor /palette /attach /image /stop /quit`

## Verification

`tests/test_v3_workbench.py` (6 tests) + full suite `24 passed`.
No mock data: token counts are estimated from real message lengths and labeled as estimates.
