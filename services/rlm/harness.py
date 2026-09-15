"""Persistent harness-state manager for Prime Agent RLM.

Fully aligned with upstream Prime Agent harness architecture:
Tracks prompt notes, memory, skills, subagent specs, strategies, retrieval, and refinement history.
Enforces immutable base safety policies and provides transactional reversible snapshots and rollback.
"""

from __future__ import annotations
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4


HarnessKind = Literal["prompt", "memory", "skill", "subagent", "strategy", "retrieval"]
HarnessScope = Literal["local", "global"]


class HarnessState:
    """Wrapper or representation of overall harness state."""
    def __init__(self, entries: Optional[Dict[str, Any]] = None):
        self.entries = entries or {}


@dataclass
class HarnessEntry:
    id: str
    kind: HarnessKind
    name: str
    content: str
    created_at: str
    updated_at: str
    scope: HarnessScope = "local"
    reference: Dict[str, Any] = field(default_factory=dict)
    arguments: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    immutable: bool = False
    source: str = "agent"
    version: int = 1


@dataclass
class RefinementSnapshot:
    id: str
    timestamp: str
    description: str
    entry_ids: List[str]
    backup_file: str


@dataclass
class RefinementEvent:
    id: str
    trigger: str
    changes: List[str]
    evidence: str = ""
    outcome: str = ""
    created_at: str = ""


class ImmutablePolicyViolationError(Exception):
    """Raised when an agent attempts to overwrite or delete an immutable base policy."""
    pass


