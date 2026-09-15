# Model Context Protocol (MCP) Integration

Prime Agent includes a complete, secure implementation of the Model Context Protocol (MCP) for tool discovery, client-server negotiation, sandboxed execution, and context delivery.

---

## 1. Architecture & Policy Sandbox

The MCP implementation is split into a secure server, an autonomous client, a tool registry, and an explicit security policy guard:

```
services/mcp/
├── __init__.py
├── client.py     # Autonomous MCP client for JSON-RPC tool invocation
├── policy.py     # Security policy gate enforcing sandbox boundaries
├── server.py     # Fast MCP server exposing local tools via JSON-RPC
└── tools.py      # Core tool registry (Filesystem, Shell, Python, Git, RAG)
```

### Security Policy Gate (`services/mcp/policy.py`)
To prevent unauthorized access, prompt injection, and host compromise, every tool call must pass through the `SecurityPolicy` gate:
- **Path Confinement**: All file read/write operations must resolve strictly inside the allowed workspace root (`E:\HCS Chat`). Path traversals (`../`, `..\`, absolute paths outside the workspace) are rejected immediately.
- **Dangerous Commands**: High-risk shell commands (e.g., `rmdir /s`, `format`, `del /f /s /q C:`, downloading executable binaries from external URLs) are blocked.
- **Audit Logging**: Every tool execution is recorded with a timestamp, caller identity, arguments, and return status in `data/sessions/mcp_audit.log`.

---

## 2. Registered MCP Tools

The `MCPToolRegistry` provides the following native tools (verified via
`hcscoder mcp` + `tests/test_mcp.py`):

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `read_file` | `path, start_line?, end_line?` | Reads file content inside the sandbox |
| `write_file` | `path, content` | Writes a file inside the sandbox (creates parents) |
| `list_dir` | `path` | Lists directory entries with sizes |
| `git_status` | — | Working-tree status of the project |
| `git_diff` | — | Uncommitted diff of the project |
| `shell_exec` | `command, timeout?=60` | Runs a shell command, captures exit/stdout/stderr |
| `web_fetch` | `url` | Fetch-only http(s) retrieval as title+text (capped, no JS, no search engine) |

---

## 3. Server Implementation (`services/mcp/server.py`)

The server implements the JSON-RPC 2.0 specification over standard I/O and HTTP:
- **`tools/list`**: Returns a JSON schema of all registered tools and their typed parameters.
- **`tools/call`**: Validates the incoming tool name and arguments against the schema, verifies permission via `policy.py`, executes the tool, and wraps the output in an MCP result packet.

### Example JSON-RPC Request:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "path": "config/models.json"
    }
  }
}
```

### Example JSON-RPC Response:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\n  \"primary\": {\n    \"name\": \"Qwen3-4B-Instruct\" ...\n  }\n}"
      }
    ],
    "isError": false
  }
}
```

---

## 4. MCP Client Integration (`services/mcp/client.py`)

The `MCPClient` class allows agents to dynamically query the available tools, parse parameter specifications, and execute operations seamlessly in code:

```python
import asyncio
from services.mcp.client import MCPClient

async def run_tool():
    client = MCPClient()
    result = await client.call_tool("read_file", {"path": "config/hardware.json"})
    print("Content:", result.get("content")[0]["text"])

asyncio.run(run_tool())
```
