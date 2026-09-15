# Security Architecture & Guardrails

Prime Agent is designed with local-first security boundaries to prevent unauthorized code execution, system corruption, prompt injection, and host compromise.

---

## 1. Threat Model & Defense In Depth

```
Untrusted Input / LLM Outputs
              │
              ▼
   Prompt Injection Defenses
   ├── Strict schema validation
   └── Instruction/Data separation
              │
              ▼
   Security Policy Gate (services/mcp/policy.py)
   ├── Workspace Path Confinement
   └── Dangerous Command Blacklist
              │
              ▼
   Windows Job Object Sandbox (services/rlm/_winjob.py)
   ├── Hard memory quotas
   └── Complete process tree termination
              │
              ▼
   Audit Trail & Transaction Journal (data/sessions/)
```

---

## 2. Policy Enforcement & Path Confinement

The security policy gate (`services/mcp/policy.py`) strictly enforces boundary constraints:

### Allowed Directory Boundaries:
- Filesystem operations (`read_file`, `write_file`, `list_directory`) are restricted strictly to paths within `E:\HCS Chat`.
- Path traversal sequences (`../`, `..\`, symlink redirection outside workspace) are intercepted and rejected with an explicit security error.

### Blacklisted Commands:
The shell tool rejects attempts to run:
- System format or disk partition utilities (`format`, `diskpart`).
- Unbounded directory deletions on root or OS directories (`rmdir /s /q C:\`, `del /f /s /q C:\`).
- Registry modifications (`reg add`, `reg delete`).
- Binary downloads from unauthorized remote hosts.

---

## 3. Windows Job Object Process Sandboxing

To prevent child processes or REPL executions from spawning unmanageable process trees or leaking CPU cycles:
- Every execution session assigns the target process to a dedicated Windows Job Object (`kernel32.dll`).
- `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` is activated so that closing the job handle immediately terminates all associated child processes.
- Memory quotas per job prevent rogue allocations from triggering system-wide OOM freezes.

---

## 4. Audit Logging & State Provenance

- **MCP Audit Trail**: Every tool call (name, caller, arguments, result code) is logged to `data/sessions/mcp_audit.log`.
- **Artifact Integrity**: Generated and modified artifacts have SHA256 hashes computed immediately upon creation and stored in `data/artifacts/catalog.json`.
- **Episodic Sessions**: Every agent session saves full prompt transcripts, intermediate plans, and verification reports in `data/sessions/<id>/transcript.json`.
