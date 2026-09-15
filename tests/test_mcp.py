"""Test Suite for MCP: Policy Gate, Sandboxing, Tools Registry, and Server/Client."""

import os
import pytest
from services.mcp.policy import ToolSecurityPolicy
from services.mcp.tools import MCPToolRegistry
from services.mcp.server import MCPServer
from services.mcp.client import MCPClient


def test_mcp_security_policy_sandbox(tmp_path):
    sandbox = str(tmp_path / "sandbox")
    os.makedirs(sandbox, exist_ok=True)
    outside = str(tmp_path / "outside")
    os.makedirs(outside, exist_ok=True)

    policy = ToolSecurityPolicy(sandbox_roots=[sandbox])

    # In sandbox path
    safe_file = os.path.join(sandbox, "test.txt")
    assert policy.validate_and_gate("read_file", {"path": safe_file}) is None

    # Outside sandbox path
    bad_file = os.path.join(outside, "secret.key")
    denial = policy.validate_and_gate("read_file", {"path": bad_file})
    assert denial is not None
    assert "Access denied" in denial


@pytest.mark.asyncio
async def test_mcp_tools_and_server_client(tmp_path):
    registry = MCPToolRegistry(policy=ToolSecurityPolicy(sandbox_roots=[str(tmp_path)]))
    server = MCPServer(registry)
    client = MCPClient(server)

    # List tools
    tools = await client.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "write_file" in tool_names
    assert "read_file" in tool_names

    # Write file via MCP
    test_file = str(tmp_path / "hello.txt")
    write_res = await client.call_tool("write_file", {"path": test_file, "content": "Prime MCP Online"})
    assert write_res["bytes_written"] == 16

    # Read file via MCP
    read_res = await client.call_tool("read_file", {"path": test_file})
    assert "Prime MCP Online" in read_res
