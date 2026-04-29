"""Critic/Reflection Agent — evaluates outputs and drives self-improvement."""

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


class CriticAgent(Agent):
    """Evaluates outputs, suggests improvements, and drives learning."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        llm: LLMProvider | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.CRITIC, bus, memory)
        self.llm = llm

    @property
    def system_prompt(self) -> str:
        return """You are the Critic Agent. Your job is to evaluate the quality of outputs
from other agents and drive continuous improvement.

Evaluation criteria:
1. Correctness: Does the output solve the stated problem?
2. Completeness: Are all requirements addressed?
3. Code quality: Is the code clean, well-structured, and maintainable?
4. Performance: Are there obvious performance issues?
5. Security: Are there security concerns?
6. Testing: Is the solution adequately tested?

Respond with:
{
    "scores": {
        "correctness": 0-10,
        "completeness": 0-10,
        "code_quality": 0-10,
        "performance": 0-10,
        "security": 0-10,
        "testing": 0-10
    },
    "overall_score": 0-10,
    "strengths": ["list of strengths"],
    "improvements": ["list of improvements"],
    "verdict": "approve" | "revise",
    "lessons_learned": ["insights for future tasks"]
}"""

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        content = message.payload.get("content", "")
        task = message.payload.get("task", "")

        evaluation = (
            self._evaluate_with_llm(task, content) if self.llm else self._evaluate_stub(content)
        )

        if self.memory:
            lessons = evaluation.get("lessons_learned", [])
            for lesson in lessons:
                self.memory.store_reflection(
                    lesson,
                    task=task[:200],
                    score=evaluation.get("overall_score", 0.0),
                )

        return message.reply(
            MessageType.TASK_RESULT,
            {
                "status": "complete",
                "result": evaluation,
            },
        )

    def _evaluate_with_llm(self, task: str, content: str) -> dict[str, Any]:
        from nexus.llm.provider import LLMMessage

        assert self.llm is not None
        context = ""
        if self.memory:
            context = self.memory.build_context(f"evaluate {task}")

        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=(
                    f"Evaluate this output:\n\nTask: {task}\n\n"
                    f"Output:\n{content}\n\n"
                    f"Context:\n{context}"
                ),
            ),
        ]
        response = self.llm.chat(messages)

        try:
            result: dict[str, Any] = json.loads(response.content)
            return result
        except json.JSONDecodeError:
            return {
                "overall_score": 5.0,
                "verdict": "revise",
                "raw_feedback": response.content,
                "lessons_learned": [],
            }

    def _evaluate_stub(self, content: str) -> dict[str, Any]:
        has_content = bool(content and len(content) > 10)
        return {
            "scores": {
                "correctness": 7 if has_content else 3,
                "completeness": 6 if has_content else 2,
                "code_quality": 7 if has_content else 5,
                "performance": 7,
                "security": 7,
                "testing": 5,
            },
            "overall_score": 6.5 if has_content else 4.0,
            "strengths": ["Output was generated"] if has_content else [],
            "improvements": [
                "Add more comprehensive error handling",
                "Increase test coverage",
            ],
            "verdict": "approve" if has_content else "revise",
            "lessons_learned": [
                "Always validate inputs",
                "Include edge case handling",
            ],
        }
