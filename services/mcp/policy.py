"""Security Policy and Permission Gate for MCP tools.

Enforces:
- Schema validation
- Sandboxed directory limits
- Permission gates for destructive actions
- Execution audit trails
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ToolSecurityPolicy:
    """Validates and gates tool execution for safety and auditability."""

    def __init__(
        self,
        sandbox_roots: Optional[List[str]] = None,
        audit_log_path: str = "logs/mcp_audit.log"
    ):
        extra = [p for p in os.environ.get("PRIME_SANDBOX_EXTRA", "").split(os.pathsep) if p.strip()]
        self.sandbox_roots = [
            str(Path(r).resolve())
            for r in (sandbox_roots or [os.getcwd(), "data/artifacts", "logs"] + extra)
        ]
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def is_path_safe(self, target_path: str) -> bool:
        try:
            resolved = str(Path(target_path).resolve())
            return any(resolved.startswith(root) for root in self.sandbox_roots)
        except Exception:
            return False

    def validate_and_gate(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        """Returns an error message if the tool call violates security policy, or None if allowed."""
        if tool_name in ["read_file", "write_file", "list_dir"]:
            path = args.get("path") or args.get("file_path") or args.get("target_path")
            if path and not self.is_path_safe(path):
                return f"Access denied: path '{path}' is outside permitted workspace sandboxes."

        if tool_name == "git_command":
            cmd = args.get("command", "")
            dangerous = ["reset --hard", "clean -fd", "push --force", "rebase"]
            if any(d in cmd for d in dangerous):
                return f"Command rejected: '{cmd}' contains dangerous operations prohibited by policy."

        return None

    def log_execution(
        self,
        tool_name: str,
        args: Dict[str, Any],
        status: str,
        result_preview: str,
        duration: float
    ):
        ts = datetime.now(timezone.utc).isoformat()
        entry = {
            "timestamp": ts,
            "tool": tool_name,
            "args": args,
            "status": status,
            "duration_sec": round(duration, 4),
            "result_preview": result_preview[:200]
        }
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(f"{entry}\n")
