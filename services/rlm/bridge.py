"""Host bridge for Prime Agent RLM.

Provides programmatic APIs injected into the persistent Python execution environment:
- rlm.spawn(prompt, name=None, role="general", **kwargs)
- rlm.send_message(recipient, message)
- rlm.list_subagents()
- rlm.collect(subagent_id=None)
- rlm.harness: create_skill, update_skill, delete_skill, create_memory, delete_memory, create_strategy
- rlm.get_harness_state(global_=False)
- rlm.emit(data)
- rag.search(query, top_k=5)
- rag.ingest(path)
- image.generate(prompt, **kwargs)
- image.edit(prompt, image_path, **kwargs)
- mcp.call(server, tool, **args)
- bash(cmd)
"""

from __future__ import annotations
import asyncio
from typing import Any, Callable, Dict, List, Optional
from services.rlm.bash import bash


class HarnessBridge:
    def __init__(self, rlm_bridge: RlmBridge):
        self._rlm = rlm_bridge

    async def create_skill(self, name: str, description: str, content: str, reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._rlm._request("harness_create_skill", name=name, description=description, content=content, reference=reference)

    async def update_skill(self, name: str, content: str, reference: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._rlm._request("harness_update_skill", name=name, content=content, reference=reference)

    async def delete_skill(self, name: str) -> Dict[str, Any]:
        return await self._rlm._request("harness_delete_skill", name=name)

    async def create_memory(self, key: str, value: str, global_: bool = False) -> Dict[str, Any]:
        return await self._rlm._request("harness_create_memory", key=key, value=value, global_=global_)

    async def delete_memory(self, key: str, global_: bool = False) -> Dict[str, Any]:
        return await self._rlm._request("harness_delete_memory", key=key, global_=global_)

    async def create_strategy(self, name: str, content: str) -> Dict[str, Any]:
        return await self._rlm._request("harness_create_strategy", name=name, content=content)

    async def delete_strategy(self, name: str) -> Dict[str, Any]:
        return await self._rlm._request("harness_delete_strategy", name=name)


class RlmBridge:
    def __init__(self, host_handler: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self._handler = host_handler
        self.harness = HarnessBridge(self)

    def set_handler(self, handler: Callable[[Dict[str, Any]], Any]):
        self._handler = handler

    async def _request(self, op: str, **kwargs) -> Any:
        if not self._handler:
            raise RuntimeError("RLM host bridge handler not connected.")
        payload = {"op": op, **kwargs}
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(payload)
        return self._handler(payload)

    async def spawn(self, prompt: str, name: Optional[str] = None, role: str = "general", **kwargs) -> Dict[str, Any]:
        """Spawns a child subagent asynchronously."""
        return await self._request("subagent_spawn", prompt=prompt, name=name, role=role, kwargs=kwargs)

    async def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        """Sends an observable message to another subagent or parent."""
        return await self._request("subagent_message", recipient=recipient, message=message)

    async def list_subagents(self) -> List[Dict[str, Any]]:
        """Lists active and completed subagents."""
        return await self._request("subagent_list")

    async def collect(self, subagent_id: Optional[str] = None) -> Any:
        """Collects child results and status."""
        return await self._request("subagent_collect", subagent_id=subagent_id)

    async def get_harness_state(self, global_: bool = False) -> Dict[str, Any]:
        """Retrieves active harness state."""
        return await self._request("harness_get_state", global_=global_)

    def emit(self, data: Dict[str, Any]) -> None:
        """Emits display or telemetry data."""
        if self._handler:
            self._handler({"op": "emit", "data": data})


class RagBridge:
    def __init__(self, host_handler: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self._handler = host_handler

    def set_handler(self, handler: Callable[[Dict[str, Any]], Any]):
        self._handler = handler

    async def _request(self, op: str, **kwargs) -> Any:
        if not self._handler:
            raise RuntimeError("RAG host bridge handler not connected.")
        payload = {"op": op, **kwargs}
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(payload)
        return self._handler(payload)

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Performs hybrid vector+lexical RAG search and reranking."""
        return await self._request("rag_search", query=query, top_k=top_k)

    async def ingest(self, path: str) -> Dict[str, Any]:
        """Ingests a document or directory into the RAG index."""
        return await self._request("rag_ingest", path=path)


class ImageBridge:
    def __init__(self, host_handler: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self._handler = host_handler

    def set_handler(self, handler: Callable[[Dict[str, Any]], Any]):
        self._handler = handler

    async def _request(self, op: str, **kwargs) -> Any:
        if not self._handler:
            raise RuntimeError("Image host bridge handler not connected.")
        payload = {"op": op, **kwargs}
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(payload)
        return self._handler(payload)

    async def generate(self, prompt: str, steps: int = 15, guidance: float = 7.5, **kwargs) -> Dict[str, Any]:
        """Generates an image artifact headlessly from text."""
        return await self._request("image_generate", prompt=prompt, steps=steps, guidance=guidance, **kwargs)

    async def edit(self, prompt: str, image_path: str, strength: float = 0.6, steps: int = 15, **kwargs) -> Dict[str, Any]:
        """Edits an existing image artifact headlessly via image-to-image."""
        return await self._request("image_edit", prompt=prompt, image_path=image_path, strength=strength, steps=steps, **kwargs)


class McpBridge:
    def __init__(self, host_handler: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self._handler = host_handler

    def set_handler(self, handler: Callable[[Dict[str, Any]], Any]):
        self._handler = handler

    async def _request(self, op: str, **kwargs) -> Any:
        if not self._handler:
            raise RuntimeError("MCP host bridge handler not connected.")
        payload = {"op": op, **kwargs}
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(payload)
        return self._handler(payload)

    async def call(self, server: str, tool: str, **args) -> Dict[str, Any]:
        """Executes a tool on a registered MCP server through security policy."""
        return await self._request("mcp_call", server=server, tool=tool, args=args)
