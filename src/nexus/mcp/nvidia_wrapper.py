"""NVIDIA NIM wrapper for LLM-driven reasoning in MCP tools.

All LLM-driven reasoning for Nexus Skill-Core tools is routed through
the NVIDIA API (NIM) using OpenAI-compatible endpoints.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/llama-3.1-405b-instruct"


class NvidiaToolWrapper:
    """Handles all LLM-driven reasoning for MCP tools via NVIDIA NIM.

    This wrapper centralizes LLM calls so that any tool requiring AI reasoning
    (code refactoring, semantic search, code explanation, etc.) goes through
    a single, consistent interface backed by NVIDIA NIM models.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = NVIDIA_NIM_BASE_URL,
    ) -> None:
        self._api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self._model = model
        self._base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    def reason(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,
    ) -> str:
        """Send a reasoning request to NVIDIA NIM and return the text response.

        Args:
            system_prompt: System-level instructions for the model.
            user_prompt: The user's request/question.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            response_format: If "json", request JSON output.

        Returns:
            The model's text response.

        Raises:
            RuntimeError: If no NVIDIA API key is configured.
        """
        if not self._api_key:
            raise RuntimeError(
                "NVIDIA API key not configured. "
                "Set NVIDIA_API_KEY environment variable or pass api_key to NvidiaToolWrapper."
            )

        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        content: str = response.choices[0].message.content or ""
        return content

    def reason_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Send a reasoning request and parse JSON response.

        Returns:
            Parsed JSON dict from the model's response.
        """
        text = self.reason(
            system_prompt,
            user_prompt,
            temperature=temperature,
            response_format="json",
        )
        try:
            result: dict[str, Any] = json.loads(text)
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from NVIDIA NIM response: %s", text[:200])
            return {"raw_response": text, "parse_error": True}

    def code_transform(
        self,
        code: str,
        instruction: str,
        language: str = "python",
    ) -> str:
        """Transform code according to instructions using NVIDIA NIM.

        Args:
            code: The source code to transform.
            instruction: What transformation to apply.
            language: Programming language of the code.

        Returns:
            The transformed code.
        """
        system_prompt = (
            f"You are an expert {language} programmer. Transform the given code "
            "according to the instruction. Return ONLY the transformed code, "
            "no explanations or markdown fences."
        )
        user_prompt = f"Instruction: {instruction}\n\nCode:\n```{language}\n{code}\n```"
        return self.reason(system_prompt, user_prompt, temperature=0.1)

    def explain_code(self, code: str, language: str = "python") -> str:
        """Explain what a piece of code does using NVIDIA NIM."""
        system_prompt = (
            f"You are an expert {language} programmer. Explain the given code clearly "
            "and concisely. Focus on what it does, its key logic, and any notable patterns."
        )
        return self.reason(system_prompt, f"```{language}\n{code}\n```")

    def suggest_fix(self, code: str, error: str, language: str = "python") -> str:
        """Suggest a fix for code that produces an error."""
        system_prompt = (
            f"You are an expert {language} debugger. Given code that produces an error, "
            "provide the fixed code. Return ONLY the fixed code, no explanations."
        )
        user_prompt = f"Error:\n{error}\n\nCode:\n```{language}\n{code}\n```"
        return self.reason(system_prompt, user_prompt, temperature=0.1)

    def semantic_search_rank(
        self,
        query: str,
        candidates: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Rank search candidates by semantic relevance using NVIDIA NIM.

        Args:
            query: The search query.
            candidates: List of dicts with 'path' and 'content' keys.

        Returns:
            Ranked list with added 'relevance_score' field.
        """
        if not candidates:
            return []

        system_prompt = (
            "You are a code search engine. Given a query and code snippets, "
            "rank them by relevance. Return a JSON array of objects with "
            "'path', 'score' (0-10), and 'reason' fields. "
            "Most relevant first."
        )
        snippets = "\n---\n".join(
            f"File: {c['path']}\n{c['content'][:500]}" for c in candidates[:20]
        )
        user_prompt = f"Query: {query}\n\nSnippets:\n{snippets}"

        try:
            result = self.reason_json(system_prompt, user_prompt)
            if isinstance(result, dict) and "raw_response" not in result:
                ranked: list[dict[str, Any]] = result.get("results", [result])
                return ranked
        except Exception:
            logger.warning("Semantic ranking failed, returning unranked results")

        return [{"path": c["path"], "score": 5, "reason": "unranked"} for c in candidates]
