"""Multi-tier Memory Architecture for Prime Agent.

Provides persistent memory subsystems:
- Working Memory (current task context, active variables)
- Episodic Memory (trajectories, tool outcomes, failures & successes)
- Semantic Memory (distilled knowledge, concepts)
- Artifact Memory (SHA-256 records, paths, metadata)
- Goal Memory (persistent goals, milestones, status)
"""

from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class GoalItem:
    goal_id: str
    title: str
    description: str
    status: str  # "ACTIVE" | "PAUSED" | "COMPLETED" | "CANCELLED"
    created_at: str
    updated_at: str
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    record_id: str
    tier: str  # "working" | "episodic" | "semantic" | "artifact"
    key: str
    value: Any
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentMemorySystem:
    """Manages persistent multi-tier memory records and goals."""

    def __init__(self, memory_dir: str = "data/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "agent_memory.json"
        self.goals_file = self.memory_dir / "goals.json"

        self.records: Dict[str, MemoryRecord] = {}
        self.goals: Dict[str, GoalItem] = {}
        self._load()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.records = {k: MemoryRecord(**v) for k, v in data.items()}
            except Exception as e:
                print(f"[Memory] Error loading records: {e}")

        if self.goals_file.exists():
            try:
                with open(self.goals_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.goals = {k: GoalItem(**v) for k, v in data.items()}
            except Exception as e:
                print(f"[Memory] Error loading goals: {e}")

    def save(self):
        data_records = {k: asdict(v) for k, v in self.records.items()}
        temp_mem = self.memory_file.with_suffix(".tmp")
        with open(temp_mem, "w", encoding="utf-8") as f:
            json.dump(data_records, f, indent=2)
        temp_mem.replace(self.memory_file)

        data_goals = {k: asdict(v) for k, v in self.goals.items()}
        temp_goals = self.goals_file.with_suffix(".tmp")
        with open(temp_goals, "w", encoding="utf-8") as f:
            json.dump(data_goals, f, indent=2)
        temp_goals.replace(self.goals_file)

    def store(self, tier: str, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> MemoryRecord:
        record_id = f"mem_{uuid4().hex[:8]}"
        rec = MemoryRecord(
            record_id=record_id,
            tier=tier,
            key=key,
            value=value,
            created_at=self._now(),
            metadata=metadata or {}
        )
        self.records[record_id] = rec
        self.save()
        return rec

    def retrieve(self, tier: str, key: str) -> Optional[Any]:
        for r in reversed(list(self.records.values())):
            if r.tier == tier and r.key == key:
                return r.value
        return None

    def query(self, tier: Optional[str] = None, key_prefix: Optional[str] = None) -> List[MemoryRecord]:
        matches = []
        for r in self.records.values():
            if tier and r.tier != tier:
                continue
            if key_prefix and not r.key.startswith(key_prefix):
                continue
            matches.append(r)
        return matches

    def create_goal(self, title: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> GoalItem:
        goal_id = f"goal_{uuid4().hex[:8]}"
        ts = self._now()
        goal = GoalItem(
            goal_id=goal_id,
            title=title,
            description=description,
            status="ACTIVE",
            created_at=ts,
            updated_at=ts,
            milestones=[],
            metadata=metadata or {}
        )
        self.goals[goal_id] = goal
        self.save()
        return goal

    def update_goal(self, goal_id: str, status: str, milestone: Optional[Dict[str, Any]] = None):
        if goal_id in self.goals:
            g = self.goals[goal_id]
            g.status = status
            g.updated_at = self._now()
            if milestone:
                g.milestones.append(milestone)
            self.save()

    def list_goals(self, status: Optional[str] = None) -> List[GoalItem]:
        if status:
            return [g for g in self.goals.values() if g.status == status]
        return list(self.goals.values())
