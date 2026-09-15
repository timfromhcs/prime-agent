"""Self-Healing Engine for Prime Agent.

Executes continuous bounded self-repair cycles:
DISCOVER -> PLAN -> IMPLEMENT -> TEST -> OBSERVE -> DIAGNOSE -> REPAIR -> RETEST -> VERIFY -> CONTINUE
Enforces transactional reversible repair: pre-repair snapshot + rollback upon failure.
"""

from __future__ import annotations
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from services.rlm.harness import HarnessStateManager


@dataclass
class RepairAttempt:
    attempt_number: int
    diagnosis: str
    action_taken: str
    retest_status: str
    evidence: str
    timestamp: str


@dataclass
class HealingSession:
    task_id: str
    initial_failure: str
    attempts: List[RepairAttempt] = field(default_factory=list)
    final_status: str = "IN_PROGRESS"  # "RESOLVED" | "FAILED_WITH_EVIDENCE"
    budget_exhausted: bool = False
    rolled_back: bool = False
    snapshot_id: Optional[str] = None


class SelfHealingCoordinator:
    """Orchestrates bounded diagnosis, repair, re-testing, and regression verification with rollback."""

    def __init__(self, max_repair_attempts: int = 3, harness: Optional[HarnessStateManager] = None):
        self.max_attempts = max_repair_attempts
        self.harness = harness
        self.sessions: Dict[str, HealingSession] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def run_healing_cycle(
        self,
        task_id: str,
        initial_error: str,
        diagnose_fn: Callable[[str, str], Any],
        repair_fn: Callable[[str, Any], Any],
        test_fn: Callable[[], Any]
    ) -> HealingSession:
        session = HealingSession(task_id=task_id, initial_failure=initial_error)
        self.sessions[task_id] = session

        # Take pre-repair transactional snapshot if harness available
        pre_snap = None
        if self.harness:
            pre_snap = self.harness.create_snapshot(f"pre_repair_{task_id}")
            session.snapshot_id = pre_snap.id

        current_error = initial_error

        for attempt in range(1, self.max_attempts + 1):
            # 1. DIAGNOSE
            diagnosis = await diagnose_fn(task_id, current_error) if asyncio.iscoroutinefunction(diagnose_fn) else diagnose_fn(task_id, current_error)

            # 2. REPAIR
            action = await repair_fn(task_id, diagnosis) if asyncio.iscoroutinefunction(repair_fn) else repair_fn(task_id, diagnosis)

            # 3. RETEST
            test_res = await test_fn() if asyncio.iscoroutinefunction(test_fn) else test_fn()
            passed = test_res.get("passed", False) if isinstance(test_res, dict) else bool(test_res)
            evidence = test_res.get("evidence", "") if isinstance(test_res, dict) else str(test_res)

            record = RepairAttempt(
                attempt_number=attempt,
                diagnosis=str(diagnosis),
                action_taken=str(action),
                retest_status="PASS" if passed else "FAIL",
                evidence=evidence,
                timestamp=self._now()
            )
            session.attempts.append(record)

            if passed:
                session.final_status = "RESOLVED"
                return session
            else:
                current_error = evidence

        session.final_status = "FAILED_WITH_EVIDENCE"
        session.budget_exhausted = True

        # Rollback to pre-repair state upon failure
        if self.harness and pre_snap:
            self.harness.rollback_to(pre_snap.id)
            session.rolled_back = True

        return session
