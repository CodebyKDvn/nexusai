"""Tests for core framework: messages, agents, registry, loop."""

from __future__ import annotations

from nexus.core.agent import Agent, AgentId, AgentRole
from nexus.core.loop import AgentLoop
from nexus.core.message import BROADCAST, Message, MessageBus, MessageType
from nexus.core.registry import AgentRegistry


class EchoAgent(Agent):
    """Simple agent that echoes task requests back as results."""

    def process(self, message: Message) -> Message | None:
        if message.type == MessageType.TASK_REQUEST:
            return message.reply(
                MessageType.TASK_RESULT,
                {"status": "complete", "result": f"Echo: {message.payload.get('task', '')}"},
            )
        return None


class ForwardingAgent(Agent):
    """Agent that forwards tasks to another agent."""

    def __init__(self, agent_id: AgentId, role: AgentRole, bus: MessageBus, target: str) -> None:
        super().__init__(agent_id, role, bus)
        self.target = target

    def process(self, message: Message) -> Message | None:
        if message.type == MessageType.TASK_REQUEST:
            return self.send(
                self.target,
                MessageType.TASK_REQUEST,
                message.payload,
                correlation_id=message.correlation_id or message.id,
            )
        return None


class TestMessageBus:
    def test_publish_subscribe(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        bus.subscribe("agent-1", lambda m: received.append(m))

        msg = Message(
            sender="user",
            recipient="agent-1",
            type=MessageType.TASK_REQUEST,
            payload={"task": "hello"},
        )
        bus.publish(msg)

        assert len(received) == 1
        assert received[0].payload["task"] == "hello"

    def test_broadcast(self) -> None:
        bus = MessageBus()
        received: list[Message] = []

        bus.subscribe(BROADCAST, lambda m: received.append(m))

        msg = Message(
            sender="user",
            recipient="agent-1",
            type=MessageType.TASK_REQUEST,
            payload={"task": "broadcast test"},
        )
        bus.publish(msg)

        assert len(received) == 1

    def test_history(self) -> None:
        bus = MessageBus()

        for i in range(5):
            bus.publish(
                Message(
                    sender="user",
                    recipient="agent-1",
                    type=MessageType.TASK_REQUEST,
                    payload={"task": f"task-{i}"},
                )
            )

        history = bus.get_history(sender="user")
        assert len(history) == 5

        history = bus.get_history(limit=3)
        assert len(history) == 3

    def test_unsubscribe(self) -> None:
        bus = MessageBus()
        received: list[Message] = []
        def handler(m: Message) -> None:
            received.append(m)

        bus.subscribe("agent-1", handler)
        bus.publish(
            Message(
                sender="user",
                recipient="agent-1",
                type=MessageType.TASK_REQUEST,
                payload={},
            )
        )
        assert len(received) == 1

        bus.unsubscribe("agent-1", handler)
        bus.publish(
            Message(
                sender="user",
                recipient="agent-1",
                type=MessageType.TASK_REQUEST,
                payload={},
            )
        )
        assert len(received) == 1


class TestMessage:
    def test_reply(self) -> None:
        msg = Message(
            sender="user",
            recipient="orchestrator",
            type=MessageType.TASK_REQUEST,
            payload={"task": "test"},
        )
        reply = msg.reply(MessageType.TASK_RESULT, {"status": "complete"})

        assert reply.sender == "orchestrator"
        assert reply.recipient == "user"
        assert reply.type == MessageType.TASK_RESULT
        assert reply.correlation_id == msg.id

    def test_to_dict(self) -> None:
        msg = Message(
            sender="user",
            recipient="agent-1",
            type=MessageType.TASK_REQUEST,
            payload={"task": "hello"},
        )
        d = msg.to_dict()
        assert d["sender"] == "user"
        assert d["type"] == "task_request"


class TestAgentRegistry:
    def test_register_and_lookup(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        agent = EchoAgent("echo-1", AgentRole.DEVELOPER, bus)
        registry.register(agent)

        assert registry.get("echo-1") is agent
        assert registry.get("nonexistent") is None
        assert len(registry) == 1

    def test_by_role(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        a1 = EchoAgent("dev-1", AgentRole.DEVELOPER, bus)
        a2 = EchoAgent("dev-2", AgentRole.DEVELOPER, bus)
        a3 = EchoAgent("qa-1", AgentRole.QA, bus)

        registry.register(a1)
        registry.register(a2)
        registry.register(a3)

        devs = registry.get_by_role(AgentRole.DEVELOPER)
        assert len(devs) == 2

        qas = registry.get_by_role(AgentRole.QA)
        assert len(qas) == 1

    def test_unregister(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        agent = EchoAgent("echo-1", AgentRole.DEVELOPER, bus)
        registry.register(agent)
        assert len(registry) == 1

        registry.unregister("echo-1")
        assert len(registry) == 0
        assert registry.get("echo-1") is None


class TestAgentLoop:
    def test_simple_echo(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        agent = EchoAgent("echo", AgentRole.DEVELOPER, bus)
        registry.register(agent)

        msg = Message(
            sender="user",
            recipient="echo",
            type=MessageType.TASK_REQUEST,
            payload={"task": "hello world"},
        )

        loop = AgentLoop(registry, max_iterations=10)
        state = loop.run(msg)

        assert state.completed
        assert state.iteration >= 1
        assert len(state.results) > 0

    def test_agent_not_found(self) -> None:
        registry = AgentRegistry()

        msg = Message(
            sender="user",
            recipient="nonexistent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "hello"},
        )

        loop = AgentLoop(registry, max_iterations=5)
        state = loop.run(msg)

        assert state.completed
        assert len(state.errors) > 0

    def test_multi_agent_chain(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        forwarder = ForwardingAgent(
            "forwarder", AgentRole.ORCHESTRATOR, bus, target="echo"
        )
        echo = EchoAgent("echo", AgentRole.DEVELOPER, bus)

        registry.register(forwarder)
        registry.register(echo)

        msg = Message(
            sender="user",
            recipient="forwarder",
            type=MessageType.TASK_REQUEST,
            payload={"task": "chain test"},
        )

        loop = AgentLoop(registry, max_iterations=10)
        state = loop.run(msg)

        assert state.completed
        assert state.iteration >= 2

    def test_max_iterations(self) -> None:
        bus = MessageBus()
        registry = AgentRegistry()

        forwarder_a = ForwardingAgent(
            "a", AgentRole.ORCHESTRATOR, bus, target="b"
        )
        forwarder_b = ForwardingAgent(
            "b", AgentRole.PLANNER, bus, target="a"
        )

        registry.register(forwarder_a)
        registry.register(forwarder_b)

        msg = Message(
            sender="user",
            recipient="a",
            type=MessageType.TASK_REQUEST,
            payload={"task": "infinite loop"},
        )

        loop = AgentLoop(registry, max_iterations=5)
        state = loop.run(msg)

        assert not state.completed
        assert state.iteration == 5
