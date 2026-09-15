"""Test Suite for Bounded Self-Healing Cycle."""

import pytest
from services.agent.self_healing import SelfHealingCoordinator


@pytest.mark.asyncio
async def test_self_healing_recovery_cycle():
    coordinator = SelfHealingCoordinator(max_repair_attempts=3)

    # Controlled fixture that fails initially then succeeds on attempt 2
    fixture_state = {"syntax_error": True, "attempts": 0}

    def diagnose(task_id: str, error: str):
        return "Syntax error: missing closing parenthesis"

    def repair(task_id: str, diagnosis: str):
        fixture_state["attempts"] += 1
        if fixture_state["attempts"] >= 2:
            fixture_state["syntax_error"] = False
        return "Fixed parenthesis"

    def run_tests():
        if fixture_state["syntax_error"]:
            return {"passed": False, "evidence": "SyntaxError on line 5"}
        return {"passed": True, "evidence": "All 3 unit tests passed."}

    session = await coordinator.run_healing_cycle(
        task_id="heal_test_1",
        initial_error="Initial build failure: SyntaxError",
        diagnose_fn=diagnose,
        repair_fn=repair,
        test_fn=run_tests
    )

    assert session.final_status == "RESOLVED"
    assert len(session.attempts) == 2
    assert session.attempts[1].retest_status == "PASS"


@pytest.mark.asyncio
async def test_self_healing_bounded_budget_exhaustion():
    coordinator = SelfHealingCoordinator(max_repair_attempts=2)

    def diagnose(task_id, error):
        return "Hardware bus failure"

    def repair(task_id, diagnosis):
        return "Attempted reboot"

    def run_tests():
        return {"passed": False, "evidence": "Hardware still uncommunicative"}

    session = await coordinator.run_healing_cycle(
        task_id="heal_test_fail",
        initial_error="Bus communication error",
        diagnose_fn=diagnose,
        repair_fn=repair,
        test_fn=run_tests
    )

    assert session.final_status == "FAILED_WITH_EVIDENCE"
    assert session.budget_exhausted is True
    assert len(session.attempts) == 2
