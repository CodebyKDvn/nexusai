"""API calling tool — makes HTTP requests."""

from __future__ import annotations

import json
from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


class APITool(Tool):
    name = "api_call"
    description = "Make an HTTP API request and return the response."
    parameters = [
        ToolParam(name="url", type="string", description="API endpoint URL"),
        ToolParam(
            name="method",
            type="string",
            description="HTTP method (GET, POST, PUT, DELETE)",
            required=False,
            default="GET",
        ),
        ToolParam(
            name="headers",
            type="object",
            description="Request headers as JSON object",
            required=False,
            default=None,
        ),
        ToolParam(
            name="body",
            type="string",
            description="Request body (JSON string)",
            required=False,
            default=None,
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        url = params["url"]
        method = params.get("method", "GET").upper()
        headers = params.get("headers") or {}
        body = params.get("body")

        try:
            import httpx

            with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                kwargs: dict[str, Any] = {"headers": headers}
                if body and method in ("POST", "PUT", "PATCH"):
                    kwargs["content"] = body
                    if "content-type" not in {k.lower() for k in headers}:
                        headers["Content-Type"] = "application/json"

                response = client.request(method, url, **kwargs)

            try:
                resp_body = response.json()
            except (json.JSONDecodeError, ValueError):
                resp_body = response.text

            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=resp_body,
                metadata={
                    "url": url,
                    "method": method,
                    "status_code": response.status_code,
                },
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=f"API call failed: {e}")
