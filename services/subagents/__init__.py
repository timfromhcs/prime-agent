"""Prime Subagents Package."""
from services.subagents.protocol import SubagentState, AgentMessage, SubagentHandle
from services.subagents.roles import SUBAGENT_ROLES, SubagentRoleSpec
from services.subagents.manager import SubagentManager

__all__ = [
    "SubagentState",
    "AgentMessage",
    "SubagentHandle",
    "SUBAGENT_ROLES",
    "SubagentRoleSpec",
    "SubagentManager"
]
