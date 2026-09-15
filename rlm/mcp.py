"""MCP integration module for rlm namespace."""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List
from services.mcp.tools import MCPToolRegistry

_registry = MCPToolRegistry()


async def list_tools() -> List[Dict[str, Any]]:
    """Returns list of registered tool schemas."""
    return _registry.get_tool_definitions()


async def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes a tool call through security policy gate."""
    return await _registry.execute(name, arguments)


class McpIntegration:
    list_tools = staticmethod(list_tools)
    call_tool = staticmethod(call_tool)
