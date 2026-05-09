"""Safety sandbox layer for terminal/system command execution."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Exact commands that are never allowed (matched as full command)
BLOCKED_EXACT = frozenset({
    ":(){ :|:& };:",
})

# Regex patterns for destructive operations.
# These are anchored so that e.g. "rm -rf /tmp/build" is allowed
# but "rm -rf /" and "rm -rf /*" are blocked.
DANGEROUS_REGEXES: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-[a-z]*r[a-z]*f[a-z]*\s+/\s*$"),    # rm -rf /
    re.compile(r"rm\s+-[a-z]*r[a-z]*f[a-z]*\s+/\*"),       # rm -rf /*
    re.compile(r"chmod\s+-r\s+777\s+/\s*$"),               # chmod -R 777 /
    re.compile(r"mkfs\.?"),                                 # mkfs / mkfs.*
    re.compile(r"dd\s+if=/dev/zero"),                       # dd if=/dev/zero
    re.compile(r">\s*/dev/sda"),                            # > /dev/sda
    re.compile(r"format\s+c:"),                             # format c:
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\binit\s+[06]\b"),
]


class SandboxError(Exception):
    """Raised when a command violates sandbox rules."""


class Sandbox:
    """Safety layer for executing terminal commands.

    Provides:
      - Command validation against blocklists
      - Working directory enforcement
      - Timeout limits
      - Output size limits
      - Optional path restrictions
    """

    def __init__(
        self,
        root_dir: str | None = None,
        allowed_dirs: list[str] | None = None,
        max_output_size: int = 50_000,
        default_timeout: int = 30,
    ) -> None:
        self._root_dir = root_dir or os.getcwd()
        self._allowed_dirs = allowed_dirs
        self._max_output_size = max_output_size
        self._default_timeout = default_timeout

    def validate_command(self, command: str) -> None:
        """Check if a command is safe to execute.

        Raises:
            SandboxError: If the command is blocked.
        """
        cmd_lower = command.lower().strip()
        cmd_normalized = re.sub(r"\s+", " ", cmd_lower)

        if cmd_normalized in BLOCKED_EXACT:
            raise SandboxError(f"Blocked command: {command}")

        for pattern in DANGEROUS_REGEXES:
            if pattern.search(cmd_normalized):
                raise SandboxError(
                    f"Potentially dangerous command detected: {command}"
                )

    def validate_path(self, path: str) -> Path:
        """Validate that a path is within allowed directories.

        Returns:
            The resolved Path object.

        Raises:
            SandboxError: If the path is outside allowed boundaries.
        """
        resolved = Path(path).resolve()

        if self._allowed_dirs:
            for allowed in self._allowed_dirs:
                if str(resolved).startswith(str(Path(allowed).resolve())):
                    return resolved
            raise SandboxError(
                f"Path {resolved} is outside allowed directories: {self._allowed_dirs}"
            )

        return resolved

    def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command within the sandbox.

        Returns:
            Dict with 'stdout', 'stderr', 'exit_code', 'timed_out' keys.
        """
        self.validate_command(command)
        work_dir = cwd or self._root_dir
        effective_timeout = timeout or self._default_timeout

        run_env = {**os.environ}
        if env:
            run_env.update(env)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=effective_timeout,
                env=run_env,
            )

            stdout = result.stdout
            stderr = result.stderr
            if len(stdout) > self._max_output_size:
                stdout = (
                    stdout[: self._max_output_size]
                    + f"\n... (truncated, {len(result.stdout)} total chars)"
                )
            if len(stderr) > self._max_output_size:
                stderr = (
                    stderr[: self._max_output_size]
                    + f"\n... (truncated, {len(result.stderr)} total chars)"
                )

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {effective_timeout}s",
                "exit_code": -1,
                "timed_out": True,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "timed_out": False,
            }
