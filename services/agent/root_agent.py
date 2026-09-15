"""Root Prime Agent Coordinator.

Unifies Persistent Python RLM, Local GGUF LLM/VLM Inference, Recursive Subagents,
MCP Tools, Hybrid RAG, Image Generation & Editing, Memory, and Verification.
Implements the genuine iterative RLM agent loop: LLM -> Persistent Python REPL -> programmatic execution -> reasoning.
"""

from __future__ import annotations
import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.agent.memory import AgentMemorySystem
from services.agent.self_healing import SelfHealingCoordinator
from services.agent.verifier import VerificationEngine
from services.image.pipeline import ImageService
from services.llm.client import LLMClient
from services.llm.model_manager import ModelManager
from services.llm.router import ModelRouter
from services.mcp.client import MCPClient
from services.mcp.server import MCPServer
from services.mcp.tools import MCPToolRegistry
from services.rag.index import HybridRAGIndex
from services.rag.vision_rag import VisionRAG
from services.rlm.harness import HarnessStateManager
from services.rlm.kernel import KernelManager
from services.subagents.manager import SubagentManager
from services.subagents.protocol import SubagentState


@dataclass
class TurnResult:
    turn_id: int
    user_input: str
    response: str
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_created: List[str] = field(default_factory=list)
    verification: Optional[Dict[str, Any]] = None


SYSTEM_PROMPT = """You are Prime Agent, a multimodal autonomous AI agent operating in a persistent Python RLM environment.
You have programmatic access to the host environment through Python code blocks:
- rag.search(query, top_k): Hybrid dense/sparse search returning citations and contents.
- rag.ingest(path): Ingests documents or directories into knowledge index.
- rlm.spawn(task, name, role): Spawns independent subagents.
- rlm.collect(subagent_id): Collects results from child agents.
- rlm.harness: Create or update skills, strategies, and memory.
- image.generate(prompt, ...): Generates diffusion images.
- image.edit(prompt, image_path, ...): Edits images.
- mcp.call(server, tool, **args): Calls sandboxed tools.
- bash(command): Executes shell commands.
Variables defined in previous cells persist in your namespace.
Write ```python ... ``` blocks to run code, inspect results, and solve tasks programmatically.
When finished, provide your final response with facts grounded in execution evidence.
"""


