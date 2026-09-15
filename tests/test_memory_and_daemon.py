"""Test Suite for Memory Systems, Goals, and Background Daemon Sessions."""

import asyncio
import pytest
from services.agent.memory import AgentMemorySystem
from services.agent.daemon import PrimeDaemon


def test_multi_tier_memory_and_goals(tmp_path):
    mem = AgentMemorySystem(memory_dir=str(tmp_path))

    # Store in working and episodic memory
    r1 = mem.store("working", "active_context", {"focus": "kernel optimization"})
    r2 = mem.store("episodic", "past_run", {"outcome": "success"})

    assert r1.tier == "working"
    assert r2.tier == "episodic"

    # Query
    working_records = mem.query(tier="working")
    assert len(working_records) == 1
    assert working_records[0].value["focus"] == "kernel optimization"

    # Create and update Goal
    goal = mem.create_goal("Benchmark Vulkan", "Measure token latency")
    assert goal.status == "ACTIVE"

    mem.update_goal(goal.goal_id, "COMPLETED", milestone={"ms": 35.2})
    updated = mem.list_goals(status="COMPLETED")
    assert len(updated) == 1
    assert updated[0].milestones[0]["ms"] == 35.2


@pytest.mark.asyncio
async def test_daemon_session_lifecycle(tmp_path):
    daemon = PrimeDaemon(state_dir=str(tmp_path))
    await daemon.start(heartbeat_interval=0.1)

    sess = daemon.create_session(goal_id="goal_123")
    assert sess.status == "RUNNING"

    # Detach
    daemon.detach_session(sess.session_id)
    assert daemon.sessions[sess.session_id].status == "DETACHED"

    # Resume
    resumed = daemon.resume_session(sess.session_id)
    assert resumed.status == "RUNNING"

    # Stop daemon
    await daemon.stop()
    assert daemon._running is False
