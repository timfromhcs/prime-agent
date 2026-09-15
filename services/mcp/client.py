"""Model Context Protocol (MCP) Client for Prime Agent."""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from services.mcp.server import MCPServer


class MCPClient:
    """Client for querying and executing tools on MCP servers."""

    def __init__(self, server: MCPServer):
        self.server = server

    async def list_tools(self) -> List[Dict[str, Any]]:
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        resp_str = await self.server.handle_request(json.dumps(req))
        resp = json.loads(resp_str)
        return resp.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }
        resp_str = await self.server.handle_request(json.dumps(req))
        resp = json.loads(resp_str)
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error'].get('message')}")
        content = resp.get("result", {}).get("content", [{}])[0]
        text = content.get("text", "")
        try:
            return json.loads(text)
        except Exception:
            return text
