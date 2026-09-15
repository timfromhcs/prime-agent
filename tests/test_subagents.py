"""Test Suite for Recursive Subagents and Messaging."""

import pytest
from services.subagents.manager import SubagentManager
from services.subagents.protocol import SubagentState


def test_subagent_spawning_and_recursion_bounds(tmp_path):
    mgr = SubagentManager(base_dir=str(tmp_path), max_depth=3, max_subagents=5)

    # Root -> Child 1
    child1 = mgr.spawn(prompt="Review security architecture", role="security", depth=1)
    assert child1.depth == 1
    assert child1.role == "security"

    # Child 1 -> Child 2
    child2 = mgr.spawn(prompt="Inspect auth tokens", role="coding", parent_id=child1.subagent_id, depth=2)
    assert child2.depth == 2
    assert child2.parent_id == child1.subagent_id

    # Child 2 -> Child 3
    child3 = mgr.spawn(prompt="Check token hashing", role="testing", parent_id=child2.subagent_id, depth=3)
    assert child3.depth == 3

    # Exceeding max depth
    with pytest.raises(ValueError, match="exceeds max allowed depth"):
        mgr.spawn(prompt="Explosion", parent_id=child3.subagent_id, depth=4)


def test_agent_to_agent_messaging(tmp_path):
    mgr = SubagentManager(base_dir=str(tmp_path))
    parent = mgr.spawn(prompt="Coordinate research", role="research")
    child = mgr.spawn(prompt="Extract statistics", role="document", parent_id=parent.subagent_id)

    # Parent to child message
    msg1 = mgr.send_message(
        sender_id=parent.subagent_id,
        recipient_id=child.subagent_id,
        content="Please extract table 2 data."
    )
    assert msg1.sender_id == parent.subagent_id
    assert msg1.recipient_id == child.subagent_id

    # Child reply to parent
    msg2 = mgr.send_message(
        sender_id=child.subagent_id,
        recipient_id=parent.subagent_id,
        content="Table 2 extracted: 45 entries found."
    )
    assert msg2.content == "Table 2 extracted: 45 entries found."

    # Verify message tracking
    messages = mgr.get_messages_for(child.subagent_id)
    assert len(messages) == 2

    # State transitions
    mgr.update_state(child.subagent_id, SubagentState.COMPLETED, findings=["Table 2 processed"])
    assert mgr.subagents[child.subagent_id].state == SubagentState.COMPLETED
    assert "Table 2 processed" in mgr.subagents[child.subagent_id].findings
