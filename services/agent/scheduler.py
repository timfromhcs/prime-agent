"""Background Task Scheduler for Prime Agent.

Supports bounded periodic background tasks (audits, RAG syncs, health checks).
"""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    interval_seconds: float
    fn: Callable[[], Any]
    last_run: float = 0.0
    run_count: int = 0
    max_runs: Optional[int] = None
    active: bool = True
    last_result: Any = None


class AgentScheduler:
    """Manages scheduled periodic maintenance and audit tasks."""

    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._task_handle: Optional[asyncio.Task] = None

    def schedule(
        self,
        name: str,
        interval_seconds: float,
        fn: Callable[[], Any],
        max_runs: Optional[int] = None
    ) -> str:
        tid = f"sched_{uuid4().hex[:8]}"
        task = ScheduledTask(
            task_id=tid,
            name=name,
            interval_seconds=interval_seconds,
            fn=fn,
            max_runs=max_runs
        )
        self.tasks[tid] = task
        return tid

    async def start(self):
        self._running = True
        self._task_handle = asyncio.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task_handle:
            self._task_handle.cancel()

    async def _loop(self):
        while self._running:
            now = time.time()
            for tid, t in list(self.tasks.items()):
                if not t.active:
                    continue
                if now - t.last_run >= t.interval_seconds:
                    t.last_run = now
                    t.run_count += 1
                    try:
                        if asyncio.iscoroutinefunction(t.fn):
                            t.last_result = await t.fn()
                        else:
                            t.last_result = t.fn()
                    except Exception as exc:
                        t.last_result = f"Error: {exc}"

                    if t.max_runs and t.run_count >= t.max_runs:
                        t.active = False
            await asyncio.sleep(1.0)
