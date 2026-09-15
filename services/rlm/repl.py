"""Persistent Python REPL Runtime for Prime RLM.

Executes code cells in a single persistent __main__ namespace on an asyncio event loop.
Features:
- Top-level await support (PyCF_ALLOW_TOP_LEVEL_AWAIT)
- Namespace persistence across executions
- State snapshot / restore using dill
- Host request/reply bridge for subagents, RAG, MCP, images
- Stdout / Stderr capture with truncation protection
"""

from __future__ import annotations
import ast
import asyncio
import io
import json
import os
import sys
import traceback
from typing import Any, Dict, Optional
import dill

from services.rlm.bash import bash
from services.rlm.bridge import RlmBridge, RagBridge, ImageBridge, McpBridge


class ReplSession:
    """A persistent execution session maintaining state across cell executions."""

    def __init__(self, session_id: str, host_handler=None):
        self.session_id = session_id
        self.host_handler = host_handler
        self.rlm = RlmBridge(host_handler)
        self.rag = RagBridge(host_handler)
        self.image = ImageBridge(host_handler)
        self.mcp = McpBridge(host_handler)

        self.namespace: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
            "__builtins__": __builtins__,
            "asyncio": asyncio,
            "bash": bash,
            "rlm": self.rlm,
            "rag": self.rag,
            "image": self.image,
            "mcp": self.mcp,
            "json": json,
            "os": os,
            "sys": sys
        }
        self.execution_count = 0

    def set_host_handler(self, handler):
        self.host_handler = handler
        self.rlm.set_handler(handler)
        self.rag.set_handler(handler)
        self.image.set_handler(handler)
        self.mcp.set_handler(handler)

    async def execute(self, code: str, max_output_chars: int = 32768) -> Dict[str, Any]:
        """Executes a code snippet with top-level await in the persistent namespace."""
        self.execution_count += 1
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        sys.stdout = stdout_buf
        sys.stderr = stderr_buf

        status = "ok"
        result_repr = None
        error_info = None

        try:
            # Parse code to check syntax and determine trailing expression
            parsed = ast.parse(code, filename=f"<cell-{self.execution_count}>")
            if not parsed.body:
                return {
                    "status": "ok",
                    "stdout": "",
                    "stderr": "",
                    "result": None
                }

            last_expr = None
            if isinstance(parsed.body[-1], ast.Expr):
                last_expr = parsed.body.pop()

            # Compile statements
            compiled_stmts = None
            if parsed.body:
                compiled_stmts = compile(
                    parsed,
                    filename=f"<cell-{self.execution_count}>",
                    mode="exec",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
                )

            # Compile trailing expression if present
            compiled_expr = None
            if last_expr:
                expr_ast = ast.Expression(body=last_expr.value)
                compiled_expr = compile(
                    expr_ast,
                    filename=f"<cell-{self.execution_count}>",
                    mode="eval",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
                )

            # Execute statements
            if compiled_stmts:
                res = eval(compiled_stmts, self.namespace)
                if asyncio.iscoroutine(res):
                    await res

            # Evaluate trailing expression
            if compiled_expr:
                res = eval(compiled_expr, self.namespace)
                if asyncio.iscoroutine(res):
                    res = await res
                if res is not None:
                    result_repr = repr(res)
                    self.namespace["_"] = res

        except BaseException as exc:
            status = "error"
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            error_info = {
                "ename": type(exc).__name__,
                "evalue": str(exc),
                "traceback": tb_lines
            }
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

        stdout_val = stdout_buf.getvalue()[:max_output_chars]
        stderr_val = stderr_buf.getvalue()[:max_output_chars]

        return {
            "status": status,
            "stdout": stdout_val,
            "stderr": stderr_val,
            "result": result_repr,
            "error": error_info,
            "execution_count": self.execution_count
        }

    def snapshot(self, path: str, max_bytes: int = 50 * 1024 * 1024) -> Dict[str, Any]:
        """Snapshots the serializable variables in namespace using dill."""
        saved = []
        skipped = []
        state_dict = {}

        skip_keys = {
            "__builtins__", "asyncio", "bash", "rlm", "rag", "image", "mcp",
            "json", "os", "sys", "_", "__name__", "__doc__"
        }

        for k, v in self.namespace.items():
            if k.startswith("_") or k in skip_keys:
                continue
            try:
                pickled = dill.dumps(v)
                if len(pickled) > max_bytes:
                    skipped.append({"name": k, "reason": "too large"})
                else:
                    state_dict[k] = pickled
                    saved.append(k)
            except Exception as e:
                skipped.append({"name": k, "reason": str(e)})

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            dill.dump(state_dict, f)

        return {
            "status": "ok",
            "saved": saved,
            "skipped": skipped,
            "total_saved": len(saved)
        }

    def restore(self, path: str) -> Dict[str, Any]:
        """Restores previously snapshotted namespace state."""
        if not os.path.exists(path):
            return {"status": "error", "reason": "Snapshot file not found"}

        try:
            with open(path, "rb") as f:
                state_dict = dill.load(f)
            restored = []
            for k, pickled_bytes in state_dict.items():
                try:
                    self.namespace[k] = dill.loads(pickled_bytes)
                    restored.append(k)
                except Exception as e:
                    pass
            return {"status": "ok", "restored": restored}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def list_names(self) -> List[str]:
        """Lists user-defined variable names currently in namespace."""
        skip_keys = {
            "__builtins__", "asyncio", "bash", "rlm", "rag", "image", "mcp",
            "json", "os", "sys", "_", "__name__", "__doc__"
        }
        return [k for k in self.namespace.keys() if not k.startswith("_") and k not in skip_keys]
