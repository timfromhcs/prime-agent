"""Subagent Protocol Definitions for Prime RLM.

Enforces bounded recursive execution, structured inter-agent messaging,
and observable state transitions.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SubagentState(str, Enum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class AgentMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    timestamp: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentHandle:
    subagent_id: str
    name: str
    role: str
    parent_id: Optional[str]
    depth: int
    session_dir: str
    state: SubagentState
    created_at: str
    completed_at: Optional[str] = None
    token_usage: int = 0
    findings: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
