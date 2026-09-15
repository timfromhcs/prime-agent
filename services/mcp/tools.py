"""Real tool implementations for Prime MCP.

Never mocks: runs actual filesystem, git, python execution, rag, and image services.
"""

from __future__ import annotations
import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.rlm.bash import bash
from services.mcp.policy import ToolSecurityPolicy


class MCPToolRegistry:
    """Manages real tool definitions and safe execution."""

    def __init__(self, policy: Optional[ToolSecurityPolicy] = None):
        self.policy = policy or ToolSecurityPolicy()
        self.tools: Dict[str, Any] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        # Filesystem tools
        self.register("list_dir", self._tool_list_dir, "List contents of a directory", {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path"}},
            "required": ["path"]
        })
        self.register("read_file", self._tool_read_file, "Read contents of a text file", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "start_line": {"type": "integer", "description": "Starting line (1-indexed)"},
                "end_line": {"type": "integer", "description": "Ending line (inclusive)"}
            },
            "required": ["path"]
        })
        self.register("write_file", self._tool_write_file, "Write contents to a file", {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Text content"}
            },
            "required": ["path", "content"]
        })

        # Git tools
        self.register("git_status", self._tool_git_status, "Get git status for the repository", {
            "type": "object", "properties": {}
        })
        self.register("git_diff", self._tool_git_diff, "Get git diff for uncommitted changes", {
            "type": "object", "properties": {}
        })

        # Shell tool
        self.register("shell_exec", self._tool_shell_exec, "Execute a shell command with timeout", {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command line to execute"},
                "timeout": {"type": "number", "description": "Timeout in seconds"}
            },
            "required": ["command"]
        })

    def register(self, name: str, fn: Any, description: str, schema: Dict[str, Any]):
        self.tools[name] = {
            "name": name,
            "fn": fn,
            "description": description,
            "inputSchema": schema
        }

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self.tools:
            return {"status": "error", "error": f"Tool '{tool_name}' not registered"}

        # Security gate
        denial = self.policy.validate_and_gate(tool_name, args)
        if denial:
            return {"status": "error", "error": denial}

        start_t = time.time()
        tool_entry = self.tools[tool_name]
        try:
            fn = tool_entry["fn"]
            if asyncio.iscoroutinefunction(fn):
                res = await fn(args)
            else:
                res = fn(args)

            duration = time.time() - start_t
            self.policy.log_execution(tool_name, args, "success", str(res), duration)
            return {"status": "ok", "result": res, "duration": duration}
        except Exception as exc:
            duration = time.time() - start_t
            self.policy.log_execution(tool_name, args, "error", str(exc), duration)
            return {"status": "error", "error": str(exc), "duration": duration}

    def _tool_list_dir(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        p = Path(args["path"])
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")
        items = []
        for child in p.iterdir():
            items.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None
            })
        return items

    def _tool_read_file(self, args: Dict[str, Any]) -> str:
        p = Path(args["path"])
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        start = max(1, args.get("start_line", 1)) - 1
        end = args.get("end_line", len(lines))
        return "".join(lines[start:end])

    def _tool_write_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        p = Path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(args["content"])
        return {"bytes_written": len(args["content"]), "path": str(p.resolve())}

    async def _tool_git_status(self, args: Dict[str, Any]) -> str:
        res = await bash("git status --short")
        return res.output

    async def _tool_git_diff(self, args: Dict[str, Any]) -> str:
        res = await bash("git diff")
        return res.output

    async def _tool_shell_exec(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cmd = args["command"]
        timeout = args.get("timeout", 60.0)
        res = await bash(cmd, timeout=timeout)
        return {
            "stdout": res.stdout,
            "stderr": res.stderr,
            "exit_code": res.exit_code,
            "timed_out": res.timed_out
        }

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"]
            }
            for t in self.tools.values()
        ]
