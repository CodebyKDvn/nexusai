"""Web browsing tool — fetches and parses web content."""

from __future__ import annotations

from typing import Any

from nexus.core.tool import Tool, ToolParam, ToolResult, ToolStatus


class BrowserTool(Tool):
    name = "browser"
    description = "Fetch a web page and return its text content."
    parameters = [
        ToolParam(name="url", type="string", description="URL to fetch"),
        ToolParam(
            name="max_length",
            type="integer",
            description="Max characters to return",
            required=False,
            default=10000,
        ),
    ]

    def execute(self, **params: Any) -> ToolResult:
        url = params["url"]
        max_length = params.get("max_length", 10000)

        try:
            import httpx

            with httpx.Client(follow_redirects=True, timeout=15.0) as client:
                response = client.get(
                    url,
                    headers={"User-Agent": "NexusAI/0.1 (research-agent)"},
                )
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            text = response.text

            if "text/html" in content_type:
                text = self._extract_text(text)

            if len(text) > max_length:
                text = text[:max_length] + "\n... (truncated)"

            return ToolResult(
                status=ToolStatus.SUCCESS,
                output=text,
                metadata={
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": content_type,
                },
            )
        except Exception as e:
            return ToolResult(status=ToolStatus.ERROR, error=f"Failed to fetch {url}: {e}")

    @staticmethod
    def _extract_text(html: str) -> str:
        import re

        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