class HarnessStateManager:
    """Manages the durable self-improving harness state with reversible snapshots."""

    def __init__(self, state_dir: str = "data/memory"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "harness_state.json"
        self.snapshots_dir = self.state_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.entries: Dict[str, HarnessEntry] = {}
        self.refinements: List[RefinementSnapshot] = []
        self._load()
        self._ensure_base_safety_policy()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_base_safety_policy(self):
        """Ensures immutable core policies are always present and cannot be modified."""
        base_policies = [
            ("policy_zero_mocks", "Base Safety: Production code must never mock real runtimes or models."),
            ("policy_path_sandbox", "Base Safety: All file writes must remain strictly within workspace boundaries."),
            ("policy_bounded_healing", "Base Safety: Automated repair attempts must never exceed budget ceiling.")
        ]
        modified = False
        for pid, content in base_policies:
            if pid not in self.entries:
                self.entries[pid] = HarnessEntry(
                    id=pid,
                    kind="strategy",
                    name=pid,
                    content=content,
                    created_at=self._now(),
                    updated_at=self._now(),
                    scope="global",
                    immutable=True,
                    source="base_policy"
                )
                modified = True
        if modified:
            self.save()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entries = {
                        k: HarnessEntry(**v)
                        for k, v in data.get("entries", {}).items()
                    }
                    self.refinements = [
                        RefinementSnapshot(**v)
                        for v in data.get("refinements", [])
                    ]
            except Exception as e:
                print(f"[Harness] Warning loading state: {e}")

    def save(self):
        data = {
            "entries": {k: asdict(v) for k, v in self.entries.items()},
            "refinements": [asdict(r) for r in self.refinements],
            "last_updated": self._now()
        }
        temp_file = self.state_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.state_file)

    def create_snapshot(self, description: str) -> RefinementSnapshot:
        snapshot_id = f"snap_{uuid4().hex[:8]}"
        ts = self._now()
        backup_path = self.snapshots_dir / f"{snapshot_id}.json"
        data = {
            "entries": {k: asdict(v) for k, v in self.entries.items()},
            "refinements": [asdict(r) for r in self.refinements],
            "last_updated": ts
        }
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        snapshot = RefinementSnapshot(
            id=snapshot_id,
            timestamp=ts,
            description=description,
            entry_ids=list(self.entries.keys()),
            backup_file=str(backup_path)
        )
        self.refinements.append(snapshot)
        self.save()
        return snapshot

    def rollback(self, snapshot_id: str) -> bool:
        """Alias for rollback_to for compatibility."""
        return self.rollback_to(snapshot_id)

    def rollback_to(self, snapshot_id: str) -> bool:
        for snap in self.refinements:
            if snap.id == snapshot_id:
                if os.path.exists(snap.backup_file):
                    with open(snap.backup_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.entries = {
                        k: HarnessEntry(**v)
                        for k, v in data.get("entries", {}).items()
                    }
                    self.save()
                    return True
        return False

    def add_or_update(
        self,
        kind: HarnessKind,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        snapshot_desc: Optional[str] = None
    ) -> HarnessEntry:
        # Check immutability
        existing = None
        for e in self.entries.values():
            if e.name == name and e.kind == kind:
                existing = e
                break

        if existing and existing.immutable:
            raise ImmutablePolicyViolationError(f"Cannot modify immutable entry: {name}")

        now_str = self._now()
        if existing:
            existing.content = content
            existing.updated_at = now_str
            existing.version += 1
            if metadata:
                existing.metadata.update(metadata)
            entry = existing
        else:
            entry_id = f"{kind}_{uuid4().hex[:8]}"
            entry = HarnessEntry(
                id=entry_id,
                kind=kind,
                name=name,
                content=content,
                created_at=now_str,
                updated_at=now_str,
                metadata=metadata or {}
            )
            self.entries[entry.id] = entry

        if snapshot_desc:
            self.create_snapshot(snapshot_desc)
        else:
            self.save()

        return entry

    def delete_entry(self, entry_id_or_name: str) -> bool:
        target_id = None
        for eid, entry in self.entries.items():
            if eid == entry_id_or_name or entry.name == entry_id_or_name:
                if entry.immutable:
                    raise ImmutablePolicyViolationError(f"Cannot delete immutable policy: {entry.name}")
                target_id = eid
                break

        if target_id:
            del self.entries[target_id]
            self.save()
            return True
        return False

    # Upstream Prime Agent API compatibility methods
    def create_skill(self, name: str, description: str, content: str, reference: Optional[Dict[str, Any]] = None) -> HarnessEntry:
        self.create_snapshot(f"Pre-create skill: {name}")
        meta = {"description": description}
        entry = self.add_or_update("skill", name, content, metadata=meta)
        if reference:
            entry.reference = reference
            self.save()
        return entry

    def update_skill(self, name: str, content: str, reference: Optional[Dict[str, Any]] = None) -> HarnessEntry:
        self.create_snapshot(f"Pre-update skill: {name}")
        entry = self.add_or_update("skill", name, content)
        if reference:
            entry.reference = reference
            self.save()
        return entry

    def delete_skill(self, name: str) -> bool:
        self.create_snapshot(f"Pre-delete skill: {name}")
        return self.delete_entry(name)

    def create_memory(self, key: str, value: str, global_: bool = False) -> HarnessEntry:
        scope: HarnessScope = "global" if global_ else "local"
        entry = self.add_or_update("memory", key, value, metadata={"scope": scope})
        entry.scope = scope
        self.save()
        return entry

    def delete_memory(self, key: str, global_: bool = False) -> bool:
        return self.delete_entry(key)

    def create_strategy(self, name: str, content: str) -> HarnessEntry:
        self.create_snapshot(f"Pre-create strategy: {name}")
        return self.add_or_update("strategy", name, content)

    def delete_strategy(self, name: str) -> bool:
        self.create_snapshot(f"Pre-delete strategy: {name}")
        return self.delete_entry(name)

    def create_subagent(self, role: str, prompt: str) -> HarnessEntry:
        return self.add_or_update("subagent", role, prompt)

    def delete_subagent(self, role: str) -> bool:
        return self.delete_entry(role)

    def create_retrieval(self, key: str, value: str) -> HarnessEntry:
        return self.add_or_update("retrieval", key, value)

    def delete_retrieval(self, key: str) -> bool:
        return self.delete_entry(key)

    def get_harness_state(self, global_: bool = False) -> Dict[str, Any]:
        return {
            "entries": [
                asdict(e) for e in self.entries.values()
                if not global_ or e.scope == "global"
            ],
            "refinements_count": len(self.refinements),
            "state_file": str(self.state_file)
        }


# Global helper function matching upstream signature
def get_harness_state(global_: bool = False, state_dir: str = "data/memory") -> Dict[str, Any]:
    mgr = HarnessStateManager(state_dir=state_dir)
    return mgr.get_harness_state(global_=global_)
