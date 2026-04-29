"""Tests for the tool system."""

from __future__ import annotations

import os
import tempfile

from nexus.core.tool import ToolRegistry
from nexus.tools.file_ops import FileDeleteTool, FileEditTool, FileReadTool, FileWriteTool
from nexus.tools.search import GrepTool
from nexus.tools.terminal import TerminalTool


class TestFileReadTool:
    def test_read_existing_file(self) -> None:
        tool = FileReadTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name

        try:
            result = tool.execute(path=path)
            assert result.ok
            assert result.output == "hello world"
        finally:
            os.unlink(path)

    def test_read_nonexistent_file(self) -> None:
        tool = FileReadTool()
        result = tool.execute(path="/tmp/nonexistent_file_xyz.txt")
        assert not result.ok
        assert "not found" in (result.error or "").lower()


class TestFileWriteTool:
    def test_write_file(self) -> None:
        tool = FileWriteTool()
        path = f"/tmp/test_write_{os.getpid()}.txt"

        try:
            result = tool.execute(path=path, content="test content")
            assert result.ok

            with open(path) as f:
                assert f.read() == "test content"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_write_creates_dirs(self) -> None:
        tool = FileWriteTool()
        path = f"/tmp/test_nexus_dir_{os.getpid()}/sub/file.txt"

        try:
            result = tool.execute(path=path, content="nested")
            assert result.ok

            with open(path) as f:
                assert f.read() == "nested"
        finally:
            import shutil
            shutil.rmtree(f"/tmp/test_nexus_dir_{os.getpid()}", ignore_errors=True)


class TestFileEditTool:
    def test_edit_file(self) -> None:
        tool = FileEditTool()
        path = f"/tmp/test_edit_{os.getpid()}.txt"

        with open(path, "w") as f:
            f.write("foo bar baz")

        try:
            result = tool.execute(path=path, old_string="bar", new_string="qux")
            assert result.ok

            with open(path) as f:
                assert f.read() == "foo qux baz"
        finally:
            os.unlink(path)

    def test_edit_string_not_found(self) -> None:
        tool = FileEditTool()
        path = f"/tmp/test_edit_nf_{os.getpid()}.txt"

        with open(path, "w") as f:
            f.write("hello")

        try:
            result = tool.execute(path=path, old_string="xyz", new_string="abc")
            assert not result.ok
        finally:
            os.unlink(path)


class TestFileDeleteTool:
    def test_delete_file(self) -> None:
        tool = FileDeleteTool()
        path = f"/tmp/test_del_{os.getpid()}.txt"

        with open(path, "w") as f:
            f.write("to delete")

        result = tool.execute(path=path)
        assert result.ok
        assert not os.path.exists(path)


class TestTerminalTool:
    def test_echo(self) -> None:
        tool = TerminalTool()
        result = tool.execute(command="echo hello")
        assert result.ok
        assert "hello" in (result.output or "")

    def test_failing_command(self) -> None:
        tool = TerminalTool()
        result = tool.execute(command="false")
        assert not result.ok

    def test_timeout(self) -> None:
        tool = TerminalTool()
        result = tool.execute(command="sleep 10", timeout=1)
        assert result.status.value == "timeout"


class TestGrepTool:
    def test_grep_pattern(self) -> None:
        tool = GrepTool()
        path = f"/tmp/test_grep_{os.getpid()}"
        os.makedirs(path, exist_ok=True)

        with open(f"{path}/test.py", "w") as f:
            f.write("def hello():\n    print('world')\n")

        try:
            result = tool.execute(pattern="hello", path=path)
            assert result.ok
            assert "hello" in (result.output or "")
        finally:
            import shutil
            shutil.rmtree(path, ignore_errors=True)


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = FileReadTool()
        registry.register(tool)

        assert registry.get("file_read") is tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(FileReadTool())
        registry.register(FileWriteTool())

        tools = registry.list_tools()
        assert len(tools) == 2

    def test_get_schemas(self) -> None:
        registry = ToolRegistry()
        registry.register(FileReadTool())

        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "file_read"
