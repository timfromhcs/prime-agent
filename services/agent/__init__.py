"""Prime Agent Services Package (lazy — heavy backends import on first use)."""

from typing import Any

_LAZY = {
    "AgentMemorySystem": "services.agent.memory",
    "MemoryRecord": "services.agent.memory",
    "GoalItem": "services.agent.memory",
    "VerificationEngine": "services.agent.verifier",
    "VerifiedClaim": "services.agent.verifier",
    "SelfHealingCoordinator": "services.agent.self_healing",
    "HealingSession": "services.agent.self_healing",
    "AgentScheduler": "services.agent.scheduler",
    "ScheduledTask": "services.agent.scheduler",
    "PrimeDaemon": "services.agent.daemon",
    "SessionState": "services.agent.daemon",
    "PrimeAgent": "services.agent.root_agent",
    "TurnResult": "services.agent.root_agent",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib
        mod = importlib.import_module(_LAZY[name])
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
