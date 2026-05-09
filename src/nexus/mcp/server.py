"""MCP Server — FastAPI-based server exposing all MCP tools.

Implements a JSON-RPC 2.0 compatible MCP server that agents can connect to
for tool discovery and execution.
"""

from __future__ import annotations

import logging
from typing import Any

from nexus.mcp.skill_store import SkillStore
from nexus.mcp.tools import ALL_MCP_TOOLS

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP-compliant server that exposes Nexus Skill-Core tools.

    Provides:
      - tools/list:  Enumerate all available tools with schemas
      - tools/call:  Execute a tool by name with arguments
      - Health check endpoint
    """

    def __init__(self, skill_store: SkillStore | None = None) -> None:
        self._store = skill_store or SkillStore()
        # Register all built-in tools
        self._store.register_all(ALL_MCP_TOOLS)

    @property
    def store(self) -> SkillStore:
        return self._store

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC 2.0 MCP request.

        Supported methods:
          - initialize
          - tools/list
          - tools/call
        """
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return self._response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "nexus-skill-core",
                    "version": "0.1.0",
                },
            })

        if method == "tools/list":
            tools = self._store.list_schemas()
            return self._response(req_id, {"tools": tools})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self._store.execute(tool_name, **arguments)
            return self._response(req_id, {
                "content": result.content,
                "isError": result.is_error,
            })

        return self._error(req_id, -32601, f"Unknown method: {method}")

    def create_app(self) -> Any:
        """Create a FastAPI application exposing this MCP server."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        app = FastAPI(
            title="Nexus Skill-Core MCP Server",
            description="MCP-compliant tool server with NVIDIA NIM reasoning",
            version="0.1.0",
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "tool_count": len(self._store.list_tools()),
                "nvidia_configured": self._store.nvidia_wrapper.is_configured,
            }

        @app.get("/tools")
        async def list_tools() -> dict[str, Any]:
            return {"tools": self._store.list_schemas()}

        @app.post("/mcp")
        async def mcp_endpoint(request: dict[str, Any]) -> dict[str, Any]:
            return self.handle_request(request)

        @app.post("/tools/{tool_name}")
        async def call_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
            result = self._store.execute(tool_name, **params)
            return {
                "content": result.content,
                "isError": result.is_error,
            }

        return app

    @staticmethod
    def _response(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
