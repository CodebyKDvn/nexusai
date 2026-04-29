"""Tool Execution Agent — handles all tool calls on behalf of other agents."""

from __future__ import annotations

import logging

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.message import Message, MessageBus, MessageType
from nexus.core.tool import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutorAgent(Agent):
    """Centralized tool execution agent — receives tool call requests and returns results."""

    def __init__(
        self,
        agent_id: AgentId,
        bus: MessageBus,
        tools: ToolRegistry | None = None,
    ) -> None:
        super().__init__(agent_id, AgentRole.TOOL_EXECUTOR, bus)
        self.tools = tools or ToolRegistry()

    def process(self, message: Message) -> Message | None:
        if message.type != MessageType.TASK_REQUEST:
            return None

        tool_name = message.payload.get("tool", "")
        params = message.payload.get("params", {})

        tool = self.tools.get(tool_name)
        if not tool:
            available = [t.name for t in self.tools.list_tools()]
            return message.reply(
                MessageType.ERROR,
                {
                    "error": f"Unknown tool: {tool_name}",
                    "available_tools": available,
                },
            )

        validation_errors = tool.validate_params(**params)
        if validation_errors:
            return message.reply(
                MessageType.ERROR,
                {"error": "Invalid parameters", "details": validation_errors},
            )

        logger.info("Executing tool %s with params: %s", tool_name, list(params.keys()))
        result = tool.execute(**params)

        return message.reply(
            MessageType.TASK_RESULT,
            {
                "status": "complete" if result.ok else "error",
                "result": result.to_dict(),
                "tool": tool_name,
            },
        )
