# hcscoder

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Local-first autonomous agent workbench.** RLM runtime with persistent Python kernel,
verified tool surface (shell/files/git/RAG/**fetch-only web**/subagents/skills),
hybrid RAG, MCP tools, **vision (local VLM)**, local image generation/editing with QA,
self-healing —
driven through an interactive streaming REPL, a TUI, a CLI, and a daemon HTTP+SSE API
that all share one backend core. No cloud required.

Every claim below names its evidence. Where something is untested or limited, it says so.

---

## Install (one line, no git clone)

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/timfromhcs/prime-agent/main/install.ps1 | iex
```

**Linux (bash):**

```bash
curl -fsSL https://raw.githubusercontent.com/timfromhcs/prime-agent/main/install.sh | bash
```

What the installer does: downloads the source archive (no clone), creates `.venv`,
runs `pip install .` (exposes `hcscoder`; `prime-agent` stays as alias), fetches GGUF
models SHA256-verified (~7.5 GB) + llama.cpp runtimes (Windows: CPU+Vulkan, Linux: CPU),
sets `PRIME_HOME` (resource anchor — the CLI works from any directory; without it,
the install is auto-detected via its own `.venv`), adds the binary
to PATH, runs `hcscoder doctor`.

| Flag | Effect |
|---|---|
| `-SkipModels` / `SKIP_MODELS=1` | skip model download |
| `-SkipLlamaCpp` / `SKIP_LLAMACPP=1` | skip llama.cpp download |
| `-InstallDir X` / `INSTALL_DIR=X` | custom directory |

Manual alternative: `git clone https://github.com/timfromhcs/prime-agent.git`,
then `.\bootstrap.ps1` + `.\install.ps1` (fetch scripts live in `scripts/`).

---

## Use

```powershell
hcscoder                      # interactive REPL: streaming tokens, tool cards, /help
hcscoder run "Migrate X"      # one-shot task, live output; --mode PLAN|BUILD|AUTO
hcscoder review               # diff review: keep/revert per file
hcscoder commit -m "msg"      # safe commit (status first, asks identity if missing)
hcscoder models               # local catalog with real installed/missing status
hcscoder tui                  # workbench TUI (or --daemon http://127.0.0.1:8000)
hcscoder serve --port 8000    # daemon API: /api/health, /api/sessions, /api/events/stream
hcscoder session new "Title"  # + list/fork/mode/compact/export/archive
hcscoder term new/run/list/rename/close   # real PowerShell sessions
hcscoder perm decide/allow    # allow/ask/deny engine
hcscoder mcp                  # 7 registered tools | hcscoder rag search "..."
hcscoder doctor               # full diagnostics | hcscoder benchmark | hcscoder optimize
```

REPL extras: `@path/to/file` embeds file context; **multiline input** (trailing `\`,
unclosed brackets, or `/paste` ending with `.`); risky prompts trigger inline approval
(`once`/`session`/`deny`); live token streaming with tool cards, spinner + elapsed,
banner/footer with model + usage; `Ctrl+C` interrupts with state persisted; PLAN mode is
enforced read-only; AUTO mode is bounded (turn/tool/subagent/time budgets).

---

## Verification status (evidence, not marketing)

| Subsystem | Status | Evidence |
|---|---|---|
| RLM persistent kernel | ✅ | `test_rlm_kernel.py` (42 → 84 across cells) |
| MCP (7 tools) | ✅ | `test_mcp.py` + `hcscoder mcp` (incl. `web_fetch`) |
| Agent tool surface (bridges + prompt honesty) | ✅ | `test_agent_surface.py`: all 14 ops route, prompt documents only real APIs |
| Subagents live (spawn → LLM → COMPLETED → collect) | ✅ | `scripts/live_subagents.py` exit 0 (fixed shared-process `chdir` bug on the way) |
| Vision live (VLM describes fixture correctly, 18 s load) | ✅ | `scripts/live_multimodal.py` — "blue square with red PRIME VISION text" |
| Diffusion live (gen + edit + QA PASS, CPU ~183 s) | ✅ | `scripts/live_multimodal.py` — artifacts `img_c6af4b92`/`img_ce9d0bd7` with SHA256 |
| RAG hybrid + rerank | ✅ | `test_rag*.py`; live p50 8 ms (`stress_headless.py`) |
| Sessions / permissions / modes / API / terminals | ✅ | `test_v3_workbench.py` |
| REPL / SSE parser / lazy startup / entry points | ✅ | `test_hcscoder.py` (8 tests) |
| llama.cpp tuning (FA on, KV q8_0, draft n-max 8) | ✅ | `test_llama_tuning.py`; flags on server exec line |
| Live LLM loop (server 3.2 s, 29 stream deltas, BUILD `RESULT:157`, FACT) | ✅ | `scripts/live_check.py` exit 0 |
| Long-horizon (scaffold calc → 6 asserts → repair → pytest green, phased, resuming) | ✅ | `scripts/live_long_task.py` → `LONG-HORIZON BUILD: PASS` (6 passed); loop hardened along the way (no-code nudge, truncation-tolerant fences, 2048 tok, error types) |
| Speculative A/B | ✅ measured, modest | 24.0 vs 22.6 tok/s decode (short output, single run; no acceptance counter in build 10977) |
| CLI startup | ✅ 0.2 s | lazy imports (was 9.8 s) |
| Headless stress (10 rounds parallel sessions/RAG/terminals) | ✅ 0 failures | `scripts/stress_headless.py` |
| Every CLI command headless incl. serve+health | ✅ | bug-loop 2026-09-15 (review/commit/REPL/TUI piped, exit 0) |
| Models on disk (SHA256) | ✅ | `hcscoder doctor` → ALL SUBSYSTEMS VERIFIED |
| Full suite | ✅ **45 passed** | `pytest tests/` |
| Linux installer | tested in WSL Ubuntu 22.04 | venv + full pip install + symlinks + `hcscoder --help` green; found+fixed `PYTHON_BIN` auto-detect bug; models/llama via documented skip flags |
| BUILD/AUTO long-horizon tasks | proven within budgets | phased scaffold→test→repair converges; ~1–2 min/step on local 4B |
| Desktop app | ❌ out of scope (by decision) | CLI UX is the product: streaming REPL, review/commit, approvals, hcscoder branding |

---

## Architecture (one core, four clients)

`services/runtime/core.py` (`PrimeRuntime`) owns task/goal/plan/execution/tools/subagents/memory.
REPL (`services/cli/`), TUI (`tui/`), CLI (`cli.py`), daemon API (`services/api/`) render it —
no logic duplicated. Docs: `ARCHITECTURE.md RLM.md SUBAGENTS.md RAG.md MCP.md MODELS.md
VISION.md IMAGE_GENERATION.md IMAGE_EDITING.md MEMORY.md AUTONOMY.md OPTIMIZATION.md
SECURITY.md TROUBLESHOOTING.md UI.md`.

Tuned for Ryzen 7 7735HS + Radeon 680M (Vulkan, unified memory): full offload, q8_0 KV,
flash-attn on, Qwen2.5-0.5B draft. See `OPTIMIZATION.md §9` for measured numbers.

## Security

- Secrets never committed (`.gitignore` + permission engine gates `*.env *credentials* *.pem`).
- Destructive patterns (`rm -rf /`, `push --force`) are deny-by-default; REPL re-confirms.
- Binaries re-fetched with hash checks (`scripts/fetch_binaries.py`), never stored in git.

## License

Apache-2.0 — see [LICENSE](LICENSE).
