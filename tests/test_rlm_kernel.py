"""Test Suite for Persistent Python RLM Kernel and Namespace State."""

import os
import pytest
from services.rlm.repl import ReplSession
from services.rlm.harness import HarnessStateManager


@pytest.mark.asyncio
async def test_repl_variable_persistence_and_await():
    session = ReplSession(session_id="test_persistence")

    # Cell 1: Define variables and imports
    cell1 = """
import math
base_value = 100
multiplier = 3.5
calculated = base_value * multiplier
"""
    res1 = await session.execute(cell1)
    assert res1["status"] == "ok"

    # Cell 2: Use previously defined variables with top-level await
    cell2 = """
import asyncio
await asyncio.sleep(0.01)
final_val = calculated + 50
final_val
"""
    res2 = await session.execute(cell2)
    assert res2["status"] == "ok"
    assert res2["result"] == "400.0"
    assert session.namespace["final_val"] == 400.0


@pytest.mark.asyncio
async def test_repl_snapshot_and_restore(tmp_path):
    session1 = ReplSession(session_id="test_snap_1")
    await session1.execute("alpha = 42\nbeta = {'agent': 'prime', 'version': 2}")

    snap_file = str(tmp_path / "snap.dill")
    snap_res = session1.snapshot(snap_file)
    assert snap_res["status"] == "ok"
    assert "alpha" in snap_res["saved"]
    assert "beta" in snap_res["saved"]

    # Restore in new session
    session2 = ReplSession(session_id="test_snap_2")
    restore_res = session2.restore(snap_file)
    assert restore_res["status"] == "ok"
    assert session2.namespace.get("alpha") == 42
    assert session2.namespace.get("beta") == {"agent": "prime", "version": 2}


def test_harness_state_snapshots(tmp_path):
    mgr = HarnessStateManager(state_dir=str(tmp_path))
    entry = mgr.add_or_update(
        kind="skill",
        name="test_skill",
        content="Always write rigorous unit tests.",
        snapshot_desc="Initial skill setup"
    )
    assert entry.name == "test_skill"
    assert len(mgr.refinements) == 1

    # Modify skill
    mgr.add_or_update(
        kind="skill",
        name="test_skill",
        content="Updated skill instructions.",
        snapshot_desc="Updated skill"
    )
    assert len(mgr.refinements) == 2

    # Rollback
    first_snap_id = mgr.refinements[0].id
    rolled = mgr.rollback(first_snap_id)
    assert rolled is True
    assert mgr.entries[entry.id].content == "Always write rigorous unit tests."
