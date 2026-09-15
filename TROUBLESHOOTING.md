# Troubleshooting & Operational Runbook

This guide covers common runtime issues, error diagnostics, and recovery procedures for the Prime Agent Local RLM Platform.

---

## 1. Quick Health Check

If any component behaves unexpectedly, first execute the diagnostics utility:
```powershell
.\doctor.ps1
```
This inspects OS health, memory availability, binary paths, model hashes, REPL execution, RAG indexes, and registered MCP tools.

---

## 2. Common Issues & Solutions

### 2.1 Port Already in Use (e.g. `127.0.0.1:8080`)
**Symptom**: `OSError: [Errno 10048] Only one usage of each socket address is normally permitted`.

**Cause**: A previous `llama-server.exe` instance or lingering background test did not release its socket immediately.

**Solution**:
1. Run the stop script to terminate all background services:
   ```powershell
   .\stop.ps1
   ```
2. Or manually force termination of lingering `llama-server` instances in PowerShell:
   ```powershell
   Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
   ```
3. Note: `services/llm/model_manager.py` includes automatic port reclamation (`free_port()`) which automatically terminates stale processes holding the target port.

---

### 2.2 Vulkan Initialization Error (`vkCreateInstance failed`)
**Symptom**: `llama-server.exe` crashes immediately on launch with Vulkan initialization errors.

**Cause**: Missing Vulkan runtime DLL or outdated AMD Adrenalin graphics driver.

**Solution**:
1. Ensure the AMD Adrenalin driver is up to date for the AMD Radeon 680M iGPU.
2. Verify `vulkan-1.dll` exists in `C:\Windows\System32\`.
3. To temporarily fallback to the high-performance CPU backend:
   Edit `config/server.json` or `config/optimal-profile.json` and set `"backend": "cpu"`.

---

### 2.3 Shared VRAM / Memory Pressure (OOM)
**Symptom**: Process killed with exit code `3221225477` (Access Violation) or system paging lag.

**Cause**: Specifying a context window larger than available shared memory (e.g., `-c 32768` with speculative draft models).

**Solution**:
1. Set `"context_size": 4096` or `2048` in `config/models.json` and `config/server.json`.
2. Run `.\optimize.ps1` to automatically clamp context sizes and thread counts according to available physical RAM.

---

### 2.4 Multimodal Projector Mismatch
**Symptom**: `llama-server.exe` errors with `clip_model_load: failed to load vision model`.

**Cause**: Using a vision projector (`mmproj`) compiled for a different vision architecture.

**Solution**:
Ensure `models/vision/mmproj-Qwen2-VL-2B-Instruct-f16.gguf` is paired exclusively with `models/vision/Qwen2-VL-2B-Instruct-Q4_K_M.gguf`. Do not pair the projector with standard non-vision LLMs.

---

### 2.5 REPL Syntax or Import Errors
**Symptom**: Subagent or REPL returns syntax errors or missing package warnings.

**Cause**: Execution in an isolated namespace without previously required imports.

**Solution**:
The bounded self-healing supervisor (`services/agent/self_healing.py`) automatically intercepts tracebacks, inspects AST nodes, and applies targeted fixes. If a session enters an irrecoverable state, use snapshot rollback:
```python
harness.rollback_to("last_known_good_snapshot")
```

---

## 3. Graceful Reset & State Clearing

To reset temporary session caches without deleting models or indexes:
```powershell
# Clean session scratchpads
Remove-Item -Path "data/sessions/*" -Recurse -Force -ErrorAction SilentlyContinue

# Restart background daemon
.\start.ps1
```