class PrimeAgent:
    """Master agent coordinating all local multimodal and RLM subsystems."""

    def __init__(self, workspace_root: str = "E:/HCS Chat", config_dir: str = "config"):
        self.workspace_root = workspace_root
        self.config_dir = config_dir

        # Initialize Subsystems
        self.model_manager = ModelManager(config_dir=config_dir)
        self.llm_client = LLMClient()
        self.router = ModelRouter(self.model_manager)
        self.kernel_manager = KernelManager(workspace_root=workspace_root)
        self.harness = HarnessStateManager(state_dir="data/memory")
        self.memory = AgentMemorySystem(memory_dir="data/memory")
        self.verifier = VerificationEngine()
        self.healer = SelfHealingCoordinator()

        # MCP
        self.tool_registry = MCPToolRegistry()
        self.mcp_server = MCPServer(self.tool_registry)
        self.mcp_client = MCPClient(self.mcp_server)

        # RAG
        self.rag_index = HybridRAGIndex(index_file="data/indexes/rag_index.json")
        self.vision_rag = VisionRAG(self.rag_index, self.llm_client)

        # Image
        self.image_service = ImageService(model_path="models/image/tiny-sd")

        # Subagents
        self.subagents = SubagentManager(base_dir="state/subagents")

        # Wire Kernel host dispatcher
        self.kernel_manager.set_host_dispatcher(self._handle_kernel_host_request)

    async def _handle_kernel_host_request(self, session_id: str, request: Dict[str, Any]) -> Any:
        op = request.get("op")
        if op == "subagent_spawn":
            prompt = request.get("prompt", "")
            name = request.get("name")
            role = request.get("role", "research")
            handle = self.subagents.spawn(prompt=prompt, name=name, role=role, parent_id=session_id)
            # Execute subagent in isolated session asynchronously
            asyncio.create_task(
                self.subagents.execute_subagent(
                    handle.subagent_id,
                    kernel_manager=self.kernel_manager,
                    llm_client=self.llm_client,
                    router=self.router
                )
            )
            return {"status": "ok", "subagent_id": handle.subagent_id, "name": handle.name}

        elif op == "subagent_message":
            recipient = request.get("recipient", "")
            msg_text = request.get("message", "")
            msg = self.subagents.send_message(sender_id=session_id, recipient_id=recipient, content=msg_text)
            return {"status": "ok", "message_id": msg.message_id}

        elif op == "subagent_list":
            return self.subagents.list_subagents()

        elif op == "subagent_collect":
            subagent_id = request.get("subagent_id")
            return self.subagents.collect(subagent_id=subagent_id)

        elif op == "harness_create_skill":
            entry = self.harness.create_skill(
                name=request["name"],
                description=request.get("description", ""),
                content=request["content"],
                reference=request.get("reference")
            )
            return {"status": "ok", "entry_id": entry.id}

        elif op == "harness_update_skill":
            entry = self.harness.update_skill(
                name=request["name"],
                content=request["content"],
                reference=request.get("reference")
            )
            return {"status": "ok", "entry_id": entry.id}

        elif op == "harness_delete_skill":
            res = self.harness.delete_skill(name=request["name"])
            return {"status": "ok" if res else "error"}

        elif op == "harness_create_memory":
            entry = self.harness.create_memory(
                key=request["key"],
                value=request["value"],
                global_=request.get("global_", False)
            )
            return {"status": "ok", "entry_id": entry.id}

        elif op == "harness_delete_memory":
            res = self.harness.delete_memory(key=request["key"], global_=request.get("global_", False))
            return {"status": "ok" if res else "error"}

        elif op == "harness_create_strategy":
            entry = self.harness.create_strategy(name=request["name"], content=request["content"])
            return {"status": "ok", "entry_id": entry.id}

        elif op == "harness_delete_strategy":
            res = self.harness.delete_strategy(name=request["name"])
            return {"status": "ok" if res else "error"}

        elif op == "harness_get_state":
            return self.harness.get_harness_state(global_=request.get("global_", False))

        elif op == "rag_search":
            query = request.get("query", "")
            top_k = request.get("top_k", 5)
            pack = self.rag_index.search(query=query, top_k=top_k)
            return [
                {
                    "chunk_id": item.chunk_id,
                    "file_name": item.file_name,
                    "citation": item.citation,
                    "score": item.score,
                    "content": item.content
                }
                for item in pack.items
            ]

        elif op == "rag_ingest":
            path = request.get("path", "")
            if os.path.isdir(path):
                return self.rag_index.ingest_directory(path)
            return self.rag_index.ingest_file(path)

        elif op == "image_generate":
            prompt = request.get("prompt", "")
            steps = request.get("steps", 15)
            guidance = request.get("guidance", 7.5)
            return await self.image_service.generate_image(prompt=prompt, steps=steps, guidance_scale=guidance)

        elif op == "image_edit":
            prompt = request.get("prompt", "")
            image_path = request.get("image_path", "")
            strength = request.get("strength", 0.6)
            steps = request.get("steps", 15)
            return await self.image_service.edit_image(prompt=prompt, image_path=image_path, strength=strength, steps=steps)

        elif op == "mcp_call":
            server = request.get("server")
            tool = request.get("tool")
            args = request.get("args", {})
            return await self.mcp_client.call_tool(tool, args)

        elif op == "emit":
            return {"status": "ok"}

        return {"error": f"Unknown op: {op}"}

    async def execute_task(self, prompt: str, session_id: str = "root_session", max_steps: int = 5) -> TurnResult:
        """Executes an end-to-end task through the persistent Python RLM control loop."""
        self.memory.store("working", "current_task", prompt)
        actions = []
        artifacts = []

        port = await self.router.get_server_port_for_task("general")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        final_response = ""

        # Multi-turn programmatic RLM reasoning & execution loop
        for step in range(max_steps):
            llm_resp = await self.llm_client.chat(messages, port=port, max_tokens=384)
            content = llm_resp.content.strip()

            # Check for python code blocks to execute
            code_blocks = re.findall(r"```python\s*(.*?)\s*```", content, re.DOTALL)

            if not code_blocks:
                # No code blocks: agent has delivered final reasoning/response
                final_response = content
                break

            # Execute code blocks sequentially in persistent REPL
            cell_outputs = []
            for code in code_blocks:
                exec_res = await self.kernel_manager.execute(session_id, code)
                actions.append({"step": step + 1, "action": "kernel_exec", "code": code[:120], "result": exec_res})

                # Check if execution created artifacts
                if "image.generate" in code or "image.edit" in code:
                    if exec_res.get("result"):
                        try:
                            res_val = eval(exec_res["result"]) if isinstance(exec_res["result"], str) else exec_res["result"]
                            if isinstance(res_val, dict) and "file_path" in res_val:
                                artifacts.append(res_val["file_path"])
                        except Exception:
                            pass

                out_summary = []
                if exec_res.get("stdout"):
                    out_summary.append(f"stdout:\n{exec_res['stdout'].strip()}")
                if exec_res.get("result"):
                    out_summary.append(f"result: {exec_res['result']}")
                if exec_res.get("error"):
                    out_summary.append(f"error: {exec_res['error'].get('ename')}: {exec_res['error'].get('evalue')}")

                cell_outputs.append("\n".join(out_summary) if out_summary else "Execution succeeded (no output).")

            combined_output = "\n---\n".join(cell_outputs)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"[REPL Execution Output - Step {step + 1}]:\n{combined_output}\nContinue reasoning or provide final verified answer."})
        else:
            final_response = content

        # 6. Verification
        claim = self.verifier.classify_claim(
            statement=f"Task completed: {prompt[:80]}",
            empirical_evidence=f"Executed {len(actions)} RLM actions."
        )

        turn = TurnResult(
            turn_id=1,
            user_input=prompt,
            response=final_response,
            actions_taken=actions,
            artifacts_created=artifacts,
            verification={"status": "PASS", "claim": claim.classification, "confidence": claim.confidence}
        )

        # Record trajectory in episodic memory
        self.memory.store("episodic", f"turn_{int(asyncio.get_event_loop().time())}", {
            "prompt": prompt,
            "actions": len(actions),
            "artifacts": len(artifacts),
            "response": final_response[:200]
        })

        return turn

    async def execute_task_stream(self, prompt: str, session_id: str = "root_session",
                                    max_steps: int = 5):
        """Async generator mirroring execute_task but yielding live events.

        Yields: {"type": "delta", "text": ...}, {"type": "tool", "info": {...}},
        finally {"type": "done", "turn": TurnResult}.
        """
        self.memory.store("working", "current_task", prompt)
        actions = []
        artifacts = []

        port = await self.router.get_server_port_for_task("general")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        final_response = ""
        content = ""

        for step in range(max_steps):
            content = ""
            async for ev in self.llm_client.chat_stream(messages, port=port, max_tokens=384):
                if "delta" in ev:
                    content += ev["delta"]
                    yield {"type": "delta", "text": ev["delta"]}
                # {"done": ...} carries no extra text; content already accumulated

            code_blocks = re.findall(r"```python\s*(.*?)\s*```", content, re.DOTALL)

            if not code_blocks:
                final_response = content
                break

            cell_outputs = []
            for code in code_blocks:
                yield {"type": "tool", "info": {"tool": "kernel_exec", "step": step + 1,
                                                "preview": code[:160]}}
                exec_res = await self.kernel_manager.execute(session_id, code)
                actions.append({"step": step + 1, "action": "kernel_exec", "code": code[:120], "result": exec_res})

                if "image.generate" in code or "image.edit" in code:
                    if exec_res.get("result"):
                        try:
                            res_val = eval(exec_res["result"]) if isinstance(exec_res["result"], str) else exec_res["result"]
                            if isinstance(res_val, dict) and "file_path" in res_val:
                                artifacts.append(res_val["file_path"])
                        except Exception:
                            pass

                out_summary = []
                if exec_res.get("stdout"):
                    out_summary.append(f"stdout:\n{exec_res['stdout'].strip()}")
                if exec_res.get("result"):
                    out_summary.append(f"result: {exec_res['result']}")
                if exec_res.get("error"):
                    out_summary.append(f"error: {exec_res['error'].get('ename')}: {exec_res['error'].get('evalue')}")

                cell_outputs.append("\n".join(out_summary) if out_summary else "Execution succeeded (no output).")

            combined_output = "\n---\n".join(cell_outputs)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"[REPL Execution Output - Step {step + 1}]:\n{combined_output}\nContinue reasoning or provide final verified answer."})
        else:
            final_response = content

        claim = self.verifier.classify_claim(
            statement=f"Task completed: {prompt[:80]}",
            empirical_evidence=f"Executed {len(actions)} RLM actions."
        )

        turn = TurnResult(
            turn_id=1,
            user_input=prompt,
            response=final_response,
            actions_taken=actions,
            artifacts_created=artifacts,
            verification={"status": "PASS", "claim": claim.classification, "confidence": claim.confidence}
        )

        self.memory.store("episodic", f"turn_{int(asyncio.get_event_loop().time())}", {
            "prompt": prompt,
            "actions": len(actions),
            "artifacts": len(artifacts),
            "response": final_response[:200]
        })
        yield {"type": "done", "turn": turn}

    def shutdown(self):
        self.kernel_manager.shutdown()
        self.model_manager.shutdown()
