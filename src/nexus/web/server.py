"""FastAPI server for Nexus AI web chat interface."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from nexus.config import NexusConfig
from nexus.team import NexusTeam

if TYPE_CHECKING:
    from nexus.core.message import Message

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: NexusConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = config or NexusConfig()
    team = NexusTeam(cfg)

    app = FastAPI(
        title="Nexus AI",
        description="Multi-Agent AI Development Platform",
        version="0.1.0",
    )

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    manager = ConnectionManager()

    def on_bus_message(msg: Message) -> None:
        """Forward agent bus messages to all connected WebSocket clients."""
        payload = msg.payload
        content = str(
            payload.get("task")
            or payload.get("result")
            or payload.get("error")
            or payload
        )
        ws_msg: dict[str, Any] = {
            "type": "agent_message",
            "sender": msg.sender,
            "recipient": msg.recipient,
            "msg_type": msg.type.value,
            "content": content,
            "timestamp": msg.timestamp.isoformat(),
        }
        if manager.loop is not None:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps(ws_msg)),
                loop=manager.loop,
            )

    team.bus.subscribe("__broadcast__", on_bus_message)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        agents = [
            {"id": a.agent_id, "role": a.role.value}
            for a in team.registry.all_agents()
        ]
        return {
            "status": "ready",
            "agent_count": team.agent_count,
            "agents": agents,
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "has_api_key": bool(cfg.llm.api_key),
        }

    @app.get("/api/crew")
    async def crew_analyze(task: str = "") -> dict[str, Any]:
        if not task:
            return {"error": "Provide a 'task' query parameter"}
        assignment = team.crew_assembler.assemble(task)
        return {
            "category": assignment.category.value,
            "agents": assignment.agents,
            "parallel": assignment.parallel,
            "confidence": assignment.confidence,
            "reasoning": assignment.reasoning,
        }

    @app.get("/api/task-graph")
    async def task_graph_status() -> dict[str, Any]:
        return team.task_graph.summary()

    # --- Reliability & Production-grade (Group 2) endpoints ---

    @app.get("/api/approval-gates")
    async def approval_gates_status() -> dict[str, Any]:
        return team.approval_gates.summary()

    @app.get("/api/approval-gates/pending")
    async def approval_pending() -> list[dict[str, Any]]:
        return [r.to_dict() for r in team.approval_gates.pending_requests]

    @app.post("/api/approval-gates/{request_id}")
    async def approval_resolve(
        request_id: str,
        approved: bool = True,
        comment: str = "",
    ) -> dict[str, Any]:
        result = team.approval_gates.resolve(
            request_id, approved=approved, comment=comment,
        )
        if result is None:
            return {"error": f"Request {request_id} not found"}
        return result.to_dict()

    @app.get("/api/evaluations")
    async def evaluations(limit: int = 20) -> dict[str, Any]:
        return team.evaluator.logger.summary()

    @app.get("/api/observability")
    async def observability() -> dict[str, Any]:
        return team.tracer.summary()

    @app.get("/api/observability/traces")
    async def traces(limit: int = 20) -> list[dict[str, Any]]:
        return [t.to_dict() for t in team.tracer.store.recent(limit)]

    @app.get("/api/recovery")
    async def recovery_status() -> dict[str, Any]:
        if team.recovery is None:
            return {"total_recoveries": 0}
        return team.recovery.summary()

    @app.get("/api/memory")
    async def memory(query: str = "") -> dict[str, Any]:
        if query:
            memories = team.memory.recall(query)
            return {
                "results": [
                    {
                        "content": m.content[:500],
                        "category": m.metadata.get("category", "unknown"),
                    }
                    for m in memories
                ]
            }
        return {
            "short_term_size": team.memory.short_term.size,
            "recent": team.memory.short_term.get_context_string(5),
        }

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        session_id = str(uuid.uuid4())[:8]
        logger.info("WebSocket connected: %s", session_id)

        await websocket.send_json({
            "type": "system",
            "content": "Connected to Nexus AI. Send your request to start collaborating.",
            "agents": [a.agent_id for a in team.registry.all_agents()],
        })

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    msg = {"message": data}

                user_message = msg.get("message", "").strip()
                if not user_message:
                    continue

                await websocket.send_json({
                    "type": "status",
                    "content": "Processing your request...",
                    "status": "thinking",
                })

                loop = asyncio.get_event_loop()
                try:
                    result = await loop.run_in_executor(None, team.run, user_message)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Error: {e}",
                    })
                    continue

                output = result.get("output", "Task completed.")
                if isinstance(output, dict):
                    output = json.dumps(output, indent=2)

                await websocket.send_json({
                    "type": "result",
                    "content": str(output),
                    "completed": result.get("completed", False),
                    "iterations": result.get("iterations", 0),
                    "errors": result.get("errors", []),
                })

        except WebSocketDisconnect:
            manager.disconnect(websocket)
            logger.info("WebSocket disconnected: %s", session_id)

    return app


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)
        if self.loop is None:
            self.loop = asyncio.get_event_loop()

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: str) -> None:
        disconnected: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)
