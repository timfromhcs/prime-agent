"""Subagent Coordinator and Lifecycle Manager for Prime Agent.

Manages multi-level recursive subagent trees with bounded depth, budget enforcement,
isolated workspaces, and observable inter-agent messaging.
"""

from __future__ import annotations
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.subagents.protocol import AgentMessage, SubagentHandle, SubagentState
from services.subagents.roles import SUBAGENT_ROLES, SubagentRoleSpec


class SubagentManager:
    """Coordinates recursive subagents, messaging, and isolated contexts."""

    def __init__(
        self,
        base_dir: str = "state/subagents",
        max_depth: int = 3,
        max_subagents: int = 16
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.max_depth = max_depth
        self.max_subagents = max_subagents
        self.subagents: Dict[str, SubagentHandle] = {}
        self.messages: List[AgentMessage] = []
        self._message_log = self.base_dir / "messages.jsonl"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def spawn(
        self,
        prompt: str,
        name: Optional[str] = None,
        role: str = "research",
        parent_id: Optional[str] = None,
        depth: int = 1
    ) -> SubagentHandle:
        """Spawns a new subagent subject to depth and recursion bounds."""
        if parent_id and parent_id in self.subagents:
            parent_depth = self.subagents[parent_id].depth
            depth = parent_depth + 1

        if depth > self.max_depth:
            raise ValueError(f"Recursion depth {depth} exceeds max allowed depth {self.max_depth}")
        if len(self.subagents) >= self.max_subagents:
            raise RuntimeError(f"Maximum subagent limit ({self.max_subagents}) reached")

        subagent_id = f"sub_{uuid4().hex[:8]}"
        agent_name = name or f"{role.capitalize()}Agent_{subagent_id[-4:]}"
        session_dir = self.base_dir / subagent_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Write initial task spec
        spec_file = session_dir / "task_spec.json"
        with open(spec_file, "w", encoding="utf-8") as f:
            json.dump({
                "subagent_id": subagent_id,
                "name": agent_name,
                "role": role,
                "parent_id": parent_id,
                "depth": depth,
                "prompt": prompt,
                "created_at": self._now()
            }, f, indent=2)

        handle = SubagentHandle(
            subagent_id=subagent_id,
            name=agent_name,
            role=role,
            parent_id=parent_id,
            depth=depth,
            session_dir=str(session_dir.resolve()),
            state=SubagentState.INITIALIZING,
            created_at=self._now()
        )
        self.subagents[subagent_id] = handle
        return handle

    async def execute_subagent(
        self,
        subagent_id: str,
        kernel_manager=None,
        llm_client=None,
        router=None,
        prompt_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes the subagent asynchronously in its isolated workspace."""
        if subagent_id not in self.subagents:
            raise KeyError(f"Subagent '{subagent_id}' not found")

        handle = self.subagents[subagent_id]
        handle.state = SubagentState.RUNNING
        session_dir = Path(handle.session_dir)

        # Read prompt from task_spec if not overridden
        spec_file = session_dir / "task_spec.json"
        prompt = prompt_override or ""
        if not prompt and spec_file.exists():
            with open(spec_file, "r", encoding="utf-8") as f:
                prompt = json.load(f).get("prompt", "")

        role_spec = SUBAGENT_ROLES.get(handle.role)
        role_prompt = role_spec.system_prompt if role_spec else f"You are a specialized {handle.role} subagent."

        start_time = time.time()
        findings = []
        artifacts = []
        answer_text = ""
        error_msg = None

        try:
            # 1. Isolated REPL execution if kernel_manager provided
            if kernel_manager:
                repl = kernel_manager.get_or_create_session(subagent_id)
                # Seed workspace directory WITHOUT os.chdir: the REPL shares
                # this process, and chdir would break host relative paths
                # (logs, configs, models). Convention: use SUBAGENT_DIR.
                init_code = (
                    f"import os\nSUBAGENT_DIR = r'{handle.session_dir}'\n"
                    f"subagent_id = '{subagent_id}'\n"
                )
                await repl.execute(init_code)

            # 2. LLM reasoning step if client and router provided
            if llm_client and router:
                port = await router.get_server_port_for_task(handle.role)
                messages = [
                    {"role": "system", "content": f"{role_prompt}\nYour isolated workspace is: {handle.session_dir}\nWrite files with absolute paths under SUBAGENT_DIR.\nProduce concrete findings and code if requested."},
                    {"role": "user", "content": prompt}
                ]
                resp = await llm_client.chat(messages, port=port, max_tokens=256)
                answer_text = resp.content

                # Check if LLM output contained python code to execute
                if "```python" in answer_text and kernel_manager:
                    import re
                    code_blocks = re.findall(r"```python\s*(.*?)\s*```", answer_text, re.DOTALL)
                    for code in code_blocks:
                        res = await kernel_manager.execute(subagent_id, code)
                        if res.get("stdout"):
                            findings.append(f"stdout: {res['stdout'].strip()}")
                        if res.get("result"):
                            findings.append(f"result: {res['result']}")
            else:
                answer_text = f"Subagent {handle.name} completed task: {prompt[:80]}"
                findings.append(f"Role: {handle.role} executed successfully.")

            # Record artifacts in session_dir
            for fpath in session_dir.iterdir():
                if fpath.name not in ["task_spec.json", "transcript.json"]:
                    artifacts.append(str(fpath.resolve()))

            handle.state = SubagentState.COMPLETED
            handle.findings.extend(findings)
            handle.artifacts.extend(artifacts)
            handle.completed_at = self._now()

            # Transmit completion to parent
            if handle.parent_id:
                self.send_message(
                    sender_id=subagent_id,
                    recipient_id=handle.parent_id,
                    content=f"Subagent {handle.name} COMPLETED. Findings: {len(findings)}, Artifacts: {len(artifacts)}. Preview: {answer_text[:120]}"
                )

        except Exception as exc:
            handle.state = SubagentState.FAILED
            handle.error = str(exc)
            handle.completed_at = self._now()
            error_msg = str(exc)
            if handle.parent_id:
                self.send_message(
                    sender_id=subagent_id,
                    recipient_id=handle.parent_id,
                    content=f"Subagent {handle.name} FAILED with error: {exc}"
                )

        # Write execution transcript
        with open(session_dir / "transcript.json", "w", encoding="utf-8") as f:
            json.dump({
                "subagent_id": subagent_id,
                "state": handle.state.value,
                "duration_seconds": round(time.time() - start_time, 3),
                "findings": handle.findings,
                "artifacts": handle.artifacts,
                "answer_preview": answer_text[:300],
                "error": error_msg
            }, f, indent=2)

        return {
            "subagent_id": subagent_id,
            "status": handle.state.value,
            "answer_preview": answer_text[:300],
            "findings": handle.findings,
            "artifacts": handle.artifacts,
            "duration_seconds": round(time.time() - start_time, 3),
            "error": error_msg
        }

    def collect(self, subagent_id: Optional[str] = None) -> Any:
        """Collects results for a specific subagent or all child agents."""
        if subagent_id:
            if subagent_id not in self.subagents:
                return None
            h = self.subagents[subagent_id]
            return {
                "subagent_id": h.subagent_id,
                "name": h.name,
                "role": h.role,
                "state": h.state.value,
                "settled": h.state in [SubagentState.COMPLETED, SubagentState.FAILED],
                "findings": h.findings,
                "artifacts": h.artifacts,
                "error": h.error,
                "session_dir": h.session_dir
            }
        return [self.collect(sid) for sid in self.subagents.keys()]

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """Transmits an observable message between subagents or parent/child."""
        msg = AgentMessage(
            message_id=f"msg_{uuid4().hex[:8]}",
            sender_id=sender_id,
            recipient_id=recipient_id,
            timestamp=self._now(),
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(msg)
        with open(self._message_log, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "message_id": msg.message_id,
                "sender": msg.sender_id,
                "recipient": msg.recipient_id,
                "timestamp": msg.timestamp,
                "content": msg.content,
                "metadata": msg.metadata
            }) + "\n")
        return msg

    def get_messages_for(self, agent_id: str) -> List[AgentMessage]:
        return [m for m in self.messages if m.recipient_id == agent_id or m.sender_id == agent_id]

    def update_state(
        self,
        subagent_id: str,
        state: SubagentState,
        findings: Optional[List[str]] = None,
        artifacts: Optional[List[str]] = None,
        error: Optional[str] = None
    ):
        if subagent_id in self.subagents:
            handle = self.subagents[subagent_id]
            handle.state = state
            if findings:
                handle.findings.extend(findings)
            if artifacts:
                handle.artifacts.extend(artifacts)
            if error:
                handle.error = error
            if state in [SubagentState.COMPLETED, SubagentState.FAILED, SubagentState.CANCELLED]:
                handle.completed_at = self._now()

    def list_subagents(self) -> List[Dict[str, Any]]:
        return [
            {
                "subagent_id": h.subagent_id,
                "name": h.name,
                "role": h.role,
                "parent_id": h.parent_id,
                "depth": h.depth,
                "state": h.state.value,
                "created_at": h.created_at,
                "completed_at": h.completed_at,
                "findings_count": len(h.findings),
                "artifacts_count": len(h.artifacts),
                "error": h.error
            }
            for h in self.subagents.values()
        ]

    def cleanup(self, subagent_id: Optional[str] = None):
        """Cleans up in-memory or directory state for subagents."""
        if subagent_id and subagent_id in self.subagents:
            del self.subagents[subagent_id]
        elif not subagent_id:
            self.subagents.clear()
