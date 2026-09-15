# Prime Agent V3

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Local-first autonomous agent workbench** — RLM runtime, subagents, RAG, MCP, vision, image
generation/editing, self-healing, and a session-first workbench UI (TUI + CLI + daemon API sharing one core).

No cloud required. No chat gimmicks: every subsystem below is backed by the test or diagnostic named next to it.

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

The installer downloads the source archive, creates `.venv`, runs `pip install .`,
fetches GGUF models (SHA256-verified, ~7.5 GB) + llama.cpp runtimes, adds `prime-agent` to PATH,
and runs `prime-agent doctor`. Options:

| Env / flag | Effect |
|---|---|
| `-SkipModels` / `SKIP_MODELS=1` | skip ~7.5 GB model download |
| `-SkipLlamaCpp` / `SKIP_LLAMACPP=1` | skip llama.cpp runtime download |
| `-InstallDir X` / `INSTALL_DIR=X` | custom target directory |

Manual install instead:

```powershell
git clone https://github.com/timfromhcs/prime-agent.git
cd prime-agent
.\bootstrap.ps1
.\install.ps1
```

---

## Requirements (honest)

| | Windows | Linux |
|---|---|---|
| OS / Python | Windows 11, Python 3.12+ | any distro, Python 3.12+ |
| RAM | 16 GB recommended | 16 GB recommended |
| Disk | ~10 GB free (models + venv) | ~10 GB free |
| GPU | optional Vulkan (AMD/NVIDIA auto-detect) | CPU build; CUDA/Vulkan = manual llama.cpp install |

---

## Use

```powershell
prime-agent tui                 # session-first workbench (PLAN / BUILD / AUTO)
prime-agent serve --port 8000   # daemon HTTP+SSE API; TUI attaches via --daemon
prime-agent session new "Title" # sessions: list / fork / archive / compact / export
prime-agent ask <session> "..." # one bounded task in a session
prime-agent run "..."           # headless single task
prime-agent doctor               # full diagnostics (hashes, runtimes, kernel, RAG, MCP)
prime-agent benchmark            # real tok/s + RAG latency report
```

TUI slash commands: `/plan /build /auto /agents /context /git /diff /term /rag /ingest /mcp /models /doctor /todo /compact /export /help`.

---

## Verification status (evidence, not claims)

| Subsystem | Status | Evidence |
|---|---|---|
| RLM persistent kernel | ✅ verified | `tests/test_rlm_kernel.py` (42 → 84 across cells) |
| MCP (6 tools) | ✅ verified | `tests/test_mcp.py` |
| RAG hybrid + rerank | ✅ verified | `tests/test_rag*.py` |
| Sessions / permissions / modes / daemon API / terminals | ✅ verified | `tests/test_v3_workbench.py` (6 tests) |
| Models on disk (SHA256) | ✅ verified | `prime-agent doctor`, `config/models.json` |
| Full suite | ✅ 24 passed | `pytest tests/` |
| BUILD/AUTO with live LLM | ⚠️ needs `llama-server` running | PLAN-path tested; LLM loop is real code, not mocked |
| Linux installer | ⚠️ untested on real Linux | script is straightforward; report issues |
| Desktop app / cloud build | ❌ not included | out of scope for V3 |

---

## Architecture

One core, three clients: **TUI** (`tui/`) + **CLI** (`cli.py`) + **daemon API** (`services/api/`)
all call `PrimeRuntime` (`services/runtime/core.py`). Details:

- `ARCHITECTURE.md` · `RLM.md` · `SUBAGENTS.md` · `RAG.md` · `MCP.md` · `MODELS.md`
- `VISION.md` · `IMAGE_GENERATION.md` · `IMAGE_EDITING.md` · `MEMORY.md`
- `AUTONOMY.md` · `OPTIMIZATION.md` · `SECURITY.md` · `TROUBLESHOOTING.md` · `UI.md`

---

## Security notes

- Never commit tokens or `.env` files — the permission engine (`services/permissions/engine.py`)
  treats `*.env *credentials* *secret* *.pem` as approval-gated by default.
- Large binaries (`.gguf`, `.safetensors`, llama.cpp `.exe`/`.dll`, `.venv`) are git-ignored
  on purpose and re-fetched with hash checks by `scripts/fetch_binaries.py`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
