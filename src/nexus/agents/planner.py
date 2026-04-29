"""Planner Agent — breaks down tasks into structured plans with milestones."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import Message, MessageBus, MessageType

if TYPE_CHECKING:
    from nexus.llm.provider import LLMProvider
    from nexus.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    """Decomposes complex tasks into structured, actionable plans."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.PLANNER, bus, memory)
        self.llm = llm

    @property
    def system_prompt(self) -> str:
        return """You are the Planner Agent. Your job is to decompose complex tasks into
structured, actionable plans.

For every task, produce a JSON plan:
{
    "goal": "High-level objective",
    "steps": [
        {
            "id": 1,
            "description": "Step description",
            "agent": "developer|debugger|qa|research",
            "dependencies": [],
            "estimated_complexity": "low|medium|high"
        }
    ],
    "milestones": [
        {"name": "Milestone name", "after_steps": [1, 2]}
    ],
    "risks": ["Potential risk 1"]
}

Rules:
- Break large tasks into 3-10 steps
- Identify dependencies between steps
- Assign each step to the most appropriate agent
- Flag risks and unknowns"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        task = message.payload.get("task", "")
        context = message.payload.get("context", "")

        if self.memory:
            past_plans = self.memory.recall(
                task, collections=["decisions"], n_results=3
            )
            if past_plans:
                context += "\n\nRelevant past decisions:\n"
                for mem in past_plans:
                    context += f"- {mem.content}\n"

        plan = self._plan_with_llm(task, context) if self.llm else self._plan_rule_based(task)

        if self.memory:
            self.memory.store_decision(
                f"Plan for: {task[:100]}",
                rationale=json.dumps(plan, indent=2)[:500],
            )

        return message.reply(
            MessageType.TASK_RESULT,
            {"status": "complete", "result": plan, "plan": plan},
        )

    def _plan_with_llm(self, task: str, context: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Create a plan for: {task}\n\nContext:\n{context}",
            ),
        ]
        response = self.llm.chat(messages)

        try:
            result: dict[str, Any] = json.loads(response.content)
            return result
        except json.JSONDecodeError:
            return {
                "goal": task,
                "steps": [
                    {
                        "id": 1,
                        "description": task,
                        "agent": "developer",
                        "dependencies": [],
                        "estimated_complexity": "medium",
                    }
                ],
                "milestones": [],
                "risks": [],
                "raw_response": response.content,
            }

    def _plan_rule_based(self, task: str) -> dict[str, Any]:
        steps = []
        step_id = 1

        steps.append({
            "id": step_id,
            "description": f"Research and understand requirements: {task[:100]}",
            "agent": "research",
            "dependencies": [],
            "estimated_complexity": "low",
        })
        step_id += 1

        steps.append({
            "id": step_id,
            "description": "Design the solution architecture",
            "agent": "developer",
            "dependencies": [1],
            "estimated_complexity": "medium",
        })
        step_id += 1

        steps.append({
            "id": step_id,
            "description": "Implement the solution",
            "agent": "developer",
            "dependencies": [2],
            "estimated_complexity": "high",
        })
        step_id += 1

        steps.append({
            "id": step_id,
            "description": "Write tests",
            "agent": "qa",
            "dependencies": [3],
            "estimated_complexity": "medium",
        })
        step_id += 1

        steps.append({
            "id": step_id,
            "description": "Review and refine",
            "agent": "critic",
            "dependencies": [3, 4],
            "estimated_complexity": "low",
        })

        return {
            "goal": task,
            "steps": steps,
            "milestones": [
                {"name": "Design complete", "after_steps": [2]},
                {"name": "Implementation complete", "after_steps": [3]},
                {"name": "Quality validated", "after_steps": [4, 5]},
            ],
            "risks": [
                "Requirements may be ambiguous",
                "Implementation complexity may be underestimated",
            ],
        }
