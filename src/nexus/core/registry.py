"""Agent registry — manages agent lifecycle and lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.core.agent import Agent, AgentId, AgentRole


class AgentRegistry:
    """Central registry for all active agents."""

    def __init__(self) -> None:
        self._agents: dict[AgentId, Agent] = {}
        self._by_role: dict[AgentRole, list[Agent]] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.agent_id] = agent
        self._by_role.setdefault(agent.role, []).append(agent)

    def unregister(self, agent_id: AgentId) -> None:
        agent = self._agents.pop(agent_id, None)
        if agent and agent.role in self._by_role:
            self._by_role[agent.role] = [
                a for a in self._by_role[agent.role] if a.agent_id != agent_id
            ]

    def get(self, agent_id: AgentId) -> Agent | None:
        return self._agents.get(agent_id)

    def get_by_role(self, role: AgentRole) -> list[Agent]:
        return self._by_role.get(role, [])

    def get_first_by_role(self, role: AgentRole) -> Agent | None:
        agents = self.get_by_role(role)
        return agents[0] if agents else None

    def all_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)
