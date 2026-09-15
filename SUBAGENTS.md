# Subagent Orchestration & Native Roles

Prime Agent implements a bounded recursive subagent architecture designed for specialized task division, deep research, sandboxed coding, visual inspection, and automated self-healing.

---

## 1. Multi-Agent Design Principles

1. **Role Specialization**: Subagents operate under narrow, well-defined system prompts and tool subsets tailored to their domain.
2. **Bounded Recursion**: Subagents may spawn child subagents up to a hard ceiling of `max_depth = 3`, preventing runaway recursion.
3. **Workspace Isolation**: Each subagent executes inside an isolated workspace directory (`state/subagents/<subagent_id>/`) with its own `task_spec.json`, dedicated REPL session, and output `transcript.json`.
4. **Asynchronous Execution & Collection**: Subagents execute their prompts asynchronously, and parents can collect progress and findings via `rlm.collect(subagent_id)`.
5. **Observable Message Bus**: Inter-agent communication is persisted to `state/subagents/messages.jsonl` with structured sender/recipient metadata.

---

## 2. The 9 Native Subagent Roles

| Role | Name | Primary Capabilities | Allowed Tools |
| :--- | :--- | :--- | :--- |
| **01** | `LeadArchitect` | Decomposes complex goals into multi-agent dependency graphs | `agent_delegate`, `mcp_read`, `rag_search` |
| **02** | `Coder` | Writes, edits, and tests code; runs unit tests in REPL | `rlm_python`, `mcp_write`, `mcp_bash`, `mcp_read` |
| **03** | `Researcher` | Gathers context from RAG, documents, and codebases | `rag_search`, `rag_ingest`, `mcp_read` |
| **04** | `VisionAnalyst` | Inspects images, runs OCR on schematics and documents | `vision_ocr`, `vision_describe`, `image_qa` |
| **05** | `CreativeDirector` | Directs image generation and multi-step image editing | `image_generate`, `image_edit`, `image_qa` |
| **06** | `DevOpsEngineer` | Manages environment, runtime scripts, dependencies | `mcp_bash`, `mcp_read`, `mcp_write`, `runtime_check` |
| **07** | `QAEngineer` | Executes test suites, computes coverage, checks regressions | `rlm_python`, `mcp_bash`, `mcp_read` |
| **08** | `SecurityAuditor` | Audits code for vulnerabilities, path traversal, injection | `mcp_read`, `rag_search`, `static_analysis` |
| **09** | `SelfHealingAgent` | Diagnoses runtime errors and applies targeted repairs | `rlm_python`, `mcp_write`, `harness_rollback` |

---

## 3. Subagent Lifecycle & Execution (`services/subagents/manager.py`)

- **`spawn(prompt, name=None, role="research", parent_id=None)`**:
  Validates recursion depth (`depth <= 3`), creates `state/subagents/<id>/task_spec.json`, initializes the handle, and registers the subagent.
- **`execute_subagent(subagent_id, kernel_manager, llm_client, router)`**:
  Runs the subagent in its isolated workspace, boots a dedicated REPL session, evaluates code blocks, records findings, and updates state to `COMPLETED`.
- **`collect(subagent_id=None)`**:
  Returns structured dictionary with `subagent_id`, `state`, `settled` (bool), `findings`, `artifacts`, and `duration_seconds`.
- **`send_message(sender_id, recipient_id, content)`**:
  Transmits an observable message logged to `messages.jsonl`.
