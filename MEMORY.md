# Multi-Tier Memory System

Prime Agent implements a persistent, structured, multi-tier memory architecture that maintains context across long-running tasks, subagent delegations, and process restarts.

---

## 1. Memory Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Working Memory (Ephemeral, In-Process)                  │
│    - Current active prompt, scratchpad, step history        │
│    - REPL local variables and execution state               │
├─────────────────────────────────────────────────────────────┤
│ 2. Episodic Memory (Session-Scoped, Append-Only)           │
│    - Execution logs, subagent message exchanges             │
│    - JSON transcripts under data/sessions/<session_id>/     │
├─────────────────────────────────────────────────────────────┤
│ 3. Semantic Memory (Global, Hybrid Search)                  │
│    - Embedded technical documentation and code knowledge    │
│    - Persisted in data/indexes/rag_index.json               │
├─────────────────────────────────────────────────────────────┤
│ 4. Long-Term Goal Store (Durable State)                     │
│    - Persistent objectives, milestones, completion status   │
│    - Stored in data/goals.json                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Component Specifications (`services/agent/memory.py`)

### 2.1 Working Memory (`WorkingMemory`)
- Maintains short-term conversation context, user commands, and intermediate tool responses.
- Enforces token budgeting: automatically compacts or summarizes older intermediate scratchpad entries when approaching the context window limit (4096 tokens).

### 2.2 Episodic Memory (`EpisodicMemory`)
- Captures discrete execution episodes consisting of:
  - Task input
  - Plan / decomposition
  - Tool invocations and results
  - Verification reports
  - Created artifact paths
- Serialized to `data/sessions/<session_id>/transcript.json` for replay and post-mortem debugging.

### 2.3 Long-Term Goals (`GoalTracker`)
- Enables autonomous pursuit of multi-day or continuous goals.
- Goals are tracked in `data/goals.json` with attributes:
  - `goal_id`: Unique identifier (UUID4)
  - `title`: Short objective summary
  - `description`: Detailed specification and acceptance criteria
  - `milestones`: Ordered list of sub-goals with individual completion flags
  - `status`: `PENDING`, `IN_PROGRESS`, `BLOCKED`, `COMPLETED`
  - `created_at` & `updated_at`

---

## 3. Usage Examples

### Managing Goals via CLI:
```powershell
# Register a long-term goal
.\prime.ps1 goal "Continuously benchmark LLM latency and update optimal profile"

# View status
.\prime.ps1 status
```

### Python API:
```python
from services.agent.memory import AgentMemorySystem

memory = AgentMemorySystem()

# Register a goal
goal = memory.create_goal(
    title="Build Local RAG Index",
    description="Index all technical documents in the docs directory"
)

# Record an episodic step
memory.record_episode(
    session_id="session_test",
    step_type="TOOL_EXECUTION",
    payload={"tool": "rag_search", "result_count": 3}
)

# Retrieve recent episodes
recent = memory.get_recent_episodes(limit=5)
```
