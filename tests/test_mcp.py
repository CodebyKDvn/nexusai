"""Tests for Nexus Skill-Core (MCP module)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from nexus.mcp.base import MCPToolCategory, MCPToolParam, MCPToolResult
from nexus.mcp.nvidia_wrapper import NvidiaToolWrapper
from nexus.mcp.sandbox import Sandbox, SandboxError
from nexus.mcp.server import MCPServer
from nexus.mcp.skill_store import SkillStore
from nexus.mcp.tools import ALL_MCP_TOOLS
from nexus.mcp.tools.code_tools import CodeExplainTool, CodeRefactorTool, SuggestFixTool
from nexus.mcp.tools.filesystem_tools import (
    FindFilesTool,
    ListDirectoryTool,
    ReadFileTool,
    ReplaceInFileTool,
    WriteFileTool,
)
from nexus.mcp.tools.git_tools import GitDiffMCPTool, GitLogTool, GitStatusMCPTool
from nexus.mcp.tools.search_tools import GrepSearchTool, SemanticSearchTool, WebSearchTool
from nexus.mcp.tools.terminal_tools import ExecuteBashTool

# ── MCPToolResult ──────────────────────────────────────────────────────

class TestMCPToolResult:
    def test_text_result(self) -> None:
        r = MCPToolResult.text("hello")
        assert r.content == [{"type": "text", "text": "hello"}]
        assert not r.is_error

    def test_error_result(self) -> None:
        r = MCPToolResult.error("boom")
        assert r.is_error
        assert "Error: boom" in r.content[0]["text"]

    def test_json_result(self) -> None:
        r = MCPToolResult.json_result({"key": "val"})
        assert not r.is_error
        parsed = json.loads(r.content[0]["text"])
        assert parsed["key"] == "val"


# ── MCPToolParam ───────────────────────────────────────────────────────

class TestMCPToolParam:
    def test_to_schema_basic(self) -> None:
        p = MCPToolParam(name="x", type="string", description="test")
        s = p.to_schema()
        assert s["type"] == "string"
        assert s["description"] == "test"

    def test_to_schema_with_enum(self) -> None:
        p = MCPToolParam(
            name="mode", type="string", description="d", enum=["a", "b"]
        )
        assert p.to_schema()["enum"] == ["a", "b"]


# ── MCPTool base ───────────────────────────────────────────────────────

class TestMCPToolBase:
    def test_input_schema(self) -> None:
        tool = ReadFileTool()
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "file_path" in schema["required"]

    def test_to_mcp_schema(self) -> None:
        tool = WriteFileTool()
        s = tool.to_mcp_schema()
        assert s["name"] == "write_file"
        assert "inputSchema" in s
        assert s["description"]

    def test_validate_missing_param(self) -> None:
        tool = ReadFileTool()
        errors = tool.validate()  # missing file_path
        assert len(errors) == 1
        assert "file_path" in errors[0]

    def test_validate_ok(self) -> None:
        tool = ReadFileTool()
        assert tool.validate(file_path="/tmp/f") == []


# ── Filesystem Tools ──────────────────────────────────────────────────

class TestFilesystemTools:
    def test_read_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = ReadFileTool().execute(file_path=str(f))
        assert not result.is_error
        assert "line1" in result.content[0]["text"]

    def test_read_file_with_offset_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        result = ReadFileTool().execute(file_path=str(f), offset=1, limit=2)
        assert not result.is_error
        text = result.content[0]["text"]
        assert "b" in text
        assert "c" in text

    def test_read_file_not_found(self) -> None:
        result = ReadFileTool().execute(file_path="/nonexistent/file.txt")
        assert result.is_error

    def test_write_file(self, tmp_path: Path) -> None:
        f = tmp_path / "subdir" / "out.txt"
        result = WriteFileTool().execute(file_path=str(f), content="hello")
        assert not result.is_error
        assert f.read_text() == "hello"

    def test_list_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "subdir").mkdir()
        result = ListDirectoryTool().execute(dir_path=str(tmp_path))
        assert not result.is_error
        text = result.content[0]["text"]
        assert "a.py" in text
        assert "subdir/" in text

    def test_list_directory_with_ignore(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()
        (tmp_path / "node_modules").mkdir()
        result = ListDirectoryTool().execute(
            dir_path=str(tmp_path), ignore="node_modules"
        )
        text = result.content[0]["text"]
        assert "node_modules" not in text

    def test_find_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        (tmp_path / "c.txt").touch()
        result = FindFilesTool().execute(pattern="*.py", path=str(tmp_path))
        assert not result.is_error
        text = result.content[0]["text"]
        assert "2 file(s)" in text

    def test_replace_in_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("hello world")
        result = ReplaceInFileTool().execute(
            file_path=str(f), old_string="hello", new_string="hi"
        )
        assert not result.is_error
        assert f.read_text() == "hi world"

    def test_replace_in_file_multiple_blocked(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("aa aa aa")
        result = ReplaceInFileTool().execute(
            file_path=str(f), old_string="aa", new_string="bb"
        )
        assert result.is_error
        assert "3 occurrences" in result.content[0]["text"]

    def test_replace_in_file_multiple_allowed(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("aa aa aa")
        result = ReplaceInFileTool().execute(
            file_path=str(f),
            old_string="aa",
            new_string="bb",
            allow_multiple=True,
        )
        assert not result.is_error
        assert f.read_text() == "bb bb bb"


# ── Terminal Tools ─────────────────────────────────────────────────────

class TestTerminalTools:
    def test_execute_bash(self) -> None:
        result = ExecuteBashTool().execute(command="echo hello")
        assert not result.is_error
        assert "hello" in result.content[0]["text"]

    def test_execute_bash_failure(self) -> None:
        result = ExecuteBashTool().execute(command="false")
        assert result.is_error

    def test_execute_bash_blocked(self) -> None:
        result = ExecuteBashTool().execute(command="rm -rf /")
        assert result.is_error


# ── Search Tools ───────────────────────────────────────────────────────

class TestSearchTools:
    def test_grep_search(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    pass\n")
        result = GrepSearchTool().execute(pattern="hello", path=str(tmp_path))
        assert not result.is_error
        text = result.content[0]["text"]
        assert "hello" in text

    def test_grep_no_matches(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("nothing here")
        result = GrepSearchTool().execute(pattern="xyzabc123", path=str(tmp_path))
        assert not result.is_error
        assert "No matches" in result.content[0]["text"]

    def test_web_search_no_dependency(self) -> None:
        # If duckduckgo_search is not installed, should error gracefully
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            tool = WebSearchTool()
            # Just verify the tool has the right metadata
            assert tool.name == "web_search"
            assert tool.source == "gemini"

    def test_semantic_search_no_results(self, tmp_path: Path) -> None:
        result = SemanticSearchTool().execute(
            query="nonexistent function", path=str(tmp_path)
        )
        assert "No files found" in result.content[0]["text"]


# ── Git Tools ──────────────────────────────────────────────────────────

class TestGitTools:
    def test_git_status(self, tmp_path: Path) -> None:
        # Init a temp repo
        os.system(f"cd {tmp_path} && git init -q && git commit --allow-empty -m 'init' -q")
        result = GitStatusMCPTool().execute(cwd=str(tmp_path))
        assert not result.is_error

    def test_git_diff(self, tmp_path: Path) -> None:
        os.system(f"cd {tmp_path} && git init -q && git commit --allow-empty -m 'init' -q")
        result = GitDiffMCPTool().execute(cwd=str(tmp_path))
        assert not result.is_error

    def test_git_log(self, tmp_path: Path) -> None:
        os.system(f"cd {tmp_path} && git init -q && git commit --allow-empty -m 'init' -q")
        result = GitLogTool().execute(cwd=str(tmp_path))
        assert not result.is_error
        assert "init" in result.content[0]["text"]


# ── Code Tools ─────────────────────────────────────────────────────────

class TestCodeTools:
    def test_code_refactor_no_api_key(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def hello(): pass")
        with patch.dict(os.environ, {}, clear=True):
            result = CodeRefactorTool().execute(
                file_path=str(f), instruction="add docstring"
            )
        assert result.is_error
        assert "NVIDIA_API_KEY" in result.content[0]["text"]

    def test_code_explain_no_api_key(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("print('hi')")
        with patch.dict(os.environ, {}, clear=True):
            result = CodeExplainTool().execute(file_path=str(f))
        assert result.is_error

    def test_suggest_fix_no_api_key(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1/0")
        with patch.dict(os.environ, {}, clear=True):
            result = SuggestFixTool().execute(
                file_path=str(f), error_message="ZeroDivisionError"
            )
        assert result.is_error

    def test_code_refactor_file_not_found(self) -> None:
        result = CodeRefactorTool().execute(
            file_path="/nonexistent.py", instruction="fix"
        )
        assert result.is_error


# ── Sandbox ────────────────────────────────────────────────────────────

class TestSandbox:
    def test_validate_safe_command(self) -> None:
        sandbox = Sandbox()
        sandbox.validate_command("ls -la")  # Should not raise

    def test_validate_blocked_command(self) -> None:
        sandbox = Sandbox()
        with pytest.raises(SandboxError):
            sandbox.validate_command("rm -rf /")

    def test_validate_dangerous_pattern(self) -> None:
        sandbox = Sandbox()
        with pytest.raises(SandboxError):
            sandbox.validate_command("shutdown -h now")

    def test_execute_simple(self) -> None:
        sandbox = Sandbox()
        result = sandbox.execute("echo hi")
        assert result["exit_code"] == 0
        assert "hi" in result["stdout"]

    def test_execute_timeout(self) -> None:
        sandbox = Sandbox()
        result = sandbox.execute("sleep 10", timeout=1)
        assert result["timed_out"]

    def test_validate_path(self, tmp_path: Path) -> None:
        sandbox = Sandbox(allowed_dirs=[str(tmp_path)])
        p = sandbox.validate_path(str(tmp_path / "file.txt"))
        assert str(tmp_path) in str(p)

    def test_validate_path_outside(self, tmp_path: Path) -> None:
        sandbox = Sandbox(allowed_dirs=[str(tmp_path)])
        with pytest.raises(SandboxError):
            sandbox.validate_path("/etc/passwd")


# ── NvidiaToolWrapper ──────────────────────────────────────────────────

class TestNvidiaToolWrapper:
    def test_not_configured(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="")
        assert not wrapper.is_configured

    def test_configured(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test-key")
        assert wrapper.is_configured

    def test_reason_no_key(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="")
        from tenacity import RetryError

        with pytest.raises(RetryError):
            wrapper.reason("sys", "user")

    def test_code_transform_calls_reason(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        with patch.object(wrapper, "reason", return_value="transformed") as m:
            result = wrapper.code_transform("x=1", "add type hint", "python")
        assert result == "transformed"
        m.assert_called_once()

    def test_explain_code(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        with patch.object(wrapper, "reason", return_value="explanation"):
            result = wrapper.explain_code("x=1", "python")
        assert result == "explanation"

    def test_suggest_fix(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        with patch.object(wrapper, "reason", return_value="fixed"):
            result = wrapper.suggest_fix("x=1/0", "ZeroDivision", "python")
        assert result == "fixed"

    def test_reason_json_valid(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        with patch.object(wrapper, "reason", return_value='{"key": "val"}'):
            result = wrapper.reason_json("sys", "user")
        assert result["key"] == "val"

    def test_reason_json_invalid(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        with patch.object(wrapper, "reason", return_value="not json"):
            result = wrapper.reason_json("sys", "user")
        assert result["parse_error"] is True

    def test_semantic_search_rank_empty(self) -> None:
        wrapper = NvidiaToolWrapper(api_key="test")
        assert wrapper.semantic_search_rank("query", []) == []


# ── SkillStore ─────────────────────────────────────────────────────────

class TestSkillStore:
    def test_register_and_get(self) -> None:
        store = SkillStore()
        tool = ReadFileTool()
        store.register(tool)
        assert store.get("read_file") is tool

    def test_register_all(self) -> None:
        store = SkillStore()
        store.register_all(ALL_MCP_TOOLS)
        assert len(store.list_tools()) == len(ALL_MCP_TOOLS)

    def test_unregister(self) -> None:
        store = SkillStore()
        store.register(ReadFileTool())
        assert store.unregister("read_file")
        assert store.get("read_file") is None
        assert not store.unregister("nonexistent")

    def test_list_schemas(self) -> None:
        store = SkillStore()
        store.register(ReadFileTool())
        schemas = store.list_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "read_file"

    def test_list_by_category(self) -> None:
        store = SkillStore()
        store.register_all(ALL_MCP_TOOLS)
        fs = store.list_by_category("filesystem")
        assert len(fs) == 5

    def test_list_by_source(self) -> None:
        store = SkillStore()
        store.register_all(ALL_MCP_TOOLS)
        codex = store.list_by_source("codex")
        assert len(codex) > 0

    def test_execute_unknown(self) -> None:
        store = SkillStore()
        result = store.execute("nonexistent")
        assert result.is_error

    def test_execute_validation_error(self) -> None:
        store = SkillStore()
        store.register(ReadFileTool())
        result = store.execute("read_file")  # missing file_path
        assert result.is_error
        assert "file_path" in result.content[0]["text"]

    def test_execute_success(self, tmp_path: Path) -> None:
        store = SkillStore()
        store.register(ReadFileTool())
        f = tmp_path / "hi.txt"
        f.write_text("hello")
        result = store.execute("read_file", file_path=str(f))
        assert not result.is_error

    def test_load_from_json(self, tmp_path: Path) -> None:
        defs = [
            {
                "name": "custom_tool",
                "description": "A test tool",
                "category": "terminal",
                "source": "custom",
                "parameters": [
                    {"name": "input", "type": "string", "description": "Input val"}
                ],
                "command_template": "echo {input}",
            }
        ]
        f = tmp_path / "tools.json"
        f.write_text(json.dumps(defs))
        store = SkillStore()
        count = store.load_from_json(str(f))
        assert count == 1
        assert store.get("custom_tool") is not None

    def test_load_from_json_missing_file(self) -> None:
        store = SkillStore()
        assert store.load_from_json("/nonexistent.json") == 0

    def test_to_catalog(self) -> None:
        store = SkillStore()
        store.register_all(ALL_MCP_TOOLS)
        catalog = store.to_catalog()
        assert "Tool Catalog" in catalog
        assert "read_file" in catalog

    def test_api_key_management(self) -> None:
        store = SkillStore()
        store.set_api_key("TEST_KEY", "abc123")
        assert store.get_api_key("TEST_KEY") == "abc123"
        assert store.get_api_key("MISSING") is None


# ── MCPServer ──────────────────────────────────────────────────────────

class TestMCPServer:
    def test_initialize(self) -> None:
        server = MCPServer()
        resp = server.handle_request({"method": "initialize", "id": 1})
        assert resp["id"] == 1
        result = resp["result"]
        assert result["serverInfo"]["name"] == "nexus-skill-core"
        assert "tools" in result["capabilities"]

    def test_tools_list(self) -> None:
        server = MCPServer()
        resp = server.handle_request({"method": "tools/list", "id": 2})
        tools = resp["result"]["tools"]
        assert len(tools) == len(ALL_MCP_TOOLS)
        # Check each tool has required fields
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "inputSchema" in t

    def test_tools_call_success(self) -> None:
        server = MCPServer()
        resp = server.handle_request({
            "method": "tools/call",
            "id": 3,
            "params": {
                "name": "execute_bash",
                "arguments": {"command": "echo test"},
            },
        })
        result = resp["result"]
        assert not result["isError"]
        assert "test" in result["content"][0]["text"]

    def test_tools_call_unknown(self) -> None:
        server = MCPServer()
        resp = server.handle_request({
            "method": "tools/call",
            "id": 4,
            "params": {"name": "unknown_tool", "arguments": {}},
        })
        assert resp["result"]["isError"]

    def test_unknown_method(self) -> None:
        server = MCPServer()
        resp = server.handle_request({"method": "unknown/method", "id": 5})
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_create_app(self) -> None:
        server = MCPServer()
        app = server.create_app()
        # FastAPI app should have routes
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/tools" in routes
        assert "/mcp" in routes

    def test_server_has_all_tools(self) -> None:
        """Verify server registers exactly the expected tool count."""
        server = MCPServer()
        assert len(server.store.list_tools()) == 17


# ── ALL_MCP_TOOLS collection ──────────────────────────────────────────

class TestAllMCPTools:
    def test_tool_count(self) -> None:
        assert len(ALL_MCP_TOOLS) == 17

    def test_all_have_required_fields(self) -> None:
        for tool in ALL_MCP_TOOLS:
            assert tool.name, f"Tool missing name: {tool}"
            assert tool.description, f"Tool {tool.name} missing description"
            assert tool.category, f"Tool {tool.name} missing category"
            assert tool.source, f"Tool {tool.name} missing source"
            assert isinstance(tool.parameters, list)

    def test_unique_names(self) -> None:
        names = [t.name for t in ALL_MCP_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_categories_valid(self) -> None:
        for tool in ALL_MCP_TOOLS:
            assert tool.category in MCPToolCategory.__members__.values()

    def test_schemas_valid(self) -> None:
        for tool in ALL_MCP_TOOLS:
            schema = tool.to_mcp_schema()
            assert schema["name"] == tool.name
            assert "inputSchema" in schema
            input_schema = schema["inputSchema"]
            assert input_schema["type"] == "object"
