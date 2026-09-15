"""Model Context Protocol (MCP) Server for Prime Agent.

Implements JSON-RPC MCP standard interface for tool discovery and execution.
"""

from __future__ import annotations
import json
from typing import Any, Dict, Optional
from services.mcp.tools import MCPToolRegistry


class MCPServer:
    """Local JSON-RPC MCP Server exposing registered tools."""

    def __init__(self, registry: Optional[MCPToolRegistry] = None):
        self.registry = registry or MCPToolRegistry()

    async def handle_request(self, request_json: str) -> str:
        try:
            req = json.loads(request_json)
        except Exception as e:
            return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}})

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "tools/list":
            tools = self.registry.get_tool_definitions()
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools}
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            result = await self.registry.execute(tool_name, arguments)
            if result.get("status") == "error":
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": result.get("error")}
                })
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result.get("result"))}]}
            })

        elif method == "initialize":
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "prime-local-mcp", "version": "1.0.0"}
                }
            })

        return json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })
