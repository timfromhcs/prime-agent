"""Prime Agent RLM runtime package shim for upstream compatibility.

Provides top-level functions and classes expected by upstream Prime Agent code:
- rlm.spawn
- rlm.bash
- rlm.harness
- rlm.mcp
- rlm.emit
- rlm.get_harness_state
"""

from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
from services.rlm.bash import bash, BashHandle, BashResult
from services.rlm.harness import (
    HarnessEntry,
    HarnessScope,
    HarnessState,
    RefinementEvent,
    HarnessStateManager,
    get_harness_state
)

# Shared global harness manager instance for standalone script access
_default_harness = HarnessStateManager()


class _HarnessShim:
    def create_skill(self, name: str, description: str, content: str, reference: Optional[Dict[str, Any]] = None):
        return _default_harness.create_skill(name, description, content, reference=reference)

    def update_skill(self, name: str, content: str, reference: Optional[Dict[str, Any]] = None):
        return _default_harness.update_skill(name, content, reference=reference)

    def delete_skill(self, name: str):
        return _default_harness.delete_skill(name)

    def create_memory(self, key: str, value: str, global_: bool = False):
        return _default_harness.create_memory(key, value, global_=global_)

    def delete_memory(self, key: str, global_: bool = False):
        return _default_harness.delete_memory(key, global_=global_)

    def create_strategy(self, name: str, content: str):
        return _default_harness.create_strategy(name, content)

    def delete_strategy(self, name: str):
        return _default_harness.delete_strategy(name)

    def create_subagent(self, role: str, prompt: str):
        return _default_harness.create_subagent(role, prompt)

    def delete_subagent(self, role: str):
        return _default_harness.delete_subagent(role)

    def create_retrieval(self, key: str, value: str):
        return _default_harness.create_retrieval(key, value)

    def delete_retrieval(self, key: str):
        return _default_harness.delete_retrieval(key)


harness = _HarnessShim()


def emit(data: Dict[str, Any]) -> None:
    pass


async def host_request(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "result": data}


async def spawn(task: str, name: str, role: str = "general", **kwargs) -> Dict[str, Any]:
    from services.subagents.manager import SubagentManager
    mgr = SubagentManager()
    handle = mgr.spawn(prompt=task, name=name, role=role)
    return {"status": "ok", "subagent_id": handle.subagent_id, "name": handle.name}


__all__ = [
    "bash",
    "BashHandle",
    "BashResult",
    "harness",
    "HarnessEntry",
    "HarnessScope",
    "RefinementEvent",
    "get_harness_state",
    "emit",
    "host_request",
    "spawn"
]
